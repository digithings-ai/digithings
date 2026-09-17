"""Canonical vault tool routing — single registry for MCP and orchestrator invoke.

All digivault tool *names* and vault-local *handlers* live here so
``mcp_server`` and ``server.orchestrator_invoke`` do not each maintain their
own handler table. The OpenAI-style orchestrator manifest stays in
``orchestrator_tools.py`` and re-exports these name constants (documented
re-export chain ending here).

Runtime backends that need HTTP / D1 / tenant context (``digivault_search_notes``,
``digivault_get_note``) register into this same dispatch table via
:func:`register_runtime_handler` from ``server.py`` at import time. MCP
discovery is driven by :func:`mcp_tool_names`, which advertises the MCP surface
name of every vault-local handler (``search_tag``, … — digigraph then prefixes
the operator server id to get ``digivault_search_tag``) plus ``search_notes``
(the runtime-backed full-text search; required ``path_prefix``; D1 -> local ->
Supabase); ``get_note`` stays orchestrator-only, and the full runtime dispatch
set is :func:`dispatch_tool_names` (vault + runtime). Tests assert both
surfaces stay aligned with ``ORCHESTRATOR_TOOL_NAMES`` / the OpenAI manifest.

Vault-local handlers honour an optional ``path_prefix`` argument (an operator
``setup.path_prefix`` value injected by digigraph's MCP client, or a direct
caller argument): reads are filtered beneath that vault subdirectory and
``create_note`` writes beneath it, with ``..``/leading-dot components refused.
An absent or blank prefix keeps the historical whole-vault behaviour.
"""

# No `from __future__ import annotations`: the stack image ships FastMCP 1.9.3,
# which calls issubclass() on raw annotations — PEP 563 string annotations crash
# every @mcp.tool() at import (Dockerfile.digithings-stack-cloudflare marker v8).
from collections.abc import Callable, Mapping
from typing import Any  # score:allow untyped any — tool argument maps are arbitrary JSON

from pydantic import BaseModel, ConfigDict, Field

from digivault.models import LintReport, Note
from digivault.vault import Vault, VaultError

# ── canonical tool names ─────────────────────────────────────────────────────
TOOL_VAULT_SEARCH_TAG = "digivault_search_tag"
TOOL_VAULT_BACKLINKS = "digivault_backlinks"
TOOL_VAULT_LINT = "digivault_lint"
TOOL_VAULT_CREATE_NOTE = "digivault_create_note"
TOOL_VAULT_SEARCH_NOTES = "digivault_search_notes"
TOOL_VAULT_GET_NOTE = "digivault_get_note"

DISPATCH_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_VAULT_SEARCH_TAG,
        TOOL_VAULT_BACKLINKS,
        TOOL_VAULT_LINT,
        TOOL_VAULT_CREATE_NOTE,
        TOOL_VAULT_SEARCH_NOTES,
        TOOL_VAULT_GET_NOTE,
    }
)

# Tools that need DIGIVAULT_ROOT / a Vault instance (filesystem-backed).
VAULT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_VAULT_SEARCH_TAG,
        TOOL_VAULT_BACKLINKS,
        TOOL_VAULT_LINT,
        TOOL_VAULT_CREATE_NOTE,
    }
)

# Tools registered by server.py (D1 / local / Supabase / by-path). Not MCP-exposed
# until a backend context is wired; names still belong to the canonical set.
RUNTIME_ONLY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_VAULT_SEARCH_NOTES,
        TOOL_VAULT_GET_NOTE,
    }
)

assert VAULT_TOOL_NAMES | RUNTIME_ONLY_TOOL_NAMES == DISPATCH_TOOL_NAMES
assert VAULT_TOOL_NAMES.isdisjoint(RUNTIME_ONLY_TOOL_NAMES)


class ToolDispatchResult(BaseModel):
    """Structured outcome of a vault-local tool handler."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    data: dict[str, Any] | None = Field(default=None)
    error: str | None = Field(default=None)


VaultToolHandler = Callable[[Vault, Mapping[str, Any]], ToolDispatchResult]
RuntimeToolHandler = Callable[..., Any]


def resolve_vault_prefix(raw: Any) -> str:
    """Normalize a tool ``path_prefix``: ``None``/blank ⇒ whole vault ("").

    Mirrors ``d1_store.resolve_path_prefix``'s path-component boundary rule —
    ``clients/acme`` must never match ``clients/acme-evil/…`` — but keeps the
    filesystem tools' historical contract that an absent or blank prefix means
    "no scoping requested" rather than refusing the call.

    Refuses ``..``, ``.`` and leading-dot components so a prefix can never walk
    out of ``DIGIVAULT_ROOT`` or into a directory the index skips; ``Vault``'s
    own ``_safe_path`` remains the second line of defence for writes. Control
    characters (``ord(ch) < 32``, e.g. an embedded NUL) are refused here too —
    ``_safe_path`` raises a bare ``ValueError`` for them, which
    :func:`dispatch_vault_tool` does not translate into a tool error
    (#4246 review).
    """
    if raw is None:
        return ""
    text = str(raw).strip().replace("\\", "/").strip("/")
    if not text:
        return ""
    if any(ord(ch) < 32 for ch in text):
        raise VaultError(f"Invalid path_prefix: {raw!r}")
    parts = text.split("/")
    if any(part in (".", "..") or part.startswith(".") for part in parts):
        raise VaultError(f"Invalid path_prefix: {raw!r}")
    return text


def _path_under_prefix(rel_path: str, prefix: str) -> bool:
    """True when vault-relative *rel_path* (with or without ``.md``) is *prefix* or below."""
    if not prefix:
        return True
    stem = rel_path[:-3] if rel_path.endswith(".md") else rel_path
    return stem == prefix or rel_path.startswith(f"{prefix}/")


def _note_under_prefix(note: Note, prefix: str) -> bool:
    return _path_under_prefix(note.rel_path, prefix)


def _handle_search_tag(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    prefix = resolve_vault_prefix(args.get("path_prefix"))
    notes = [
        n for n in vault.search_by_tag(str(args.get("tag") or "")) if _note_under_prefix(n, prefix)
    ]
    return ToolDispatchResult(
        ok=True,
        data={"notes": [n.model_dump(mode="json") for n in notes]},
    )


def _handle_backlinks(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    name = str(args.get("name") or "")
    prefix = resolve_vault_prefix(args.get("path_prefix"))
    note = vault.get_note(name)
    if note is None or not _note_under_prefix(note, prefix):
        # Outside the prefix (or absent) reads the same as missing — a scoped
        # caller must not be able to probe sibling corpora by note name.
        return ToolDispatchResult(ok=False, error=f"No such note: {name!r}")
    backlinks: list[str] = []
    for src in vault.backlinks(name):
        src_note = vault.get_note(src)
        if src_note is not None and _note_under_prefix(src_note, prefix):
            backlinks.append(src)
    return ToolDispatchResult(ok=True, data={"name": name, "backlinks": backlinks})


def _handle_lint(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    prefix = resolve_vault_prefix(args.get("path_prefix"))
    report = vault.lint()
    if prefix:
        issues = tuple(issue for issue in report.issues if _path_under_prefix(issue.note, prefix))
        note_count = sum(1 for n in vault.list_notes() if _note_under_prefix(n, prefix))
        report = LintReport(ok=not issues, note_count=note_count, issues=issues)
    return ToolDispatchResult(ok=True, data=report.model_dump(mode="json"))


def _handle_create_note(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    if "name" not in args or not str(args.get("name") or "").strip():
        return ToolDispatchResult(ok=False, error="missing argument: 'name'")
    prefix = resolve_vault_prefix(args.get("path_prefix"))
    fm = {"title": args["title"]} if args.get("title") else {}
    try:
        note = vault.create_note(
            str(args["name"]), frontmatter=fm, body=str(args.get("body") or ""), subdir=prefix
        )
    except VaultError as exc:
        return ToolDispatchResult(ok=False, error=str(exc))
    except KeyError as exc:
        return ToolDispatchResult(ok=False, error=f"missing argument: {exc}")
    return ToolDispatchResult(ok=True, data=note.model_dump(mode="json"))


# Single vault-local handler table — MCP and orchestrator both route here.
VAULT_HANDLERS: dict[str, VaultToolHandler] = {
    TOOL_VAULT_SEARCH_TAG: _handle_search_tag,
    TOOL_VAULT_BACKLINKS: _handle_backlinks,
    TOOL_VAULT_LINT: _handle_lint,
    TOOL_VAULT_CREATE_NOTE: _handle_create_note,
}

assert frozenset(VAULT_HANDLERS) == VAULT_TOOL_NAMES

# Populated by server.py for search_notes / get_note (and any future runtime tools).
_RUNTIME_HANDLERS: dict[str, RuntimeToolHandler] = {}


def register_runtime_handler(name: str, handler: RuntimeToolHandler) -> None:
    """Register a server-side handler into the canonical dispatch table.

    Only names in :data:`RUNTIME_ONLY_TOOL_NAMES` (or more generally
    :data:`DISPATCH_TOOL_NAMES` minus vault-local) may be registered. Replacing an
    existing registration is allowed (tests / re-import).
    """
    if name not in DISPATCH_TOOL_NAMES:
        raise ValueError(f"unknown digivault tool name: {name!r}")
    if name in VAULT_HANDLERS:
        raise ValueError(f"cannot overwrite vault-local handler for {name!r}")
    _RUNTIME_HANDLERS[name] = handler


def clear_runtime_handlers() -> None:
    """Test helper — drop runtime registrations without touching vault handlers."""
    _RUNTIME_HANDLERS.clear()


# MCP surface names: clean verbs the chat sees prefixed with the operator
# server id (e.g. digivault_search_tag). The canonical dispatch ids keep the
# service prefix; these are the names MCP discovery advertises.
MCP_TOOL_SEARCH_TAG = "search_tag"
MCP_TOOL_BACKLINKS = "backlinks"
MCP_TOOL_LINT = "lint"
MCP_TOOL_CREATE_NOTE = "create_note"
MCP_TOOL_SEARCH_NOTES = "search_notes"

_MCP_SURFACE_NAMES: dict[str, str] = {
    TOOL_VAULT_SEARCH_TAG: MCP_TOOL_SEARCH_TAG,
    TOOL_VAULT_BACKLINKS: MCP_TOOL_BACKLINKS,
    TOOL_VAULT_LINT: MCP_TOOL_LINT,
    TOOL_VAULT_CREATE_NOTE: MCP_TOOL_CREATE_NOTE,
    TOOL_VAULT_SEARCH_NOTES: MCP_TOOL_SEARCH_NOTES,
}


def mcp_tool_names() -> frozenset[str]:
    """Names MCP discovery must advertise — the MCP surface name of each vault-local tool."""
    return frozenset(_MCP_SURFACE_NAMES.values())


def dispatch_tool_names() -> frozenset[str]:
    """Names the runtime can dispatch — vault handlers plus registered runtime tools."""
    return frozenset(VAULT_HANDLERS) | frozenset(_RUNTIME_HANDLERS)


def dispatch_vault_tool(
    name: str, args: Mapping[str, Any] | None, vault: Vault
) -> ToolDispatchResult:
    """Dispatch a vault-local tool by name against an open :class:`Vault`.

    Raises ``KeyError`` if ``name`` is not a vault-local tool (callers that also
    handle runtime-only tools should check :data:`VAULT_HANDLERS` first).
    """
    handler = VAULT_HANDLERS[name]
    try:
        return handler(vault, args or {})
    except VaultError as exc:
        return ToolDispatchResult(ok=False, error=str(exc))
    except KeyError as exc:
        return ToolDispatchResult(ok=False, error=f"missing argument: {exc}")


def register_mcp_tools(mcp: Any, open_vault: Callable[[], Vault]) -> frozenset[str]:
    """Register every vault-local tool on a FastMCP instance from :data:`VAULT_HANDLERS`.

    Returns the set of tool names registered (must equal :func:`mcp_tool_names`).
    Callers must not hand-register digivault tools beside this — discovery and
    dispatch stay one table.
    """
    import json as _json

    def _mcp_result(result: ToolDispatchResult) -> str:
        if not result.ok:
            return f"[digivault error: {result.error}]"
        assert result.data is not None
        return _json.dumps(result.data)

    def _mcp_search_tag_result(result: ToolDispatchResult) -> str:
        """Preserve pre-#3041 MCP contract: JSON array of {name, title, rel_path}.

        Orchestrator dispatch keeps ``{"notes": [...]}`` (full note dumps) via
        :func:`dispatch_vault_tool`; only the MCP surface projects the slim array.
        """
        if not result.ok:
            return f"[digivault error: {result.error}]"
        notes = (result.data or {}).get("notes") or []
        slim = [
            {
                "name": n.get("name"),
                "title": n.get("title"),
                "rel_path": n.get("rel_path"),
            }
            for n in notes
            if isinstance(n, Mapping)
        ]
        return _json.dumps(slim)

    @mcp.tool(name=MCP_TOOL_SEARCH_NOTES)
    def search_notes(query: str, path_prefix: str, limit: int = 10) -> str:
        """Full-text search across the vault notes under a path prefix (required)."""
        import os

        from digivault.local_search import search_local_vault
        from digivault.server import (
            _d1_configured,
            _load_d1_database_map,
            _open_d1_store,
            _open_supabase_store,
        )

        prefix = (path_prefix or "").strip()
        if not prefix:
            return "[digivault error: path_prefix is required]"
        if not (query or "").strip():
            return "[digivault error: query is required]"
        try:
            if _d1_configured():
                _load_d1_database_map()
                hits = _open_d1_store(prefix).search(query, limit=limit, path_prefix=prefix)
            elif (os.environ.get("DIGIVAULT_ROOT") or "").strip():
                hits = search_local_vault(open_vault(), query, limit=limit, path_prefix=prefix)
            else:
                hits = _open_supabase_store().search(query, limit=limit, path_prefix=prefix)
        except Exception as exc:
            return f"[digivault error: {exc}]"
        return _mcp_result(
            ToolDispatchResult(ok=True, data={"hits": [h.model_dump(mode="json") for h in hits]})
        )

    # ``path_prefix`` is declared on every handler so digigraph's MCP client can
    # inject the operator ``setup.path_prefix`` value as a tool kwarg (FastMCP
    # silently drops kwargs the signature does not declare). The client merges
    # setup over caller args, so an operator-configured prefix always wins over
    # a model-supplied one; an absent/blank value keeps whole-vault behaviour.

    @mcp.tool(name=MCP_TOOL_SEARCH_TAG)
    def digivault_search_tag(tag: str, path_prefix: str | None = None) -> str:
        """Find vault notes carrying a given tag (without '#'). Use to locate docs by topic."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_search_tag_result(
            dispatch_vault_tool(
                TOOL_VAULT_SEARCH_TAG, {"tag": tag, "path_prefix": path_prefix}, vault
            )
        )

    @mcp.tool(name=MCP_TOOL_BACKLINKS)
    def digivault_backlinks(name: str, path_prefix: str | None = None) -> str:
        """List notes that link to a given note (its backlinks)."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_result(
            dispatch_vault_tool(
                TOOL_VAULT_BACKLINKS, {"name": name, "path_prefix": path_prefix}, vault
            )
        )

    @mcp.tool(name=MCP_TOOL_LINT)
    def digivault_lint(path_prefix: str | None = None) -> str:
        """Validate the vault: unresolved wikilinks, missing frontmatter, orphans, tags."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_result(
            dispatch_vault_tool(TOOL_VAULT_LINT, {"path_prefix": path_prefix}, vault)
        )

    @mcp.tool(name=MCP_TOOL_CREATE_NOTE)
    def digivault_create_note(
        name: str, title: str | None = None, body: str = "", path_prefix: str | None = None
    ) -> str:
        """Create a new markdown note in the vault with optional title and body."""
        import os

        if os.environ.get("DIGIVAULT_MCP_WRITE") != "1":
            return "[digivault error: write tools are disabled on this MCP surface]"
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        args: dict[str, Any] = {"name": name, "body": body, "path_prefix": path_prefix}
        if title is not None:
            args["title"] = title
        return _mcp_result(dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, args, vault))

    # Bind references so ruff doesn't flag the nested defs as unused — FastMCP
    # holds them via the decorator; we only need the names for the return set.
    _ = (
        digivault_search_tag,
        digivault_backlinks,
        digivault_lint,
        digivault_create_note,
        search_notes,
    )
    return mcp_tool_names()
