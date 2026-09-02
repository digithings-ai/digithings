"""Read helpers for thesis-first portfolio state slots."""

from __future__ import annotations

from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digiquant.research.state import RebalancePayload
from digiquant.portfolio.models.deliberation import is_unchallenged_carry
from digiquant.portfolio.state import PortfolioState


def analyst_payloads(state: PortfolioState) -> dict[str, dict[str, Any]]:
    """Per-ticker unified analyst payloads (H5)."""
    return {
        ticker: {k: v for k, v in payload.items() if k != "_document"}
        for ticker, payload in state.phase_portfolio.asset_analysts.items()
    }


def sized_book(state: PortfolioState) -> RebalancePayload | None:
    """H8 sized portfolio — sole weight owner on the thesis-first path."""
    book = state.phase_portfolio.sized_book
    if book is not None:
        return book
    # Legacy strangler: chain-terminal 7E may still populate phase7d_rebalance.
    return state.phase7d_rebalance


def _deliberation_rounds_count(rounds: Any) -> int:
    """PM↔analyst round count = the max ``round_number`` in the transcript (0 if none)."""
    if not isinstance(rounds, list):
        return 0
    numbers = [t.get("round_number") for t in rounds if isinstance(t, dict)]
    return max((n for n in numbers if isinstance(n, int)), default=0)


def _is_pm_analyst_transcript(rounds: Any) -> bool:
    """True when ``rounds`` is an H6 PM↔analyst chat (role + message), not bull/bear args."""
    if not isinstance(rounds, list) or not rounds:
        return False
    first = next((r for r in rounds if isinstance(r, dict)), None)
    if first is None:
        return False
    role = first.get("role")
    message = first.get("message")
    return role in ("pm", "analyst") and isinstance(message, str) and bool(message.strip())


def _shaped_theses(
    summary: dict[str, Any],
    *,
    rounds: Any,
    unchallenged: bool,
) -> tuple[str, str]:
    """Bull/bear fields for the published document.

    H6 ``DeliberationSummary`` has no real bull/bear theses — only a PM↔analyst
    ``transcript``. Falling both sides back to ``conclusion`` produced two identical
    cards in the UI and hid the real debate. When a chat transcript is present and
    no explicit theses were supplied, leave both empty so consumers render the chat.
    Carry paths without a transcript keep the legacy conclusion fallback (#1742).
    """
    conclusion = summary.get("conclusion", "") or ""
    explicit_bull = summary.get("bull_thesis") or ""
    explicit_bear = summary.get("bear_thesis") or ""
    chat = _is_pm_analyst_transcript(rounds)

    if explicit_bull:
        bull = str(explicit_bull)
    elif chat:
        bull = ""
    else:
        bull = str(conclusion)

    if unchallenged:
        bear = ""
    elif explicit_bear:
        bear = str(explicit_bear)
    elif chat:
        bear = ""
    else:
        bear = str(conclusion)

    return bull, bear


def deliberation_summaries(state: PortfolioState) -> dict[str, dict[str, Any]]:
    """Per-ticker deliberation summaries (H6) — PM-compatible debate shape.

    Persists the convergence metadata (``converged`` / ``escalated`` / ``cap_reason`` /
    ``rounds_count``) alongside the legacy bull/bear shape, so the published
    ``deliberation/{ticker}`` document records whether a debate actually converged, was
    carried, or hit the max-rounds cap. The Jun-2026 audit found these stripped before the
    write, leaving zero observability into the deliberation (#945).

    ``carry_reason`` rides along so a consumer can tell a benign quiet-ticker carry from a
    crashed deliberation, and a crash carry publishes **no** ``bear_thesis``: falling both
    sides back to the same ``conclusion`` produced two byte-identical theses and made a
    debate that never happened look two-sided (#1742).

    H6 chat turns are published under both ``transcript`` (canonical) and ``rounds``
    (legacy alias used by ``rounds_count`` / older consumers). When the transcript is a
    real PM↔analyst exchange, ``bull_thesis`` / ``bear_thesis`` are left empty unless the
    summary already carried distinct theses — the UI renders the chat, not mirrored cards.
    """
    out: dict[str, dict[str, Any]] = {}
    for ticker, summary in state.phase_portfolio.deliberation_summaries.items():
        if not isinstance(summary, dict):
            continue
        rounds = summary.get("transcript", summary.get("rounds", []))
        unchallenged = is_unchallenged_carry(summary)
        bull_thesis, bear_thesis = _shaped_theses(summary, rounds=rounds, unchallenged=unchallenged)
        chat = _is_pm_analyst_transcript(rounds)
        out[ticker] = {
            "ticker": ticker,
            "converged": summary.get("converged", True),
            "conclusion": summary.get("conclusion", ""),
            # Canonical chat key + legacy alias (same list when H6 ran a debate).
            "transcript": list(rounds)
            if chat
            else (
                list(summary["transcript"]) if isinstance(summary.get("transcript"), list) else []
            ),
            "rounds": rounds,
            "rounds_count": _deliberation_rounds_count(rounds),
            "bull_thesis": bull_thesis,
            "bear_thesis": bear_thesis,
            "bear_case": summary.get("bear_case") or summary.get("bear_thesis"),
            "net_stance": summary.get("net_stance", "neutral"),
            "conviction_delta": summary.get("conviction_delta", 0),
            "carried": summary.get("carried", False),
            "carry_reason": summary.get("carry_reason"),
            "escalated": summary.get("escalated", False),
            "cap_reason": summary.get("cap_reason"),
            "base_forecast_id": summary.get("base_forecast_id"),
            "amendment_id": summary.get("amendment_id"),
            "effective_forecast_id": summary.get("effective_forecast_id"),
            "amendment_outcome": summary.get("amendment_outcome"),
            "forecast_degradation": summary.get("forecast_degradation"),
            "effective_forecast": summary.get("effective_forecast"),
            # Full amendment dump for H9 registry retry after fail-soft (#2790).
            "forecast_amendment": summary.get("forecast_amendment"),
        }
    return out
