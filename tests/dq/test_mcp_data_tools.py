from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server  # noqa: E402


@pytest.mark.unit
def test_data_tools_registered():
    server = create_mcp_server()
    # Prefer a public accessor; fall back to FastMCP's internal manager across versions.
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert "digiquant_get_price_technicals" in names, f"missing data tool; got {sorted(names)}"
    assert "digiquant_get_macro_series" in names, f"missing data tool; got {sorted(names)}"
