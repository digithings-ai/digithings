"""Leaf: ingest OpenAPI/Swagger JSON files as ``PageClass.openapi`` pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any  # score:allow untyped any — OpenAPI JSON nodes are open dicts

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
    load_openapi_sources,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

# An ATX heading at true line start ("#" through "######" followed by whitespace).
# Mirrors digisearch's heading.py _HEADING split-point rule, so anything that would
# act as a split point there is exactly what needs escaping here.
_ATX_HEADING_START = re.compile(r"^(#{1,6})([ \t])", re.MULTILINE)

# A fence opener/closer candidate: ``` or ~~~, three or more of the same character.
# Mirrors heading.py's _FENCE rule (same-char, len >= open, to close).
_FENCE_LINE = re.compile(r"^(`{3,}|~{3,})")

# Every character that can start a new physical line, plus the other Unicode/ASCII
# separators some renderers also treat as line breaks (vertical tab, form feed, NEL,
# LINE/PARAGRAPH SEPARATOR, the C1 group-separator family). Collapsing every one of
# these to a space is what makes a value genuinely single-line: no line-structure
# character survives, so it can never itself begin a new physical output line.
_LINE_STRUCTURE = re.compile(r"[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")

# A run of plain horizontal whitespace, collapsed to one space after the above pass
# turns every line-structure character into a space too.
_WHITESPACE_RUN = re.compile(r"[ \t]+")


def _sanitize_free_text(text: str) -> str:
    """Escape markdown structure hazards in multi-line free text placed as its OWN
    standalone block (``lines.extend([text, ""])`` — the value occupies whole output
    lines by itself, with no literal prefix sharing its first line).

    Exactly two call sites qualify and may use this: ``info.description`` and an
    operation's ``description``. Legitimate multi-line prose is wanted at both, so
    this preserves newlines rather than collapsing them — which is safe ONLY because
    the value's first physical line really does begin at true column 0 of an output
    line for these two sites. Every other interpolation site in this module places a
    value INLINE after a literal prefix (``"## "``, ``"**"``, ``"Tags: "``, etc.), and
    for those a fence or heading in the value's own text is not a real hazard once
    embedded (it starts mid-line, after the prefix) — the actual hazard there is that
    the value could contain a newline at all, which is what ``_sanitize_inline`` (not
    this function) prevents outright. Do not route an inline site through this
    function: its fence-tracking assumes the value's first line starts a real output
    line, which is false whenever a literal prefix precedes it, and letting an
    unbalanced fence's auto-appended closer inherit the template's trailing text (e.g.
    ``` ```** ```) is exactly the bug this module was previously patched for.

    ``openapi_to_markdown`` embeds spec-author text verbatim into a markdown document
    that ``heading_segments`` then parses for its own section boundaries. Left
    unescaped, that text can hijack the document's structure two ways:

    - An ATX heading line (``# ...`` .. ``###### ...``) becomes a spurious split
      point, stealing the rest of the enclosing operation's body into its own
      segment and corrupting breadcrumbs for everything after it.
    - An unbalanced fenced code block (``` or ~~~, any length >= 3) leaves the
      whole document "inside a fence" from the parser's point of view, silently
      swallowing every subsequent ``## METHOD /path`` heading.

    This function neutralizes both without dropping any words: heading markers are
    escaped in place (the line no longer starts with ``#``, but its text survives),
    and any fence left open by the end of the text is closed. Heading escaping is
    fence-aware: a line inside a *balanced* fenced region is never touched, because
    it cannot act as a split point there anyway (the downstream segmenter is itself
    fence-aware) and escaping it would corrupt code meant to render verbatim.
    """
    if not text:
        return text
    fence_char = ""
    fence_len = 0
    in_fence = False
    out_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if in_fence:
            out_lines.append(line)
            candidate = _FENCE_LINE.match(stripped)
            if (
                candidate is not None
                and candidate.group(1)[0] == fence_char
                and len(candidate.group(1)) >= fence_len
            ):
                in_fence = False
                fence_char = ""
                fence_len = 0
            continue
        opener = _FENCE_LINE.match(stripped)
        if opener:
            in_fence = True
            fence_char = opener.group(1)[0]
            fence_len = len(opener.group(1))
            out_lines.append(line)
            continue
        out_lines.append(_ATX_HEADING_START.sub(lambda m: "\\" + m.group(1) + m.group(2), line))
    escaped = "\n".join(out_lines)
    if in_fence:
        escaped = f"{escaped}\n{fence_char * fence_len}"
    return escaped


def _sanitize_inline(value: object) -> str:
    """Sanitize a spec-author-supplied value for INLINE interpolation.

    THE INVARIANT this module maintains: any spec-author value interpolated inline
    into a structured markdown line — i.e. anywhere it is placed after a literal
    prefix sharing that same output line (``"# "``, ``"**"``, ``"Tags: "``,
    ``"Operation ID: `"``, ``"- `"``, ``"Endpoint: "``, ``"## "``, ``"→ "``, ``" v"``,
    a route string, a schema/media-type name, a response status code — anything that
    is NOT one of the two standalone-block description placements) is always
    single-line. This is the single choke point every such site must route through.

    Collapsing every line break (``\\n``, ``\\r\\n``, ``\\r``) and other
    line-structure character (vertical tab, form feed, NEL, LINE/PARAGRAPH SEPARATOR,
    the C1 group separators) into a single space, then collapsing the resulting
    whitespace runs and stripping, is what makes the invariant hold: a value that
    cannot contain a newline cannot open a fenced code block, cannot start an ATX
    heading on a line of its own, and cannot otherwise alter the document's
    line-based structure at all. That is strictly stronger than — and replaces the
    need for — fence tracking or heading escaping at inline sites, which is exactly
    where the previous three fix rounds kept leaving a new field unescaped: their
    fence-tracking silently assumed the value's own first line began at true column 0
    of an output line, which is only ever true for a standalone block, never for an
    inline site. No characters are dropped beyond whitespace collapsing, so this is
    lossless in words.

    The only two sites that legitimately need multi-line prose — ``info.description``
    and an operation's ``description``, both placed as their OWN standalone line via
    ``lines.extend([text, ""])`` — are exempt and use ``_sanitize_free_text`` instead.
    A future interpolation site has exactly two choices, never a bare ``str(value)``:
    this function if it shares a line with other template text, or
    ``_sanitize_free_text`` if it is one of those two standalone placements. Reaching
    for ``str(value)`` directly at a new inline site is what left every earlier gap
    open.
    """
    text = _LINE_STRUCTURE.sub(" ", str(value))
    return _WHITESPACE_RUN.sub(" ", text).strip()


def _schema_name(schema: dict[str, Any]) -> str:
    """Readable name for a schema node: the $ref tail, or its declared type."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _sanitize_inline(ref.rsplit("/", 1)[-1])
    declared = schema.get("type")
    if isinstance(declared, list):
        return _sanitize_inline(" | ".join(str(t) for t in declared)) if declared else "object"
    return _sanitize_inline(declared) if declared else "object"


def _operation_lines(route: str, method: str, operation: dict[str, Any]) -> list[str]:
    """Markdown for one operation as its own ``##`` section."""
    # The "Endpoint:" line is unconditional: it guarantees every operation section
    # has body content beyond its heading line, so heading_segments never treats it
    # as a contentless stub and merges it into a neighbouring operation (finding 3).
    safe_route = _sanitize_inline(route)
    lines = [
        f"## {method.upper()} {safe_route}",
        "",
        f"Endpoint: {method.upper()} {safe_route}",
        "",
    ]
    # summary is interpolated INLINE after "**" (lines.extend([f"**{summary}**", ""]) —
    # the literal "**" prefix shares the first line with the value) so it goes through
    # _sanitize_inline, not _sanitize_free_text; only `detail` below is a genuine
    # standalone-block placement.
    summary = _sanitize_inline(operation.get("summary") or "")
    if summary:
        lines.extend([f"**{summary}**", ""])
    detail = _sanitize_free_text(str(operation.get("description") or "").strip())
    if detail:
        lines.extend([detail, ""])
    tags = operation.get("tags")
    if isinstance(tags, list) and tags:
        lines.extend([f"Tags: {_sanitize_inline(', '.join(str(t) for t in tags))}", ""])
    operation_id = operation.get("operationId")
    if operation_id:
        lines.extend([f"Operation ID: `{_sanitize_inline(operation_id)}`", ""])

    parameters = operation.get("parameters")
    if isinstance(parameters, list) and parameters:
        lines.append("Parameters:")
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            schema = parameter.get("schema")
            kind = _schema_name(schema) if isinstance(schema, dict) else "object"
            required = " (required)" if parameter.get("required") else ""
            name = _sanitize_inline(parameter.get("name", "?"))
            location = _sanitize_inline(parameter.get("in", "query"))
            lines.append(f"- `{name}` in {location}: {kind}{required}")
        lines.append("")

    body = operation.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content")
        if isinstance(content, dict):
            for media_type, media in sorted(content.items()):
                schema = media.get("schema") if isinstance(media, dict) else None
                if isinstance(schema, dict):
                    safe_media_type = _sanitize_inline(media_type)
                    lines.append(f"Request body (`{safe_media_type}`): {_schema_name(schema)}")
            lines.append("")

    responses = operation.get("responses")
    if isinstance(responses, dict) and responses:
        lines.append("Responses:")
        for code, response in sorted(responses.items()):
            # Response description is interpolated INLINE after "- `{code}`: " (see
            # below), not emitted as its own standalone line, so _sanitize_inline
            # applies here even though the same field name (`description`) is a
            # standalone-block site elsewhere in this module (info/operation level).
            text = str(response.get("description") or "") if isinstance(response, dict) else ""
            text = _sanitize_inline(text)
            schema_note = ""
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                for media in content.values():
                    schema = media.get("schema") if isinstance(media, dict) else None
                    if isinstance(schema, dict):
                        schema_note = f" → {_schema_name(schema)}"
                        break
            lines.append(f"- `{_sanitize_inline(code)}`: {text}{schema_note}".rstrip())
        lines.append("")
    return lines


def openapi_to_markdown(path: Path, *, note_type: str) -> str:
    """Build a markdown body from an OpenAPI document: one ``##`` section per operation."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"# OpenAPI (unparsed)\n\nSource: `{path.name}`\n\n```\n{raw[:8000]}\n```\n"
    info = data.get("info") if isinstance(data, dict) else None
    title = "OpenAPI"
    version = ""
    description = ""
    if isinstance(info, dict):
        # title/version are interpolated INLINE ("# {title}", " v{version}"); only
        # `description` below is the genuine standalone-block placement.
        title = _sanitize_inline(info.get("title") or title)
        version = _sanitize_inline(info.get("version") or "")
        description = str(info.get("description") or "")
    paths = data.get("paths") if isinstance(data, dict) else None
    path_items = sorted(paths.items()) if isinstance(paths, dict) else []
    lines = [
        f"# {title}",
        "",
        f"> OpenAPI reference (`{note_type}`)" + (f" v{version}" if version else ""),
        "",
    ]
    if description:
        lines.extend([_sanitize_free_text(description.strip()), ""])
    lines.append(f"Source file: `{path.as_posix()}`")
    lines.append("Content-Type: application/openapi+json")
    lines.append("")
    for route, item in path_items:
        if not isinstance(item, dict):
            continue
        for method, operation in sorted(item.items()):
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            lines.extend(_operation_lines(route, method, operation))
    return "\n".join(lines).rstrip("\n") + "\n"


def ingest_openapi_sources(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    repo_root: Path,
) -> int:
    """Stage OpenAPI files into the workdir as classified openapi pages."""
    if not manifest.openapi_sources:
        return 0
    cfg_path = Path(manifest.openapi_sources)
    if not cfg_path.is_absolute():
        cfg_path = repo_root / cfg_path
    if not cfg_path.is_file():
        raise FileNotFoundError(f"openapi_sources not found: {cfg_path}")
    cfg = load_openapi_sources(cfg_path)

    files_dir = workspace.root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for rel in cfg.files:
        src = Path(rel)
        if not src.is_absolute():
            src = repo_root / src
        if not src.is_file():
            continue
        try:
            rel_path = src.relative_to(repo_root.resolve())
        except ValueError:
            rel_path = Path(src.name)
        dest_name = slug_for_url(f"file:///{rel_path.as_posix()}") + ".md"
        dest = files_dir / dest_name
        dest.write_text(
            openapi_to_markdown(src, note_type=cfg.vault_note_type),
            encoding="utf-8",
        )
        local_rel = f"files/{dest_name}"
        source_url = f"repo://{manifest.client}/{rel_path.as_posix()}"
        workspace.append_classified(
            ClassifiedPage(
                page=DiscoveredPage(
                    url=source_url,
                    final_url=source_url,
                    content_type="application/openapi+json",
                    title=src.stem.replace("-", " ").replace("_", " "),
                    depth=0,
                    local_path=local_rel,
                    discovered_from="openapi_sources",
                ),
                page_class=PageClass.openapi,
                score=95.0,
                reasons=("openapi_sources", f"path:{rel_path.as_posix()}"),
            )
        )
        workspace.append_source_map(
            SourceMapEntry(
                local_path=local_rel,
                source_url=source_url,
                content_type="application/openapi+json",
            )
        )
        count += 1
    return count
