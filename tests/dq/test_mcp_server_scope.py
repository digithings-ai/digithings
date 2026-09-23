"""MCP server construction: scope filtering + bind settings (#3854 scope work).

``scope="read"`` is the dashboard-chat surface (latest/historical runs,
documents/research, prices, technicals, house book, gate reads). Compute and
mutate tools (backtest / optimize / pipeline / export / fits / fetches /
policy-replay runs) stay on the default ``scope="full"`` surface only.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server

from digiquant import mcp_server


def _tool_names(server) -> set[str]:
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


READ_TOOLS_EXTRA = {"coinmetrics_list_catalog"}

#: The 33 digifetch x Gloomberb enrichment reads (#4069, #4110) are read-scope
#: only, default-ON behind GLOOMBERB_ENABLED.
DIGIFETCH_TOOLS = {
    "gloomberb_get_quote",
    "gloomberb_get_quotes_batch",
    "gloomberb_get_price_history",
    "gloomberb_get_ticker_financials",
    "gloomberb_get_options_chain",
    "gloomberb_get_sec_filings",
    "gloomberb_get_holders",
    "gloomberb_get_analyst_research",
    "gloomberb_get_corporate_actions",
    "yahoo_get_earnings_calendar",
    "gloomberb_get_exchange_rate",
    "gloomberb_search",
    "gloomberb_get_news",
    "gloomberb_get_econ_calendar",
    "gloomberb_get_econ_series",
    "gloomberb_get_yield_curve",
    "gloomberb_get_cds",
    "gloomberb_search_research",
    "gloomberb_get_congress_trades",
    "gloomberb_get_transcripts",
    "gloomberb_get_statements",
    "gloomberb_get_ticker_tweets",
    "gloomberb_search_tweet",
    "gloomberb_list_venues",
    "gloomberb_run_screener",
    "gloomberb_get_13f_funds",
    "gloomberb_get_13f_holdings",
    "gloomberb_get_shiller",
    "gloomberb_get_proxy_statements",
    "gloomberb_get_filing_events",
    "gloomberb_get_risk_reports",
    "gloomberb_get_short_interest",
    "gloomberb_get_equity_diagnostic",
    "gloomberb_list_saved_searches",
}

COMPUTE_TOOLS = {
    "run_backtest",
    "run_optimize",
    "export",
    "run_pipeline",
    "coinbase_fetch_ohlcv",
    "fit_btc_power_law",
    "build_sdca_risk_index",
    "bitview_fetch_series",
    "bgeometrics_fetch_series",
    "coinmetrics_fetch_series",
    "fit_sdca_weights",
    "generate_slapper_tearsheet",
    "validate_slapper_vs_tradingview",
    "dashboard_run_policy_replay",
}


@pytest.mark.unit
def test_full_scope_is_default_and_complete():
    names = _tool_names(create_mcp_server())
    assert READ_SCOPE_TOOLS <= names
    assert COMPUTE_TOOLS <= names
    assert names == READ_SCOPE_TOOLS | COMPUTE_TOOLS


@pytest.mark.unit
def test_read_scope_exposes_only_read_tools():
    names = _tool_names(create_mcp_server(scope="read"))
    assert names == set(READ_SCOPE_TOOLS)
    assert not (names & COMPUTE_TOOLS)


@pytest.mark.unit
def test_invalid_scope_raises():
    with pytest.raises(ValueError, match="scope"):
        create_mcp_server(scope="everything")


@pytest.mark.unit
def test_create_mcp_server_honours_bind_settings():
    server = create_mcp_server(host="0.0.0.0", port=8123)
    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 8123


@pytest.mark.unit
def test_run_mcp_passes_bind_via_constructor_not_run():
    """Installed mcp's run() takes (transport, mount_path) only — host/port
    belong on the server. run_mcp must not forward them to run()."""
    with patch.object(mcp_server, "create_mcp_server") as factory:
        mcp_server.run_mcp(host="0.0.0.0", port=8123)
    factory.assert_called_once_with(scope="full", host="0.0.0.0", port=8123)
    factory.return_value.run.assert_called_once_with(transport="streamable-http")


@pytest.mark.unit
def test_run_mcp_honours_digiquant_mcp_host_env(monkeypatch):
    """Direct run_mcp() must honor DIGIQUANT_MCP_HOST (sibling bind-fallback)."""
    monkeypatch.setenv("DIGIQUANT_MCP_HOST", "0.0.0.0")
    with patch.object(mcp_server, "create_mcp_server") as factory:
        mcp_server.run_mcp(host=None)
    factory.assert_called_once_with(scope="full", host="0.0.0.0", port=8767)
    factory.return_value.run.assert_called_once_with(transport="streamable-http")


@pytest.mark.unit
def test_run_mcp_explicit_host_wins_over_env(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MCP_HOST", "0.0.0.0")
    with patch.object(mcp_server, "create_mcp_server") as factory:
        mcp_server.run_mcp(host="127.0.0.1", port=8123)
    factory.assert_called_once_with(scope="full", host="127.0.0.1", port=8123)


@pytest.mark.unit
def test_read_scope_includes_coinmetrics_catalog():
    assert READ_TOOLS_EXTRA <= set(READ_SCOPE_TOOLS)


@pytest.mark.unit
def test_read_scope_includes_trade_levels():
    # Track E (#137): causal levels are a pure read/compute surface.
    assert "get_trade_levels" in READ_SCOPE_TOOLS
    assert "get_trade_levels" not in COMPUTE_TOOLS


@pytest.mark.unit
def test_read_scope_includes_digifetch_family():
    assert DIGIFETCH_TOOLS <= set(READ_SCOPE_TOOLS)
    assert not (DIGIFETCH_TOOLS & COMPUTE_TOOLS)


@pytest.mark.unit
def test_tool_counts_pin_post_3855_surface():
    assert len(READ_SCOPE_TOOLS) == 44
    assert len(COMPUTE_TOOLS) == 14
    assert len(_tool_names(create_mcp_server())) == 58
