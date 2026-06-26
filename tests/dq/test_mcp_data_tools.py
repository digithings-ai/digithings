from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server  # noqa: E402


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
def test_query_data_tool_registered():
    """#925: external agents can fetch the paper book + market data via query_data."""
    names = _tool_names(create_mcp_server())
    assert "digiquant_query_data" in names, f"missing query_data tool; got {sorted(names)}"


@pytest.mark.unit
def test_query_data_inherits_in_process_allowlist():
    """The MCP wrapper reuses the same table allowlist as the in-process agents.

    The book tables the issue names (positions/nav_history/theses) are readable;
    operator-internal telemetry stays unreadable. ``documents`` is intentionally
    NOT added here — exposing every published doc externally is a separate
    security decision (human gate), out of scope for this wiring.
    """
    from digiquant.olympus.atlas.data.queries import ALLOWED_READ_TABLES

    for table in ("positions", "nav_history", "theses"):
        assert table in ALLOWED_READ_TABLES
    for blocked in ("decision_log", "atlas_run_diagnostics", "documents"):
        assert blocked not in ALLOWED_READ_TABLES
