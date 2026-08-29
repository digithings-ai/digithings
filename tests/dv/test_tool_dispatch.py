"""Unit tests for digivault.tool_dispatch — canonical vault tool routing (#1188).

Asserts:
- every canonical tool name has a dispatch path (vault handler or runtime claim)
- MCP discovery names equal the vault-local handler set (no drift)
- OpenAI orchestrator manifest names equal DISPATCH_TOOL_NAMES
- each vault-local tool name executes through dispatch_vault_tool
"""

from __future__ import annotations

from pathlib import Path

import pytest
from digivault.mcp_server import mcp as digivault_mcp
from digivault.orchestrator_tools import (
    ORCHESTRATOR_TOOL_NAMES,
    build_orchestrator_tool_manifest,
)
from digivault.tool_dispatch import (
    DISPATCH_TOOL_NAMES,
    RUNTIME_ONLY_TOOL_NAMES,
    TOOL_VAULT_BACKLINKS,
    TOOL_VAULT_CREATE_NOTE,
    TOOL_VAULT_GET_NOTE,
    TOOL_VAULT_LINT,
    TOOL_VAULT_SEARCH_NOTES,
    TOOL_VAULT_SEARCH_TAG,
    VAULT_HANDLERS,
    VAULT_TOOL_NAMES,
    clear_runtime_handlers,
    dispatch_tool_names,
    dispatch_vault_tool,
    mcp_tool_names,
    register_runtime_handler,
)
from digivault.vault import Vault

pytestmark = pytest.mark.unit


def test_canonical_name_partitions_cover_dispatch_set() -> None:
    assert VAULT_TOOL_NAMES | RUNTIME_ONLY_TOOL_NAMES == DISPATCH_TOOL_NAMES
    assert VAULT_TOOL_NAMES.isdisjoint(RUNTIME_ONLY_TOOL_NAMES)
    assert frozenset(VAULT_HANDLERS) == VAULT_TOOL_NAMES


def test_orchestrator_reexports_match_tool_dispatch() -> None:
    """Documented re-export chain: orchestrator_tools.ORCHESTRATOR_TOOL_NAMES ends here."""
    assert ORCHESTRATOR_TOOL_NAMES == DISPATCH_TOOL_NAMES
    manifest_names = {t["function"]["name"] for t in build_orchestrator_tool_manifest()}
    assert manifest_names == DISPATCH_TOOL_NAMES


def test_mcp_discovery_matches_vault_handler_set() -> None:
    """MCP discovery list must equal the vault-local runtime dispatch set (#1188)."""
    assert mcp_tool_names() == frozenset(VAULT_HANDLERS)
    # FastMCP keeps tools on the tool manager; names must match our registry.
    managed = digivault_mcp._tool_manager.list_tools()
    discovered = {t.name for t in managed}
    assert discovered == mcp_tool_names()


def test_server_runtime_registration_completes_dispatch_set() -> None:
    """Importing digivault.server claims search_notes / get_note on the dispatch table."""
    import digivault.server  # noqa: F401 — side-effect: register_runtime_handler

    assert dispatch_tool_names() == DISPATCH_TOOL_NAMES
    assert RUNTIME_ONLY_TOOL_NAMES <= dispatch_tool_names()


@pytest.mark.parametrize("tool_name", sorted(VAULT_TOOL_NAMES))
def test_each_vault_tool_name_dispatches(tool_name: str, tmp_path: Path) -> None:
    """Every vault-local tool name has a handler that runs (no KeyError / unknown)."""
    (tmp_path / "a.md").write_text("---\ntitle: A\ntags: [doc]\n---\nsee [[b]]\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\n\n", encoding="utf-8")
    vault = Vault(tmp_path)

    args_by_tool = {
        TOOL_VAULT_SEARCH_TAG: {"tag": "doc"},
        TOOL_VAULT_BACKLINKS: {"name": "b"},
        TOOL_VAULT_LINT: {},
        TOOL_VAULT_CREATE_NOTE: {"name": "c", "title": "C", "body": "hi"},
    }
    result = dispatch_vault_tool(tool_name, args_by_tool[tool_name], vault)
    assert result.ok is True
    assert result.data is not None


def test_dispatch_backlinks_missing_note(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\n\n", encoding="utf-8")
    result = dispatch_vault_tool(TOOL_VAULT_BACKLINKS, {"name": "missing"}, Vault(tmp_path))
    assert result.ok is False
    assert result.error is not None
    assert "No such note" in result.error


def test_dispatch_create_note_requires_name(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\n\n", encoding="utf-8")
    result = dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, {}, Vault(tmp_path))
    assert result.ok is False
    assert result.error is not None
    assert "name" in result.error


def test_dispatch_unknown_vault_tool_raises(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\n\n", encoding="utf-8")
    with pytest.raises(KeyError):
        dispatch_vault_tool("not_a_real_tool", {}, Vault(tmp_path))


def test_runtime_only_names_are_the_d1_family() -> None:
    assert RUNTIME_ONLY_TOOL_NAMES == frozenset({TOOL_VAULT_SEARCH_NOTES, TOOL_VAULT_GET_NOTE})


def test_register_runtime_handler_rejects_unknown_and_vault_local() -> None:
    clear_runtime_handlers()
    try:
        with pytest.raises(ValueError, match="unknown digivault tool name"):
            register_runtime_handler("not_a_tool", lambda: None)
        with pytest.raises(ValueError, match="cannot overwrite vault-local"):
            register_runtime_handler(TOOL_VAULT_LINT, lambda: None)
    finally:
        clear_runtime_handlers()


def test_register_runtime_handler_claims_dispatch_name() -> None:
    clear_runtime_handlers()
    try:
        called: list[str] = []

        def _handler() -> str:
            called.append("search")
            return "ok"

        register_runtime_handler(TOOL_VAULT_SEARCH_NOTES, _handler)
        assert TOOL_VAULT_SEARCH_NOTES in dispatch_tool_names()
        assert _handler() == "ok"
        assert called == ["search"]
        # Replacement is allowed for tests / re-import.
        register_runtime_handler(TOOL_VAULT_SEARCH_NOTES, lambda: "replaced")
        assert TOOL_VAULT_SEARCH_NOTES in dispatch_tool_names()
    finally:
        clear_runtime_handlers()
        assert TOOL_VAULT_SEARCH_NOTES not in dispatch_tool_names()


def test_dispatch_create_note_duplicate_returns_error(tmp_path: Path) -> None:
    (tmp_path / "exists.md").write_text("---\ntitle: Exists\n---\n\n", encoding="utf-8")
    result = dispatch_vault_tool(
        TOOL_VAULT_CREATE_NOTE,
        {"name": "exists", "title": "Dup"},
        Vault(tmp_path),
    )
    assert result.ok is False
    assert result.error == "Note already exists: 'exists'"
