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
    ``gloomberb_get_equity_diagnostic``). The report carries ``access="preview"``
    and the envelope carries the :data:`PREVIEW_ACCESS_WARNING` marker.
``pro``
    Session **and** a Gloomberb Pro plan. A valid free session is gated with
    the non-retryable ``pro_required`` error (distinct from ``auth_required``:
    the caller has a session, it just is not entitled), so agents can tell a
    missing entitlement apart from a missing/misconfigured session.

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

Entitlement = Literal["free", "session", "preview", "pro"]

#: One declaration per digifetch tool (mirrors the MCP + manifest surfaces).
TOOL_ENTITLEMENTS: dict[str, Entitlement] = {
    # free — anonymous reads
    "gloomberb_get_quote": "free",
    "gloomberb_get_quotes_batch": "free",
    "gloomberb_get_price_history": "free",
    "gloomberb_get_ticker_financials": "free",
    "gloomberb_get_options_chain": "free",
    "gloomberb_get_sec_filings": "free",
    "yahoo_get_earnings_calendar": "free",
    "gloomberb_get_exchange_rate": "free",
    "gloomberb_search": "free",
    "gloomberb_get_news": "free",
    "gloomberb_get_econ_calendar": "free",
    "gloomberb_get_econ_series": "free",
    "gloomberb_get_yield_curve": "free",
    "gloomberb_get_cds": "free",
    "gloomberb_get_congress_trades": "free",
    "gloomberb_list_venues": "free",
    "gloomberb_get_13f_funds": "free",
    "gloomberb_get_13f_holdings": "free",
    "gloomberb_get_shiller": "free",
    "gloomberb_get_proxy_statements": "free",
    "gloomberb_get_filing_events": "free",
    "gloomberb_get_risk_reports": "free",
    # session — GLOOMBERB_SESSION_COOKIE required (zero-HTTP auth_required without it)
    "gloomberb_get_holders": "session",
    "gloomberb_get_analyst_research": "session",
    "gloomberb_get_corporate_actions": "session",
    "gloomberb_search_research": "session",
    "gloomberb_get_statements": "session",
    "gloomberb_get_ticker_tweets": "session",
    "gloomberb_search_tweet": "session",
    "gloomberb_get_short_interest": "session",
    "gloomberb_list_saved_searches": "session",
    # preview — session required; a free session gets a labeled preview
    "gloomberb_get_equity_diagnostic": "preview",
    # pro — session + Gloomberb Pro; a free session gets pro_required
    "gloomberb_get_transcripts": "pro",
    "gloomberb_run_screener": "pro",
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
