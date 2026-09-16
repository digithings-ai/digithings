"""path_prefix scoping for the digivault MCP vault-local tools (#4223 review).

The digigraph MCP client injects an operator ``setup.path_prefix`` as a tool
kwarg (``mcp_client.call_prefixed_tool``). Before this, FastMCP dropped the
unknown kwarg and every vault-local tool silently served the whole
``DIGIVAULT_ROOT`` — cross-corpus reads and writes. These tests pin:

- the prefix scopes ``search_tag`` / ``backlinks`` / ``lint`` / ``create_note``
  to a subdirectory,
- a prefix can never escape the vault root (``..`` refused, absolute refused),
- absent/blank prefixes keep whole-vault behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivault.tool_dispatch import (
    MCP_TOOL_BACKLINKS,
    MCP_TOOL_CREATE_NOTE,
    MCP_TOOL_LINT,
    MCP_TOOL_SEARCH_TAG,
    TOOL_VAULT_BACKLINKS,
    TOOL_VAULT_CREATE_NOTE,
    TOOL_VAULT_LINT,
    TOOL_VAULT_SEARCH_TAG,
    dispatch_vault_tool,
    register_mcp_tools,
    resolve_vault_prefix,
)
from digivault.vault import Vault

pytestmark = pytest.mark.unit

PREFIX = "clients/acme"


def _vault(tmp_path: Path) -> Vault:
    """Two corpora plus a root note; ``clients/acme`` links to a sibling."""
    acme = tmp_path / PREFIX
    other = tmp_path / "clients/other"
    acme.mkdir(parents=True)
    other.mkdir(parents=True)
    (acme / "hub.md").write_text(
        "---\ntitle: Acme hub\ntags: [guide]\n---\nsee [[missing-doc]]\n", encoding="utf-8"
    )
    (acme / "note.md").write_text(
        "---\ntitle: Acme note\ntags: [guide]\n---\nsee [[hub]]\n", encoding="utf-8"
    )
    (other / "note.md").write_text(
        "---\ntitle: Other note\ntags: [guide]\n---\nsee [[hub]]\n", encoding="utf-8"
    )
    (tmp_path / "outside.md").write_text(
        "---\ntitle: Outside\ntags: [guide]\n---\nsee [[note]]\n", encoding="utf-8"
    )
    return Vault(tmp_path)


class _FakeMcp:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *, name: str):
        def deco(fn):
            self.tools[name] = fn
            return fn

        return deco


def _surface(tmp_path: Path) -> dict[str, object]:
    fake = _FakeMcp()
    vault = _vault(tmp_path)
    register_mcp_tools(fake, lambda: vault)
    return fake.tools


def _search_tag_names(raw: str) -> list[str]:
    return [row["name"] for row in json.loads(raw)]


def test_search_tag_scoped_to_prefix(tmp_path: Path) -> None:
    raw = _surface(tmp_path)[MCP_TOOL_SEARCH_TAG]("guide", path_prefix=PREFIX)  # type: ignore[operator]
    assert _search_tag_names(raw) == ["hub", "note"]


def test_search_tag_prefix_boundary_is_path_component(tmp_path: Path) -> None:
    """``clients/acme`` must not match ``clients/acme-evil`` (#2358 boundary rule)."""
    evil = tmp_path / "clients/acme-evil"
    evil.mkdir(parents=True)
    (evil / "evil.md").write_text("---\ntitle: Evil\ntags: [guide]\n---\n\n", encoding="utf-8")
    raw = _surface(tmp_path)[MCP_TOOL_SEARCH_TAG]("guide", path_prefix=PREFIX)  # type: ignore[operator]
    assert "evil" not in _search_tag_names(raw)


def test_search_tag_blank_prefix_keeps_whole_vault(tmp_path: Path) -> None:
    raw = _surface(tmp_path)[MCP_TOOL_SEARCH_TAG]("guide", path_prefix="  ")  # type: ignore[operator]
    assert set(_search_tag_names(raw)) == {"hub", "note", "outside"}


def test_backlinks_scoped_to_prefix(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    payload = json.loads(surface[MCP_TOOL_BACKLINKS]("hub", path_prefix=PREFIX))  # type: ignore[operator]
    assert payload["backlinks"] == ["note"]


def test_backlinks_outside_prefix_reports_missing(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    raw = surface[MCP_TOOL_BACKLINKS]("outside", path_prefix=PREFIX)  # type: ignore[operator]
    assert "No such note" in raw


def test_lint_scoped_to_prefix(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    scoped = json.loads(surface[MCP_TOOL_LINT](path_prefix=PREFIX))  # type: ignore[operator]
    assert scoped["note_count"] == 2
    # The unresolved [[missing-doc]] lives in clients/acme/hub.md and must still
    # be reported inside the scoped corpus.
    assert any(i["kind"] == "unresolved_link" for i in scoped["issues"])
    whole = json.loads(surface[MCP_TOOL_LINT]())  # type: ignore[operator]
    # clients/other/note.md collides with clients/acme/note.md and is not
    # indexed (stem duplicates surface as a lint issue instead).
    assert whole["note_count"] == 3


def test_create_note_lands_beneath_prefix(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    raw = surface[MCP_TOOL_CREATE_NOTE]("fresh", title="Fresh", path_prefix=PREFIX)  # type: ignore[operator]
    created = json.loads(raw)
    assert created["rel_path"] == f"{PREFIX}/fresh.md"
    assert (tmp_path / PREFIX / "fresh.md").is_file()
    assert not (tmp_path / "fresh.md").exists()


def test_create_note_rejects_traversal_prefix(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    raw = surface[MCP_TOOL_CREATE_NOTE]("escape", path_prefix="../outside-dir")  # type: ignore[operator]
    assert "[digivault error:" in raw
    assert not (tmp_path.parent / "outside-dir").exists()


@pytest.mark.parametrize(
    "prefix",
    ["../evil", "clients/../evil", "..", ".", ".hidden", "clients/.hidden"],
)
def test_dispatch_rejects_traversal_prefix_everywhere(tmp_path: Path, prefix: str) -> None:
    vault = _vault(tmp_path)
    for name, args in (
        (TOOL_VAULT_SEARCH_TAG, {"tag": "guide", "path_prefix": prefix}),
        (TOOL_VAULT_BACKLINKS, {"name": "hub", "path_prefix": prefix}),
        (TOOL_VAULT_LINT, {"path_prefix": prefix}),
        (TOOL_VAULT_CREATE_NOTE, {"name": "x", "path_prefix": prefix}),
    ):
        result = dispatch_vault_tool(name, args, vault)
        assert result.ok is False, name
        assert result.error is not None and "path_prefix" in result.error


def test_resolve_vault_prefix_normalizes_blank_and_slashes() -> None:
    assert resolve_vault_prefix(None) == ""
    assert resolve_vault_prefix("") == ""
    assert resolve_vault_prefix("  /  ") == ""
    assert resolve_vault_prefix("/clients/acme/") == "clients/acme"
    assert resolve_vault_prefix("clients\\acme") == "clients/acme"


def test_dispatch_create_note_whole_vault_without_prefix(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    result = dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, {"name": "root-note"}, vault)
    assert result.ok is True
    assert (tmp_path / "root-note.md").is_file()
