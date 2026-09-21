from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server


def _tool_names(server) -> set[str]:
    # Prefer a public accessor; fall back to FastMCP's internal manager across versions.
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


@pytest.mark.unit
def test_data_tools_registered():
    names = _tool_names(create_mcp_server())
    assert "digiquant_get_price_technicals" in names, f"missing data tool; got {sorted(names)}"
    assert "digiquant_get_macro_series" in names, f"missing data tool; got {sorted(names)}"


@pytest.mark.unit
def test_query_research_tool_registered():
    """#4436: external agents search research output + the paper book by filters."""
    names = _tool_names(create_mcp_server())
    assert "digiquant_query_research" in names, f"missing query_research tool; got {sorted(names)}"


@pytest.mark.unit
def test_query_data_tool_removed():
    """The generic raw-table reader was folded into query_research (#4436)."""
    names = _tool_names(create_mcp_server())
    assert "digiquant_query_data" not in names


@pytest.mark.unit
def test_query_research_documents_house_scope():
    """The MCP wrapper reads the house book; documents resolve through house scope."""
    server = create_mcp_server()
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    qr = next(t for t in tools if t.name == "digiquant_query_research")
    assert "r2" in qr.description.lower()
    assert "include_prior" in qr.description.lower()
