"""In-process ``digifetch_*`` tool surface for pipeline agents (#4146).

The 33 digifetch x Gloomberb tools (#4110) were MCP-registration + orchestrator
manifest schemas only: the research analysts and portfolio manager could not
call them while reasoning. This module gives them an in-process surface:

* :data:`DIGIFETCH_TOOLS` — the OpenAI function schemas, *generated* from
  :func:`digiquant.orchestrator_tools.build_orchestrator_tool_manifest` (filtered
  to the names declared in :data:`TOOL_ENTITLEMENTS`), so the MCP, manifest, and
  in-process surfaces cannot drift.
* :data:`EQUITY_TOOLS` / :data:`MACRO_TOOLS` / :data:`PM_TOOLS` — curated
  per-phase subsets (``<= 16`` names each; prompt budget, not capability).
* :func:`available_digifetch_tools` — subset -> schemas, dropping
  ``session`` / ``pro`` / ``preview`` tools when ``GLOOMBERB_SESSION_COOKIE`` is
  absent (the same zero-HTTP gate the MCP tools apply; without a cookie those
  tools would only return ``auth_required``).
* :func:`build_digifetch_tool_dispatcher` — ``(name, args) -> {"content": <json
  str>, "ok": bool}`` routed
  through the shared :class:`GloomberbClient` and serialized with the §7
  attribution envelope.

The client factory (:func:`build_gloomberb_client`) and envelope serializer
(:func:`gloomberb_envelope_json`) live here too, so the MCP surface and the
pipeline dispatcher share one pacing/cache/circuit-breaker client per env pair
(``mcp_server`` imports them; #4146 moved them out of the server module).

Gloomberb is **enrichment only** — 15-minute free-tier delay, rate limits, and
the §5.2 caps disqualify it as a pipeline primary. The tools are read-scope and
every payload keeps the "Sourced from Gloomberb" attribution + the
``term.gloom.sh/?ticker=`` deep link where one listing is addressed.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from typing import (  # score:allow untyped any — duck-typed client + heterogeneous tool payloads
    Any,
    Callable,
    NamedTuple,
)

from pydantic import BaseModel, ValidationError

from .client import (
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    SUBSTACK_SESSION_COOKIE_ENV,
    gloomberb_enabled,
)
from .entitlements import TOOL_ENTITLEMENTS
from .models import (
    AlertAddInput,
    AlertListInput,
    AnalystResearchInput,
    BondCalcInput,
    BrokerPositionsInput,
    CdsInput,
    CdxInput,
    CentralBankRatesInput,
    ComparePerfInput,
    CongressTradesInput,
    CorporateActionsInput,
    CorrMatrixInput,
    CotInput,
    CryptoMarketsInput,
    CustomChartInput,
    DebtMaturitiesInput,
    DigifetchEnvelope,
    DigifetchError,
    DividendYieldInput,
    EarningsCalendarInput,
    EconCalendarInput,
    EconSeriesInput,
    EquityDiagnosticInput,
    EstimateRevisionsInput,
    ExchangeRateInput,
    FearGreedInput,
    FilingEventsInput,
    FundGraphInput,
    FxMatrixInput,
    HackerNewsInput,
    HiringInput,
    HoldersInput,
    IbkrExecuteOrderInput,
    IbkrPreviewOrderInput,
    IpoCalendarInput,
    IvHistoryInput,
    IvScreenInput,
    IvSurfaceInput,
    KellyInput,
    MarketHaltsInput,
    MarketValInput,
    MoneyMarketsInput,
    NewsInput,
    NoteAddInput,
    OptionsCalcInput,
    OptionsChainInput,
    OptionsFlowInput,
    PollsInput,
    PortfolioAddInput,
    PortfolioRemoveInput,
    PortfolioViewInput,
    PredictionMarketsInput,
    PriceHistoryInput,
    ProxyStatementsInput,
    QuoteInput,
    QuoteRecapInput,
    QuotesBatchInput,
    RatePathInput,
    RelGraphInput,
    RelValInput,
    ResearchSearchInput,
    RiskReportsInput,
    SavedSearchesInput,
    ScreenerInput,
    SearchInput,
    SecFilingsInput,
    SessionMoversInput,
    ShillerInput,
    ShortInterestInput,
    ShortVolumeInput,
    SovrInput,
    StatementsInput,
    SubstackInput,
    ThesisAddInput,
    ThirteenFFundsInput,
    ThirteenFHoldingsInput,
    TickerFinancialsInput,
    TickerTweetsInput,
    TimeAndSalesInput,
    TranscriptsInput,
    TreasuryAuctionsInput,
    TrendingInput,
    TweetSearchInput,
    ValGraphInput,
    VenuesInput,
    ViewAddInput,
    VixTermInput,
    WatchlistAddInput,
    WatchlistRemoveInput,
    YieldCurveInput,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DIGIFETCH_TOOLS",
    "EQUITY_TOOLS",
    "MACRO_TOOLS",
    "PM_TOOLS",
    "DigifetchDispatch",
    "DIGIFETCH_DISPATCH",
    "available_digifetch_tools",
    "build_digifetch_tool_dispatcher",
    "build_gloomberb_client",
    "close_gloomberb_client",
    "gloomberb_envelope_json",
]

# ── shared client factory + envelope serializer (moved from mcp_server, #4146) ──
#
# One lazily-built ``GloomberbClient`` per (kill switch, session cookie,
# substack cookie) env triple. Keyed by the raw env values so an
# operator/test env change gets a fresh client without a process restart; the default (unset) pair is the anonymous,
# default-ON client. Only one client is kept alive: when the env pair changes,
# the replaced client is closed so its transport is not leaked. The lock
# serializes the read/close/replace dance — LangGraph runs parallel nodes, and
# they all funnel through this one cached client.

_gloomberb_clients: dict[tuple[str, str, str], Any] = {}
_gloomberb_clients_lock = threading.Lock()


def close_gloomberb_client(client: Any) -> None:
    """Best-effort close for a client being replaced (never mask the new one)."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:  # closing is cleanup; an error must not break a tool call
        pass


def build_gloomberb_client() -> Any:
    """Build/cache the Gloomberb client from env (patchable seam for tests)."""
    from digiquant.data.gloomberb import GloomberbClient

    key = (
        os.environ.get(GLOOMBERB_ENABLED_ENV, ""),
        os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, ""),
        os.environ.get(SUBSTACK_SESSION_COOKIE_ENV, ""),
    )
    with _gloomberb_clients_lock:
        client = _gloomberb_clients.get(key)
        if client is not None:
            return client
        client = GloomberbClient()
        for stale in _gloomberb_clients.values():
            close_gloomberb_client(stale)
        _gloomberb_clients.clear()
        _gloomberb_clients[key] = client
        return client


def gloomberb_envelope_json(
    envelope: Any, *, symbol: str | None = None, attributed: bool = True
) -> str:
    """Serialize a ``DigifetchEnvelope`` with §7 attribution + deep link.

    ``symbol`` adds a ``term.gloom.sh/?ticker=`` source link. ``attributed``
    is False for the Yahoo-backed earnings calendar, which is not Gloomberb-
    sourced and must not claim the attribution.
    """
    payload = envelope.model_dump(mode="json")
    if attributed:
        from digiquant.data.gloomberb import attribution_fields

        payload.update(attribution_fields(symbol))
    return json.dumps(payload, indent=2, default=str)


# ── curated per-phase subsets (#4146) ─────────────────────────────────────────
#
# Not all 70 tools everywhere (prompt budget): the equity/sector research
# phases get company facts + analyst views, the macro phase gets rates/credit/
# long-run valuation, and the portfolio PM (analyst + direction) gets a
# PM-fit mix of quotes/news/analyst views plus macro context. Every name is
# declared in ``TOOL_ENTITLEMENTS``; ``available_digifetch_tools`` drops the
# session-/preview-/pro-gated ones when no Gloomberb cookie is configured
# (and the venue_session reader when no Substack cookie is configured).
#
# deliberation stays digifetch-free: it is research-tools-only by policy
# (#2908, no generic web search in the deliberation loop), and its evidence
# path is the evidence bundle + amendment flow, not a new market-data family.
# The legacy Phase 7D PM path (``phase7d_pm``, no live graph caller) is also
# unwired; direction is the portfolio direction phase.

EQUITY_TOOLS: tuple[str, ...] = (
    "digifetch_quote",
    "digifetch_quotes_batch",
    "digifetch_price_history",
    "digifetch_ticker_financials",
    "digifetch_analyst_research",
    "digifetch_corporate_actions",
    "digifetch_earnings_calendar",
    "digifetch_sec_filings",
    "digifetch_holders",
    "digifetch_news",
    "digifetch_ticker_tweets",
    "digifetch_short_interest",
    "digifetch_statements",
    "digifetch_risk_reports",
    "digifetch_filing_events",
    "digifetch_research_search",
)

MACRO_TOOLS: tuple[str, ...] = (
    "digifetch_econ_calendar",
    "digifetch_econ_series",
    "digifetch_yield_curve",
    "digifetch_cds",
    "digifetch_shiller",
    "digifetch_news",
    "digifetch_research_search",
    "digifetch_prediction_markets",
    # portfolio-math compositions (130-coverage Task 3): valuation + funding
    # context for the macro phase. compare_performance / correlation_matrix /
    # relative_valuation stay MCP-only: EQUITY_TOOLS is at its 16-name prompt
    # budget and evictions need owner sign-off.
    "digifetch_market_valuation",
    "digifetch_money_markets",
    "digifetch_rate_path",
    # probe-backed tools (130-coverage Task 5): rates/credit/positioning core
    # for the macro phase.
    "digifetch_central_bank_rates",
    "digifetch_cdx",
    "digifetch_sovereign_cds",
    "digifetch_cot",
    # ToS/direct tools (130-coverage Task 6): Treasury auction results are
    # rates core for the macro phase (16/16 — at cap; polls and hacker_news
    # stay MCP-only, see below).
    "digifetch_treasury_auctions",
)
# ``digifetch_congress_trades`` stays MCP-only for now (#4146 review F9): its
# upstream OCR dependency answers HTTP 500, so a pipeline tool could only return
# a typed upstream_error. Re-add to MACRO_TOOLS when upstream recovers.

PM_TOOLS: tuple[str, ...] = (
    "digifetch_quote",
    "digifetch_quotes_batch",
    "digifetch_news",
    "digifetch_econ_calendar",
    "digifetch_econ_series",
    "digifetch_yield_curve",
    "digifetch_analyst_research",
    "digifetch_research_search",
    "digifetch_corporate_actions",
    "digifetch_earnings_calendar",
    "digifetch_shiller",
    "digifetch_cds",
    # probe-backed tools (130-coverage Task 5): market-wide session movers +
    # the IPO calendar.
    "digifetch_session_movers",
    "digifetch_ipo_calendar",
    # ToS/direct tools (130-coverage Task 6): market-wide sentiment gauge +
    # trade-halt risk for the PM direction read (16/16 — at cap).
    "digifetch_fear_greed",
    "digifetch_market_halts",
)
# ``digifetch_polls`` and ``digifetch_hacker_news`` stay MCP-only for now
# (130-coverage Task 6): EQUITY is at its 16-name cap and MACRO/PM filled to
# 16 with the rates/sentiment/risk picks above. Both remain discoverable via
# MCP and the full manifest; promote into a subset only with an eviction the
# owner signs off.


# ── schemas, generated from the orchestrator manifest builders ────────────────


def _digifetch_manifest_tools() -> list[dict[str, Any]]:
    """The manifest entries whose names carry a digifetch entitlement.

    Generated rather than hand-copied so the MCP, manifest, and in-process
    schemas are the same dicts (descriptions carry the entitlement note, and
    the top-level ``entitlement`` key is preserved as on the manifest surface).
    """
    from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

    return [
        tool
        for tool in build_orchestrator_tool_manifest()
        if tool["function"]["name"] in TOOL_ENTITLEMENTS
    ]


#: Every digifetch tool schema, in manifest order (names = TOOL_ENTITLEMENTS keys).
DIGIFETCH_TOOLS: list[dict[str, Any]] = _digifetch_manifest_tools()

_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {
    tool["function"]["name"]: tool for tool in DIGIFETCH_TOOLS
}

_DEFAULT_TOOL_NAMES: tuple[str, ...] = tuple(t["function"]["name"] for t in DIGIFETCH_TOOLS)


def _session_cookie_present() -> bool:
    return bool(os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip())


def _substack_cookie_present() -> bool:
    return bool(os.environ.get(SUBSTACK_SESSION_COOKIE_ENV, "").strip())


def available_digifetch_tools(subset: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Schemas for *subset* (default: every digifetch tool), runtime-gated.

    Unlike the MCP surface — which registers gated tools and answers each call
    with the typed ``auth_required`` / ``pro_required`` / disabled envelope —
    this in-process surface filters the list so a pipeline LLM is never handed
    a tool that can only error:

    * the whole family is dropped when ``GLOOMBERB_ENABLED`` disables it
      (default ON; a typo fails closed), because every call would return the
      typed "disabled by kill switch" ``upstream_error``; and
    * ``session`` / ``preview`` / ``pro`` tools are dropped when
      ``GLOOMBERB_SESSION_COOKIE`` is unset, because they would return the
      typed ``auth_required`` / ``pro_required`` error with no request (#4099);
    * the ``venue_session`` reader (``digifetch_substack``) is dropped when
      ``SUBSTACK_SESSION_COOKIE`` is unset, for the same reason.

    An unknown name is a wiring bug and raises ``KeyError``.
    """
    if not gloomberb_enabled():
        return []
    names = _DEFAULT_TOOL_NAMES if subset is None else subset
    has_session = _session_cookie_present()
    has_substack = _substack_cookie_present()
    schemas: list[dict[str, Any]] = []
    for name in names:
        entitlement = TOOL_ENTITLEMENTS[name]
        if entitlement == "free":
            pass
        elif entitlement == "venue_session":
            if not has_substack:
                continue
        elif not has_session:
            continue
        schemas.append(_SCHEMA_BY_NAME[name])
    return schemas


# ── dispatcher ────────────────────────────────────────────────────────────────


class DigifetchDispatch(NamedTuple):
    """One tool's dispatch row: args model, client method, §7 link/attribution."""

    input_model: type[BaseModel]
    client_method: str
    symbol_field: str | None = None
    attributed: bool = True


#: ``name -> dispatch`` for every digifetch tool. The row mirrors the MCP
#: wrapper for that tool (same Pydantic input model, same client method, same
#: deep-link/attribution choice); the parity test pins both directions.
DIGIFETCH_DISPATCH: dict[str, DigifetchDispatch] = {
    "digifetch_quote": DigifetchDispatch(QuoteInput, "quote", "symbol"),
    "digifetch_quotes_batch": DigifetchDispatch(QuotesBatchInput, "quotes_batch"),
    "digifetch_price_history": DigifetchDispatch(PriceHistoryInput, "price_history", "symbol"),
    "digifetch_ticker_financials": DigifetchDispatch(
        TickerFinancialsInput, "ticker_financials", "symbol"
    ),
    "digifetch_options_chain": DigifetchDispatch(OptionsChainInput, "options_chain", "symbol"),
    "digifetch_sec_filings": DigifetchDispatch(SecFilingsInput, "sec_filings", "ticker"),
    "digifetch_holders": DigifetchDispatch(HoldersInput, "holders", "symbol"),
    "digifetch_analyst_research": DigifetchDispatch(
        AnalystResearchInput, "analyst_research", "symbol"
    ),
    "digifetch_corporate_actions": DigifetchDispatch(
        CorporateActionsInput, "corporate_actions", "symbol"
    ),
    "digifetch_earnings_calendar": DigifetchDispatch(
        EarningsCalendarInput, "earnings_calendar", attributed=False
    ),
    "digifetch_exchange_rate": DigifetchDispatch(ExchangeRateInput, "exchange_rate"),
    "digifetch_search": DigifetchDispatch(SearchInput, "search"),
    "digifetch_news": DigifetchDispatch(NewsInput, "news", "ticker"),
    "digifetch_econ_calendar": DigifetchDispatch(EconCalendarInput, "econ_calendar"),
    "digifetch_econ_series": DigifetchDispatch(EconSeriesInput, "econ_series"),
    "digifetch_yield_curve": DigifetchDispatch(YieldCurveInput, "yield_curve"),
    "digifetch_cds": DigifetchDispatch(CdsInput, "cds"),
    "digifetch_research_search": DigifetchDispatch(ResearchSearchInput, "research_search"),
    "digifetch_congress_trades": DigifetchDispatch(CongressTradesInput, "congress_trades"),
    "digifetch_transcripts": DigifetchDispatch(TranscriptsInput, "transcripts", "ticker"),
    "digifetch_statements": DigifetchDispatch(StatementsInput, "statements", "symbol"),
    "digifetch_ticker_tweets": DigifetchDispatch(TickerTweetsInput, "ticker_tweets", "ticker"),
    "digifetch_tweet_search": DigifetchDispatch(TweetSearchInput, "tweet_search"),
    "digifetch_venues": DigifetchDispatch(VenuesInput, "venues"),
    "digifetch_saved_searches": DigifetchDispatch(SavedSearchesInput, "saved_searches"),
    "digifetch_screener": DigifetchDispatch(ScreenerInput, "screener"),
    "digifetch_13f_funds": DigifetchDispatch(ThirteenFFundsInput, "thirteen_f_funds"),
    "digifetch_13f_holdings": DigifetchDispatch(ThirteenFHoldingsInput, "thirteen_f_holdings"),
    "digifetch_shiller": DigifetchDispatch(ShillerInput, "shiller"),
    "digifetch_proxy_statements": DigifetchDispatch(
        ProxyStatementsInput, "proxy_statements", "ticker"
    ),
    "digifetch_filing_events": DigifetchDispatch(FilingEventsInput, "filing_events", "ticker"),
    "digifetch_risk_reports": DigifetchDispatch(RiskReportsInput, "risk_reports", "ticker"),
    "digifetch_short_interest": DigifetchDispatch(ShortInterestInput, "short_interest", "symbol"),
    "digifetch_equity_diagnostic": DigifetchDispatch(
        EquityDiagnosticInput, "equity_diagnostic", "symbol"
    ),
    "digifetch_prediction_markets": DigifetchDispatch(
        PredictionMarketsInput, "prediction_markets", attributed=False
    ),
    # Calculators + compositions (130-coverage Task 2): derived math, never
    # Cloud-sourced, so no deep link and no attribution.
    "digifetch_options_calculator": DigifetchDispatch(
        OptionsCalcInput, "options_calculator", attributed=False
    ),
    "digifetch_bond_calculator": DigifetchDispatch(
        BondCalcInput, "bond_calculator", attributed=False
    ),
    "digifetch_kelly_sizer": DigifetchDispatch(KellyInput, "kelly_sizer", attributed=False),
    "digifetch_dividend_yield": DigifetchDispatch(
        DividendYieldInput, "dividend_yield", attributed=False
    ),
    "digifetch_fx_cross_rates": DigifetchDispatch(
        FxMatrixInput, "fx_cross_rates", attributed=False
    ),
    "digifetch_vix_term_structure": DigifetchDispatch(
        VixTermInput, "vix_term_structure", attributed=False
    ),
    # Portfolio-math compositions (130-coverage Task 3): derived math over
    # existing reads, never Cloud-sourced, so no deep link and no attribution.
    "digifetch_compare_performance": DigifetchDispatch(
        ComparePerfInput, "compare_performance", attributed=False
    ),
    "digifetch_correlation_matrix": DigifetchDispatch(
        CorrMatrixInput, "correlation_matrix", attributed=False
    ),
    "digifetch_relationship_graph": DigifetchDispatch(
        RelGraphInput, "relationship_graph", attributed=False
    ),
    "digifetch_relative_valuation": DigifetchDispatch(
        RelValInput, "relative_valuation", attributed=False
    ),
    "digifetch_fundamental_graph": DigifetchDispatch(
        FundGraphInput, "fundamental_graph", attributed=False
    ),
    "digifetch_valuation_graph": DigifetchDispatch(
        ValGraphInput, "valuation_graph", attributed=False
    ),
    "digifetch_custom_chart": DigifetchDispatch(CustomChartInput, "custom_chart", attributed=False),
    "digifetch_market_valuation": DigifetchDispatch(
        MarketValInput, "market_valuation", attributed=False
    ),
    "digifetch_money_markets": DigifetchDispatch(
        MoneyMarketsInput, "money_markets", attributed=False
    ),
    "digifetch_rate_path": DigifetchDispatch(RatePathInput, "rate_path", attributed=False),
    # Probe-backed tools (130-coverage Task 5): one row per Task 4 GO verdict.
    # The rows mirror the MCP wrappers (same input model, client method, and
    # deep-link/attribution choice); the parity test pins both directions.
    "digifetch_time_and_sales": DigifetchDispatch(TimeAndSalesInput, "time_and_sales", "symbol"),
    "digifetch_quote_recap": DigifetchDispatch(QuoteRecapInput, "quote_recap", "symbol"),
    "digifetch_estimate_revisions": DigifetchDispatch(
        EstimateRevisionsInput, "estimate_revisions", "symbol"
    ),
    "digifetch_short_volume": DigifetchDispatch(ShortVolumeInput, "short_volume", "symbol"),
    "digifetch_hiring": DigifetchDispatch(HiringInput, "hiring", "ticker"),
    "digifetch_central_bank_rates": DigifetchDispatch(CentralBankRatesInput, "central_bank_rates"),
    "digifetch_cdx": DigifetchDispatch(CdxInput, "cdx"),
    "digifetch_sovereign_cds": DigifetchDispatch(SovrInput, "sovereign_cds"),
    "digifetch_options_flow": DigifetchDispatch(OptionsFlowInput, "options_flow"),
    "digifetch_cot": DigifetchDispatch(CotInput, "cot"),
    "digifetch_crypto_markets": DigifetchDispatch(CryptoMarketsInput, "crypto_markets"),
    "digifetch_iv_screen": DigifetchDispatch(IvScreenInput, "iv_screen"),
    "digifetch_iv_history": DigifetchDispatch(IvHistoryInput, "iv_history", "symbol"),
    "digifetch_iv_surface": DigifetchDispatch(IvSurfaceInput, "iv_surface", "symbol"),
    "digifetch_debt_maturities": DigifetchDispatch(
        DebtMaturitiesInput, "debt_maturities", "symbol"
    ),
    "digifetch_session_movers": DigifetchDispatch(SessionMoversInput, "session_movers"),
    # Venue-direct (prediction-markets precedent): free, unattributed, per-row
    # venue URLs, no Gloomberb claims.
    "digifetch_trending": DigifetchDispatch(TrendingInput, "trending", attributed=False),
    "digifetch_substack": DigifetchDispatch(SubstackInput, "substack", attributed=False),
    "digifetch_ipo_calendar": DigifetchDispatch(IpoCalendarInput, "ipo_calendar"),
    # ToS/direct tools (130-coverage Task 6): venue-direct, free,
    # unattributed, per-row venue URLs, no Gloomberb claims.
    "digifetch_fear_greed": DigifetchDispatch(FearGreedInput, "fear_greed", attributed=False),
    "digifetch_polls": DigifetchDispatch(PollsInput, "polls", attributed=False),
    "digifetch_treasury_auctions": DigifetchDispatch(
        TreasuryAuctionsInput, "treasury_auctions", attributed=False
    ),
    "digifetch_market_halts": DigifetchDispatch(MarketHaltsInput, "market_halts", attributed=False),
    "digifetch_hacker_news": DigifetchDispatch(HackerNewsInput, "hacker_news", attributed=False),
    # Workspace writes + broker reads + approval-gated orders (130-coverage
    # Task 7): no personal Cloud write route is verified, so the payloads carry
    # no Gloomberb-sourced data and stay unattributed (like the calculators and
    # venue-direct tools); the descriptions still name the Cloud account surface.
    "digifetch_portfolio_view": DigifetchDispatch(
        PortfolioViewInput, "portfolio_view", attributed=False
    ),
    "digifetch_watchlist_add": DigifetchDispatch(
        WatchlistAddInput, "watchlist_add", "symbol", attributed=False
    ),
    "digifetch_watchlist_remove": DigifetchDispatch(
        WatchlistRemoveInput, "watchlist_remove", "symbol", attributed=False
    ),
    "digifetch_portfolio_add": DigifetchDispatch(
        PortfolioAddInput, "portfolio_add", "symbol", attributed=False
    ),
    "digifetch_portfolio_remove": DigifetchDispatch(
        PortfolioRemoveInput, "portfolio_remove", "symbol", attributed=False
    ),
    "digifetch_alert_add": DigifetchDispatch(
        AlertAddInput, "alert_add", "symbol", attributed=False
    ),
    "digifetch_alert_list": DigifetchDispatch(AlertListInput, "alert_list", attributed=False),
    "digifetch_note_add": DigifetchDispatch(NoteAddInput, "note_add", "symbol", attributed=False),
    "digifetch_thesis_add": DigifetchDispatch(
        ThesisAddInput, "thesis_add", "ticker", attributed=False
    ),
    "digifetch_view_add": DigifetchDispatch(ViewAddInput, "view_add", attributed=False),
    "digifetch_broker_positions": DigifetchDispatch(
        BrokerPositionsInput, "broker_positions", attributed=False
    ),
    "digifetch_ibkr_preview_order": DigifetchDispatch(
        IbkrPreviewOrderInput, "ibkr_preview_order", "symbol", attributed=False
    ),
    "digifetch_ibkr_execute_order": DigifetchDispatch(
        IbkrExecuteOrderInput, "ibkr_execute_order", "symbol", attributed=False
    ),
}


def _symbol_for(spec: DigifetchDispatch, request: Any) -> str | None:
    """Best-effort §7 deep-link symbol from the typed request, else the raw args.

    On a Pydantic ``ValidationError`` the dispatcher falls back to the raw
    payload, so the error envelope keeps the ``term.gloom.sh/?ticker=`` link the
    MCP wrapper would have emitted for the same call (#4146 review F3).
    """
    if not spec.symbol_field:
        return None
    if isinstance(request, spec.input_model):
        value = getattr(request, spec.symbol_field, None)
    elif isinstance(request, Mapping):
        value = request.get(spec.symbol_field)
    else:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def build_digifetch_tool_dispatcher(
    client: Any | None = None,
) -> Callable[[str, dict[str, Any]], str | dict[str, Any]]:
    """Return an ``execute_tool(name, args) -> result`` bound to a client.

    Each result is ``{"content": <attribution-enveloped JSON string>, "ok": bool}``
    (#4556): ``content`` is what the model reads, and ``ok`` is the honest
    success flag the tool-call telemetry records. The upstream is a live read, so
    a wire 5xx that survives the client's own retries is a failed tool call even
    though the dispatcher, by contract, still returns a string instead of raising.

    ``client`` is the patchable seam tests inject (MockTransport-backed); when
    omitted, the shared env-keyed :func:`build_gloomberb_client` is resolved on
    each call so pacing/cache/breaker are shared with the MCP tools and an env
    change is picked up without rebuilding the dispatcher.

    Args are validated through the tool's Pydantic input model; invalid args
    fall through to the client, which maps them to a typed ``invalid_input``
    envelope with no request (the same contract as the MCP wrappers). The
    ``content`` half of every result is attribution-enveloped JSON and the
    dispatcher never raises.
    """

    def _resolve_client() -> Any:
        return client if client is not None else build_gloomberb_client()

    def execute_tool(name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        spec = DIGIFETCH_DISPATCH.get(name)
        if spec is None:
            return {"content": f"Error: unknown digifetch tool {name!r}", "ok": False}
        try:
            payload = dict(args or {})
            request: Any = spec.input_model.model_validate(payload)
        except ValidationError:
            # Let the client produce its typed invalid_input envelope (the
            # single validation/error contract for both surfaces); the raw
            # payload still supplies the deep link when it carries one.
            request = payload
        except (TypeError, ValueError) as exc:
            # A non-mapping args payload (list/str/number) never reaches the
            # client: answer with the same typed invalid_input shape (#4146
            # review F2) instead of raising out of the tool loop.
            logger.warning("digifetch tool %s got non-mapping args: %s", name, exc)
            return {
                "content": gloomberb_envelope_json(
                    DigifetchEnvelope(
                        data=DigifetchError(
                            code="invalid_input",
                            message=(
                                f"tool args must be an object; got {type(args).__name__}: {exc}"
                            ),
                            retryable=False,
                        )
                    ),
                    attributed=spec.attributed,
                ),
                "ok": False,
            }
        try:
            envelope = getattr(_resolve_client(), spec.client_method)(request)
        except Exception as exc:  # mirror the MCP wrappers: never raise to the loop
            logger.warning("digifetch tool %s failed: %s", name, exc)
            return {
                "content": json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                "ok": False,
            }
        return {
            "content": gloomberb_envelope_json(
                envelope, symbol=_symbol_for(spec, request), attributed=spec.attributed
            ),
            # An envelope whose ``data`` slot is a typed error is still a failed
            # call: the model gets the error text, telemetry records ok=False.
            "ok": not isinstance(envelope.data, DigifetchError),
        }

    return execute_tool
