"""Canonical vault tool routing — single registry for MCP and orchestrator invoke.

All digivault tool *names* and vault-local *handlers* live here so
``mcp_server`` and ``server.orchestrator_invoke`` do not each maintain their
own handler table. The OpenAI-style orchestrator manifest stays in
``orchestrator_tools.py`` and re-exports these name constants (documented
re-export chain ending here).

Runtime backends that need HTTP / D1 / tenant context (``digivault_search_notes``,
``digivault_get_note``) register into this same dispatch table via
:func:`register_runtime_handler` from ``server.py`` at import time. MCP
discovery is driven by :func:`mcp_tool_names`, which equals the vault-local
handler set (filesystem tools); the full runtime dispatch set is
:func:`dispatch_tool_names` (vault + runtime). Tests assert both surfaces stay
aligned with ``ORCHESTRATOR_TOOL_NAMES`` / the OpenAI manifest.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any  # score:allow untyped any — tool argument maps are arbitrary JSON

from pydantic import BaseModel, ConfigDict, Field

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


def _handle_search_tag(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    notes = vault.search_by_tag(str(args.get("tag") or ""))
    return ToolDispatchResult(
        ok=True,
        data={"notes": [n.model_dump(mode="json") for n in notes]},
    )


def _handle_backlinks(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    name = str(args.get("name") or "")
    if vault.get_note(name) is None:
        return ToolDispatchResult(ok=False, error=f"No such note: {name!r}")
    return ToolDispatchResult(
        ok=True,
        data={"name": name, "backlinks": list(vault.backlinks(name))},
    )


def _handle_lint(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    del args  # lint takes no arguments
    return ToolDispatchResult(ok=True, data=vault.lint().model_dump(mode="json"))


def _handle_create_note(vault: Vault, args: Mapping[str, Any]) -> ToolDispatchResult:
    if "name" not in args or not str(args.get("name") or "").strip():
        return ToolDispatchResult(ok=False, error="missing argument: 'name'")
    fm = {"title": args["title"]} if args.get("title") else {}
    try:
        note = vault.create_note(
            str(args["name"]), frontmatter=fm, body=str(args.get("body") or "")
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


def mcp_tool_names() -> frozenset[str]:
    """Names MCP discovery must advertise — equals the vault-local handler set."""
    return frozenset(VAULT_HANDLERS)


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

    @mcp.tool(name=TOOL_VAULT_SEARCH_TAG)
    def digivault_search_tag(tag: str) -> str:
        """Find vault notes carrying a given tag (without '#'). Use to locate docs by topic."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_result(dispatch_vault_tool(TOOL_VAULT_SEARCH_TAG, {"tag": tag}, vault))

    @mcp.tool(name=TOOL_VAULT_BACKLINKS)
    def digivault_backlinks(name: str) -> str:
        """List notes that link to a given note (its backlinks)."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_result(dispatch_vault_tool(TOOL_VAULT_BACKLINKS, {"name": name}, vault))

    @mcp.tool(name=TOOL_VAULT_LINT)
    def digivault_lint() -> str:
        """Validate the vault: unresolved wikilinks, missing frontmatter, orphans, tags."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        return _mcp_result(dispatch_vault_tool(TOOL_VAULT_LINT, {}, vault))

    @mcp.tool(name=TOOL_VAULT_CREATE_NOTE)
    def digivault_create_note(name: str, title: str | None = None, body: str = "") -> str:
        """Create a new markdown note in the vault with optional title and body."""
        try:
            vault = open_vault()
        except VaultError as e:
            return f"[digivault error: {e}]"
        args: dict[str, Any] = {"name": name, "body": body}
        if title is not None:
            args["title"] = title
        return _mcp_result(dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, args, vault))

    # Bind references so ruff doesn't flag the nested defs as unused — FastMCP
    # holds them via the decorator; we only need the names for the return set.
    _ = (digivault_search_tag, digivault_backlinks, digivault_lint, digivault_create_note)
    return mcp_tool_names()
