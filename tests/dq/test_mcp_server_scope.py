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


READ_TOOLS_EXTRA = {"digiquant_list_coinmetrics_catalog"}

#: The 33 digifetch x Gloomberb enrichment reads (#4069, #4110) are read-scope
#: only, default-ON behind GLOOMBERB_ENABLED.
DIGIFETCH_TOOLS = {
    "digifetch_quote",
    "digifetch_quotes_batch",
    "digifetch_price_history",
    "digifetch_ticker_financials",
    "digifetch_options_chain",
    "digifetch_sec_filings",
    "digifetch_holders",
    "digifetch_analyst_research",
    "digifetch_corporate_actions",
    "digifetch_earnings_calendar",
    "digifetch_exchange_rate",
    "digifetch_search",
    "digifetch_news",
    "digifetch_econ_calendar",
    "digifetch_econ_series",
    "digifetch_yield_curve",
    "digifetch_cds",
    "digifetch_research_search",
    "digifetch_congress_trades",
    "digifetch_transcripts",
    "digifetch_statements",
    "digifetch_ticker_tweets",
    "digifetch_tweet_search",
    "digifetch_venues",
    "digifetch_screener",
    "digifetch_13f_funds",
    "digifetch_13f_holdings",
    "digifetch_shiller",
    "digifetch_proxy_statements",
    "digifetch_filing_events",
    "digifetch_risk_reports",
    "digifetch_short_interest",
    "digifetch_equity_diagnostic",
}

COMPUTE_TOOLS = {
    "digiquant_run_backtest",
    "digiquant_run_optimize",
    "digiquant_export",
    "digiquant_run_pipeline",
    "digiquant_fetch_coinbase_ohlcv",
    "digiquant_fit_btc_power_law",
    "digiquant_build_sdca_risk_index",
    "digiquant_fetch_bitview_series",
    "digiquant_fetch_bgeometrics_series",
    "digiquant_fetch_coinmetrics_series",
    "digiquant_fit_sdca_weights",
    "digiquant_generate_slapper_tearsheet",
    "digiquant_validate_slapper_vs_tradingview",
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
    assert "digiquant_get_trade_levels" in READ_SCOPE_TOOLS
    assert "digiquant_get_trade_levels" not in COMPUTE_TOOLS


@pytest.mark.unit
def test_read_scope_includes_digifetch_family():
    assert DIGIFETCH_TOOLS <= set(READ_SCOPE_TOOLS)
    assert not (DIGIFETCH_TOOLS & COMPUTE_TOOLS)


@pytest.mark.unit
def test_tool_counts_pin_post_3855_surface():
    assert len(READ_SCOPE_TOOLS) == 43
    assert len(COMPUTE_TOOLS) == 14
    assert len(_tool_names(create_mcp_server())) == 57
