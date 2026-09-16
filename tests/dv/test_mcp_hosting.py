"""digivault MCP hosting pin: the 4-tool MCP boundary + VaultError laziness.

MCP exposes exactly the four vault-local tools; ``digivault_search_notes`` /
``digivault_get_note`` stay orchestrator-only. A missing ``DIGIVAULT_ROOT``
must fail loud at tool-call time (``_open_vault``), never at import time.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digivault.tool_dispatch import mcp_tool_names
from digivault.vault import VaultError


@pytest.mark.unit
def test_mcp_tool_names_is_the_vault_local_set_plus_search_notes():
    from digivault.tool_dispatch import (
        MCP_TOOL_BACKLINKS,
        MCP_TOOL_CREATE_NOTE,
        MCP_TOOL_LINT,
        MCP_TOOL_SEARCH_NOTES,
        MCP_TOOL_SEARCH_TAG,
    )

    assert mcp_tool_names() == {
        MCP_TOOL_SEARCH_TAG,
        MCP_TOOL_BACKLINKS,
        MCP_TOOL_LINT,
        MCP_TOOL_CREATE_NOTE,
        MCP_TOOL_SEARCH_NOTES,
    }
    assert "get_note" not in mcp_tool_names()


@pytest.mark.unit
def test_import_succeeds_without_digivault_root(monkeypatch):
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    sys.modules.pop("digivault.mcp_server", None)
    import digivault.mcp_server as mcp_server

    importlib.reload(mcp_server)
    assert mcp_server.mcp is not None


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "   "])
def test_open_vault_raises_vault_error_without_root(monkeypatch, value):
    monkeypatch.setenv("DIGIVAULT_ROOT", value)
    sys.modules.pop("digivault.mcp_server", None)
    import digivault.mcp_server as mcp_server

    importlib.reload(mcp_server)
    with pytest.raises(VaultError):
        mcp_server._open_vault()


@pytest.mark.unit
def test_open_vault_raises_vault_error_when_unset(monkeypatch):
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    sys.modules.pop("digivault.mcp_server", None)
    import digivault.mcp_server as mcp_server

    importlib.reload(mcp_server)
    with pytest.raises(VaultError):
        mcp_server._open_vault()
