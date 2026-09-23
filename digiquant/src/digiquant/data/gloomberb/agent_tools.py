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
* :func:`build_digifetch_tool_dispatcher` — ``(name, args) -> json_str`` routed
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
    gloomberb_enabled,
)
from .entitlements import TOOL_ENTITLEMENTS
from .models import (
    AnalystResearchInput,
    CdsInput,
    CongressTradesInput,
    CorporateActionsInput,
    DigifetchEnvelope,
    DigifetchError,
    EarningsCalendarInput,
    EconCalendarInput,
    EconSeriesInput,
    EquityDiagnosticInput,
    ExchangeRateInput,
    FilingEventsInput,
    HoldersInput,
    NewsInput,
    OptionsChainInput,
    PriceHistoryInput,
    ProxyStatementsInput,
    QuoteInput,
    QuotesBatchInput,
    ResearchSearchInput,
    RiskReportsInput,
    SavedSearchesInput,
    ScreenerInput,
    SearchInput,
    SecFilingsInput,
    ShillerInput,
    ShortInterestInput,
    StatementsInput,
    ThirteenFFundsInput,
    ThirteenFHoldingsInput,
    TickerFinancialsInput,
    TickerTweetsInput,
    TranscriptsInput,
    TweetSearchInput,
    VenuesInput,
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
# One lazily-built ``GloomberbClient`` per (kill switch, session cookie) env
# pair. Keyed by the raw env values so an operator/test env change gets a fresh
# client without a process restart; the default (unset) pair is the anonymous,
# default-ON client. Only one client is kept alive: when the env pair changes,
# the replaced client is closed so its transport is not leaked. The lock
# serializes the read/close/replace dance — LangGraph runs parallel nodes, and
# they all funnel through this one cached client.

_gloomberb_clients: dict[tuple[str, str], Any] = {}
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
# Not all 33 tools everywhere (prompt budget): the equity/sector research
# phases get company facts + analyst views, the macro phase gets rates/credit/
# long-run valuation, and the portfolio PM (analyst + direction) gets a
# PM-fit mix of quotes/news/analyst views plus macro context. Every name is
# declared in ``TOOL_ENTITLEMENTS``; ``available_digifetch_tools`` drops the
# session-/pro-/preview-gated ones when no cookie is configured.
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
)


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
      typed ``auth_required`` / ``pro_required`` error with no request (#4099).

    An unknown name is a wiring bug and raises ``KeyError``.
    """
    if not gloomberb_enabled():
        return []
    names = _DEFAULT_TOOL_NAMES if subset is None else subset
    has_session = _session_cookie_present()
    schemas: list[dict[str, Any]] = []
    for name in names:
        entitlement = TOOL_ENTITLEMENTS[name]
        if entitlement != "free" and not has_session:
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
