"""Per-tool entitlement declarations for the digifetch x Gloomberb family (#4110).

One vocabulary, declared once per tool and surfaced in three places:

* the MCP registration (``mcp_server`` attaches ``fn.entitlement`` and appends
  the note to the registered description),
* the orchestrator manifest (``orchestrator_tools`` sets a top-level
  ``entitlement`` key and appends the same note), and
* the tool descriptions themselves (so an agent sees the requirement before
  calling).

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
    # session — GLOOMBERB_SESSION_COOKIE required (zero-HTTP auth_required without it)
    "digifetch_holders": "session",
    "digifetch_analyst_research": "session",
    "digifetch_corporate_actions": "session",
    "digifetch_research_search": "session",
    "digifetch_statements": "session",
    "digifetch_ticker_tweets": "session",
    "digifetch_tweet_search": "session",
    "digifetch_short_interest": "session",
    # preview — session required; a free session gets a labeled preview
    "digifetch_equity_diagnostic": "preview",
    # pro — session + Gloomberb Pro; a free session gets pro_required
    "digifetch_transcripts": "pro",
    "digifetch_screener": "pro",
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
    entitlement = TOOL_ENTITLEMENTS.get(name)
    if entitlement is None:
        return None
    return ENTITLEMENT_DESCRIPTIONS[entitlement]


def with_entitlement_note(name: str, description: str) -> str:
    """Append the declared entitlement note to *description* (idempotent)."""
    note = entitlement_note(name)
    if note is None or note in description:
        return description
    return f"{description.rstrip()}\n\n{note}"
