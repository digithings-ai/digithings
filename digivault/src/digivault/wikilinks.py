"""Parse and rewrite Obsidian-style ``[[wikilinks]]``.

Supported forms:

- ``[[note]]``               — plain link
- ``[[note#heading]]``       — link to a heading
- ``[[note|alias]]``         — link with display text
- ``[[note#heading|alias]]`` — both
- ``![[note]]``              — embed / transclusion (also ``![[note#heading]]``)

Code spans and fenced code blocks are skipped so that ``[[...]]`` appearing in
examples is not treated as a real link.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from digivault.models import LinkRef

# Capture the optional embed '!', then the inner target between [[ ]].
_WIKILINK_RE = re.compile(r"(?P<embed>!)?\[\[(?P<inner>[^\[\]\n]+?)\]\]")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans (length-preserving)."""
    out_lines: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(" " * len(line))
            continue
        if in_fence:
            out_lines.append(" " * len(line))
        else:
            out_lines.append(line)
    joined = "".join(out_lines)
    # Inline code: replace `...` runs with spaces of equal length.
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), joined)


def _parse_inner(inner: str, embed: bool, raw: str) -> LinkRef:
    target_part, _, alias = inner.partition("|")
    name, _, heading = target_part.partition("#")
    return LinkRef(
        target=name.strip(),
        heading=heading.strip() or None,
        alias=alias.strip() or None,
        embed=embed,
        raw=raw,
    )


def parse_links(text: str) -> list[LinkRef]:
    """Return every wikilink in ``text`` (ignoring code spans/blocks)."""
    scannable = _strip_code(text)
    links: list[LinkRef] = []
    for m in _WIKILINK_RE.finditer(scannable):
        inner = m.group("inner").strip()
        if not inner:
            continue
        links.append(_parse_inner(inner, embed=bool(m.group("embed")), raw=m.group(0)))
    return links


def rewrite_target(text: str, old_name: str, new_name: str) -> str:
    """Rewrite every ``[[old_name...]]`` to point at ``new_name`` (preserving
    heading, alias and embed markers). Code spans/blocks are left untouched.

    Matching on the target name is exact (case-sensitive), consistent with how
    the vault indexes note names.
    """
    code_mask = _strip_code(text)

    def _repl(m: re.Match[str]) -> str:
        # Only rewrite matches that are NOT inside masked code (the mask blanks
        # code regions, so a real link still shows through in `code_mask`).
        if code_mask[m.start() : m.end()] != m.group(0):
            return m.group(0)
        inner = m.group("inner").strip()
        ref = _parse_inner(inner, embed=bool(m.group("embed")), raw=m.group(0))
        if ref.target != old_name:
            return m.group(0)
        rebuilt = new_name
        if ref.heading:
            rebuilt += f"#{ref.heading}"
        if ref.alias:
            rebuilt += f"|{ref.alias}"
        prefix = "!" if ref.embed else ""
        return f"{prefix}[[{rebuilt}]]"

    return _WIKILINK_RE.sub(_repl, text)


def map_targets(text: str, mapper: Callable[[str], str | None]) -> str:
    """Rewrite link targets via ``mapper`` (returns a new name, or None to skip)."""
    code_mask = _strip_code(text)

    def _repl(m: re.Match[str]) -> str:
        if code_mask[m.start() : m.end()] != m.group(0):
            return m.group(0)
        ref = _parse_inner(m.group("inner").strip(), bool(m.group("embed")), m.group(0))
        new = mapper(ref.target)
        if not new or new == ref.target:
            return m.group(0)
        rebuilt = new
        if ref.heading:
            rebuilt += f"#{ref.heading}"
        if ref.alias:
            rebuilt += f"|{ref.alias}"
        return f"{'!' if ref.embed else ''}[[{rebuilt}]]"

    return _WIKILINK_RE.sub(_repl, text)
