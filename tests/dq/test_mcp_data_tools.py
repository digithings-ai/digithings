from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server  # noqa: E402


@pytest.mark.unit
def test_data_tools_registered():
    server = create_mcp_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    assert "digiquant_get_price_technicals" in names
    assert "digiquant_get_macro_series" in names
