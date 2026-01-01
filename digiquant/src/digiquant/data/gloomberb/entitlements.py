"""Per-tool entitlement declarations for the digifetch x Gloomberb family (#4110).

One vocabulary, declared once per tool and rendered on two surfaces:

* the MCP registration (``mcp_server`` attaches ``fn.entitlement`` and appends
  the note to the registered description), and
* the orchestrator manifest (``orchestrator_tools`` sets a top-level
  ``entitlement`` key and appends the same note).

Because both surfaces append the same note, every tool description an agent
reads also states its entitlement before the call.

Vocabulary:

``free``
    Anonymous read; no session cookie is needed.
``session``
    A Gloomberb session cookie (``GLOOMBERB_SESSION_COOKIE``) is required for
    the full payload. Without one the tool returns ``auth_required`` with **no
    HTTP request** (zero-HTTP gating).
``preview``
    Session required, but a free (email-verified) session still receives a
    labeled preview instead of a hard gate (today only
    ``digifetch_equity_diagnostic``). The report carries ``access="preview"``
    and the envelope carries the :data:`PREVIEW_ACCESS_WARNING` marker.
``pro``
    Session **and** a Gloomberb Pro plan. A valid free session is gated with
    the non-retryable ``pro_required`` error (distinct from ``auth_required``:
    the caller has a session, it just is not entitled), so agents can tell a
    missing entitlement apart from a missing/misconfigured session.
``venue_session``
    An own-account **venue** session (today only ``digifetch_substack`` with
    ``SUBSTACK_SESSION_COOKIE``). Without stored auth the tool returns
    ``auth_required`` with login instructions and makes **no request**
    (fail-soft, never an exception-shaped failure); an expired session maps
    to ``auth_required`` the same way.

A Pro session is supplied by putting a Gloomberb Pro account's cookie in
``GLOOMBERB_SESSION_COOKIE`` (bare token or ``name=value``); there is no
separate Pro switch in digiquant.

DigiQuant bundling placeholder: the highest DigiQuant subscription tier may
bundle Gloomberb Pro access in the future (business/partnership follow-up, no
billing code in this phase). ``entitlement="pro"`` is the hook a bundling
layer would resolve against; nothing in this module performs billing.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "Entitlement",
    "TOOL_ENTITLEMENTS",
    "ENTITLEMENT_DESCRIPTIONS",
    "entitlement_for",
    "entitlement_note",
    "with_entitlement_note",
]

Entitlement = Literal["free", "session", "preview", "pro", "venue_session"]

#: One declaration per digifetch tool (mirrors the MCP + manifest surfaces).
TOOL_ENTITLEMENTS: dict[str, Entitlement] = {
    # free — anonymous reads
    "digifetch_quote": "free",
    "digifetch_quotes_batch": "free",
    "digifetch_price_history": "free",
    "digifetch_ticker_financials": "free",
    "digifetch_options_chain": "free",
    "digifetch_sec_filings": "free",
    "digifetch_earnings_calendar": "free",
    "digifetch_exchange_rate": "free",
    "digifetch_search": "free",
    "digifetch_news": "free",
    "digifetch_econ_calendar": "free",
    "digifetch_econ_series": "free",
    "digifetch_yield_curve": "free",
    "digifetch_cds": "free",
    "digifetch_congress_trades": "free",
    "digifetch_venues": "free",
    "digifetch_13f_funds": "free",
    "digifetch_13f_holdings": "free",
    "digifetch_shiller": "free",
    "digifetch_proxy_statements": "free",
    "digifetch_filing_events": "free",
    "digifetch_risk_reports": "free",
    "digifetch_prediction_markets": "free",
    # calculators + compositions (130-coverage Task 2) — derived math, never
    # Cloud-sourced, so all six are anonymous reads like the other free tools
    "digifetch_options_calculator": "free",
    "digifetch_bond_calculator": "free",
    "digifetch_kelly_sizer": "free",
    "digifetch_dividend_yield": "free",
    "digifetch_fx_cross_rates": "free",
    "digifetch_vix_term_structure": "free",
    # options scenario (130-coverage Task 8: OSA) — derived math over the
    # options_chain read, never Cloud-sourced, so anonymous like the Task 2
    # compositions. MCP-only: all three curated subsets are at their 16-name
    # prompt-budget caps.
    "digifetch_options_scenario": "free",
    # portfolio-math compositions (130-coverage Task 3) — derived math over
    # existing reads, so all ten are anonymous reads like the other free tools
    "digifetch_compare_performance": "free",
    "digifetch_correlation_matrix": "free",
    "digifetch_relationship_graph": "free",
    "digifetch_relative_valuation": "free",
    "digifetch_fundamental_graph": "free",
    "digifetch_valuation_graph": "free",
    "digifetch_custom_chart": "free",
    "digifetch_market_valuation": "free",
    "digifetch_money_markets": "free",
    "digifetch_rate_path": "free",
    # session — GLOOMBERB_SESSION_COOKIE required (zero-HTTP auth_required without it)
    "digifetch_holders": "session",
    "digifetch_analyst_research": "session",
    "digifetch_corporate_actions": "session",
    "digifetch_research_search": "session",
    "digifetch_statements": "session",
    "digifetch_ticker_tweets": "session",
    "digifetch_tweet_search": "session",
    "digifetch_short_interest": "session",
    "digifetch_saved_searches": "session",
    # workspace writes + broker reads + approval-gated orders (130-coverage
    # Task 7): session-gated like the other account-surface tools. No personal
    # Cloud write route is verified (Task 7 source probe: team-scoped account
    # APIs only), so the workspace/broker tools are read-only in this phase and
    # never issue a request; preview mints a local ticket and execute ships
    # disabled pending human gate review.
    "digifetch_portfolio_view": "session",
    "digifetch_watchlist_add": "session",
    "digifetch_watchlist_remove": "session",
    "digifetch_portfolio_add": "session",
    "digifetch_portfolio_remove": "session",
    "digifetch_alert_add": "session",
    "digifetch_alert_list": "session",
    "digifetch_note_add": "session",
    "digifetch_thesis_add": "session",
    "digifetch_view_add": "session",
    "digifetch_broker_positions": "session",
    "digifetch_ibkr_preview_order": "session",
    "digifetch_ibkr_execute_order": "session",
    # probe-backed tools (130-coverage Task 5): Cloud reads behind the
    # session gate (zero-HTTP auth_required without the cookie). The IV trio
    # stays session per the verdicts' guess — the readers are pro_gated, so
    # a server plan denial still surfaces verbatim (typed pro_required).
    "digifetch_time_and_sales": "session",
    "digifetch_quote_recap": "session",
    "digifetch_estimate_revisions": "session",
    "digifetch_short_volume": "session",
    "digifetch_hiring": "session",
    "digifetch_central_bank_rates": "session",
    "digifetch_cdx": "session",
    "digifetch_sovereign_cds": "session",
    "digifetch_cot": "session",
    "digifetch_crypto_markets": "session",
    "digifetch_iv_screen": "session",
    "digifetch_iv_history": "session",
    "digifetch_iv_surface": "session",
    "digifetch_debt_maturities": "session",
    "digifetch_session_movers": "session",
    # preview — session required; a free session gets a labeled preview
    "digifetch_equity_diagnostic": "preview",
    # pro — session + Gloomberb Pro; a free session gets pro_required
    "digifetch_transcripts": "pro",
    "digifetch_screener": "pro",
    # probe-backed (130-coverage Task 5): FLOW is the one scanner with no
    # delayed tier — the recorded-history route fails closed on denial.
    "digifetch_options_flow": "pro",
    # venue_session — own-account venue session, fail-soft without stored auth
    "digifetch_substack": "venue_session",
    # probe-backed tools (130-coverage Task 5): the IPO calendar is a public
    # Cloud route and trending reads Yahoo's public endpoint, so both are
    # anonymous like the other free tools. They sit at the end (in manifest
    # builder order: trending, then ipo_calendar) so TOOL_ENTITLEMENTS order
    # matches manifest order for the free subset.
    "digifetch_trending": "free",
    "digifetch_ipo_calendar": "free",
    # ToS/direct tools (130-coverage Task 6): venue-direct anonymous reads
    # (CNN, VoteHub, Fiscal Data, Nasdaq Trader, Hacker News), free like the
    # other anonymous tools. Order matches manifest builder order below.
    "digifetch_fear_greed": "free",
    "digifetch_polls": "free",
    "digifetch_treasury_auctions": "free",
    "digifetch_market_halts": "free",
    "digifetch_hacker_news": "free",
}

#: The sentence appended to the MCP/manifest description for each entitlement.
ENTITLEMENT_DESCRIPTIONS: dict[Entitlement, str] = {
    "free": "Entitlement: free (anonymous; no session cookie needed).",
    "session": (
        "Entitlement: session (requires GLOOMBERB_SESSION_COOKIE; without it the "
        "tool returns auth_required with no request)."
    ),
    "preview": (
        "Entitlement: preview (requires GLOOMBERB_SESSION_COOKIE; a free session "
        "still gets a labeled preview report, access=preview)."
    ),
    "pro": (
        "Entitlement: pro (requires GLOOMBERB_SESSION_COOKIE and a Gloomberb Pro "
        "plan; a free session is gated with the non-retryable pro_required error)."
    ),
    "venue_session": (
        "Entitlement: venue_session (requires SUBSTACK_SESSION_COOKIE — your own "
        "Substack account; without it the tool returns auth_required with login "
        "instructions and makes no request)."
    ),
}


def entitlement_for(name: str) -> Entitlement | None:
    """The declared entitlement for a tool name, or None when undeclared."""
    return TOOL_ENTITLEMENTS.get(name)


def entitlement_note(name: str) -> str | None:
    """The description sentence for a declared tool, or None."""
    entitlement = entitlement_for(name)
    if entitlement is None:
        return None
    return ENTITLEMENT_DESCRIPTIONS[entitlement]


def with_entitlement_note(name: str, description: str) -> str:
    """Append the declared entitlement note to *description* (idempotent)."""
    note = entitlement_note(name)
    if note is None or note in description:
        return description
    return f"{description.rstrip()}\n\n{note}"
