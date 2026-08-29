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
    dispatch_tool_names,
    dispatch_vault_tool,
    mcp_tool_names,
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


def test_mcp_search_tag_returns_slim_array(tmp_path: Path) -> None:
    """MCP surface keeps pre-#3041 array projection; orchestrator keeps {notes: ...}."""
    import json

    from digivault.tool_dispatch import register_mcp_tools

    (tmp_path / "a.md").write_text("---\ntitle: A\ntags: [doc]\n---\n\n", encoding="utf-8")
    vault = Vault(tmp_path)

    class _FakeMcp:
        def __init__(self) -> None:
            self.tools: dict[str, object] = {}

        def tool(self, *, name: str):
            def deco(fn):
                self.tools[name] = fn
                return fn

            return deco

    fake = _FakeMcp()
    register_mcp_tools(fake, lambda: vault)
    raw = fake.tools[TOOL_VAULT_SEARCH_TAG]("doc")  # type: ignore[operator]
    assert isinstance(raw, str)
    payload = json.loads(raw)
    assert isinstance(payload, list)
    assert payload == [{"name": "a", "title": "A", "rel_path": "a.md"}]

    orch = dispatch_vault_tool(TOOL_VAULT_SEARCH_TAG, {"tag": "doc"}, vault)
    assert orch.ok is True
    assert isinstance(orch.data, dict)
    assert "notes" in orch.data
    assert orch.data["notes"][0]["name"] == "a"


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
