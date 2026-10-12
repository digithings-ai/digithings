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

from digiquant.data.gloomberb import session_gate
from digiquant.data.gloomberb.session_gate import SessionGateStatus
from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server

from digiquant import mcp_server


def _tool_names(server) -> set[str]:
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


@pytest.fixture(autouse=True)
def authenticated_gloomberb_session():
    """Every test in this module is about SCOPE, not about the Gloomberb
    advertisement gate (#2752), so the whole file runs with the gate held open
    against a stubbed verdict and no probe on the network.

    ``create_mcp_server`` imports ``session_gate_status`` inside its own body,
    on every call, so patching the module attribute here is what the server
    sees. Without this fixture the scope tables below would be read at 85 tools
    instead of 126 and three tests would fail for the wrong reason. The gate
    itself is pinned in ``test_gloomberb_session_gate.py`` and, at registration
    level, by ``test_session_tools_disappear_without_an_authenticated_cookie``
    at the end of this file."""
    session_gate.reset_session_gate_cache()
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        session_gate,
        "session_gate_status",
        lambda *args, **kwargs: SessionGateStatus(True, "ok", "authenticated for the scope tests"),
    )
    try:
        yield
    finally:
        monkey.undo()
        session_gate.reset_session_gate_cache()


READ_TOOLS_EXTRA = {"digiquant_list_coinmetrics_catalog"}

#: The 89 digifetch x Gloomberb tools (#4069, #4110, 130-coverage through Task 8)
#: are read-scope only, default-OFF behind GLOOMBERB_ENABLED.
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
    # `digifetch_congress_trades` is refused under 5 U.S.C. 13107(c)(1)(B)
    # (DIG-1057) and is on no scope — see `digiquant.tool_refusals`.
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
    "digifetch_saved_searches",
    # calculators + compositions (130-coverage Task 2, unattributed derived math)
    "digifetch_options_calculator",
    "digifetch_bond_calculator",
    "digifetch_kelly_sizer",
    "digifetch_dividend_yield",
    "digifetch_fx_cross_rates",
    "digifetch_vix_term_structure",
    # options scenario (130-coverage Task 8: OSA, unattributed derived math)
    "digifetch_options_scenario",
    # portfolio-math compositions (130-coverage Task 3, unattributed derived math)
    "digifetch_compare_performance",
    "digifetch_correlation_matrix",
    "digifetch_relationship_graph",
    "digifetch_relative_valuation",
    "digifetch_fundamental_graph",
    "digifetch_valuation_graph",
    "digifetch_custom_chart",
    "digifetch_market_valuation",
    "digifetch_money_markets",
    "digifetch_rate_path",
    # probe-backed tools (130-coverage Task 5, one per Task 4 GO verdict)
    "digifetch_time_and_sales",
    "digifetch_quote_recap",
    "digifetch_estimate_revisions",
    "digifetch_short_volume",
    "digifetch_hiring",
    "digifetch_central_bank_rates",
    "digifetch_cdx",
    "digifetch_sovereign_cds",
    "digifetch_options_flow",
    "digifetch_cot",
    "digifetch_crypto_markets",
    "digifetch_iv_screen",
    "digifetch_iv_history",
    "digifetch_iv_surface",
    "digifetch_debt_maturities",
    "digifetch_session_movers",
    "digifetch_trending",
    "digifetch_substack",
    "digifetch_ipo_calendar",
    # ToS/direct tools (130-coverage Task 6, venue-direct, unattributed)
    "digifetch_fear_greed",
    "digifetch_polls",
    "digifetch_treasury_auctions",
    "digifetch_market_halts",
    "digifetch_hacker_news",
    # Workspace writes + broker reads + approval-gated orders (130-coverage Task 7)
    "digifetch_portfolio_view",
    "digifetch_watchlist_add",
    "digifetch_watchlist_remove",
    "digifetch_portfolio_add",
    "digifetch_portfolio_remove",
    "digifetch_alert_add",
    "digifetch_alert_list",
    "digifetch_note_add",
    "digifetch_thesis_add",
    "digifetch_view_add",
    "digifetch_broker_positions",
    "digifetch_ibkr_preview_order",
    "digifetch_ibkr_execute_order",
}

#: The 14 LuxAlgo hosted reads (#4779 P0 Library + #4844 edge/trackers).
LUXALGO_TOOLS = {
    "luxalgo_library_search",
    "luxalgo_library_get_concept",
    "luxalgo_library_get_indicator",
    "luxalgo_library_list_concepts",
    "luxalgo_library_list_indicators",
    "luxalgo_library_list_tags",
    "luxalgo_library_list_families",
    "luxalgo_library_get_family",
    "luxalgo_edge_symbols",
    "luxalgo_edge_presets",
    "luxalgo_edge_report",
    "luxalgo_trackers_datasets",
    "luxalgo_trackers_latest",
    "luxalgo_trackers_ticker",
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
def test_read_scope_includes_luxalgo_family():
    assert LUXALGO_TOOLS <= set(READ_SCOPE_TOOLS)
    assert not (LUXALGO_TOOLS & COMPUTE_TOOLS)


@pytest.mark.unit
def test_tool_counts_pin_post_3855_surface():
    # 113 → 112: `digifetch_congress_trades` left the read scope (DIG-1057).
    assert len(READ_SCOPE_TOOLS) == 112
    assert len(COMPUTE_TOOLS) == 14
    # 127 → 126: the refused tool is registered on no scope, full included.
    assert len(_tool_names(create_mcp_server())) == 126


@pytest.mark.unit
def test_congress_trades_is_refused_on_every_scope():
    # DIG-1057 / 5 U.S.C. 13107(c)(1)(B): Counsel's refusal list is enforced at
    # registration, so `scope="full"` cannot reopen the tool.
    from digiquant.tool_refusals import REFUSED_TOOLS

    assert "digifetch_congress_trades" in REFUSED_TOOLS
    assert "digifetch_congress_trades" not in READ_SCOPE_TOOLS
    assert "digifetch_congress_trades" not in _tool_names(create_mcp_server())
    assert "digifetch_congress_trades" not in _tool_names(create_mcp_server(scope="read"))


@pytest.mark.unit
def test_session_tools_disappear_without_an_authenticated_cookie():
    """The gate is the only reason the surface can shrink below the tables.

    With the cookie gone and the real gate running, exactly the
    session/preview/pro tools leave both scopes: nothing else may, or a typo in
    the entitlement set would silently drop the free family too. Counts come
    from ``TOOL_ENTITLEMENTS`` rather than from a literal, so this follows the
    vocabulary instead of restating it.
    """
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    session_gate.reset_session_gate_cache()
    monkey = pytest.MonkeyPatch()
    monkey.delenv("GLOOMBERB_SESSION_COOKIE", raising=False)
    monkey.setattr(
        session_gate,
        "session_gate_status",
        lambda *args, **kwargs: SessionGateStatus(
            False, "no_secret", "GLOOMBERB_SESSION_COOKIE is not set"
        ),
    )
    try:
        full = _tool_names(create_mcp_server())
        read = _tool_names(create_mcp_server(scope="read"))
    finally:
        monkey.undo()
        session_gate.reset_session_gate_cache()

    gated = {
        name for name, tier in TOOL_ENTITLEMENTS.items() if tier in {"session", "preview", "pro"}
    }
    free = {name for name, tier in TOOL_ENTITLEMENTS.items() if tier == "free"}

    assert gated, "the gate would have nothing to hide"
    assert not (full & gated), sorted(full & gated)[:5]
    assert not (read & gated), sorted(read & gated)[:5]
    # The free family is untouched by the gate, on either scope.
    assert free & full
    assert len(full) == 126 - len(gated)
