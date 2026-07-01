"""Per-ticker fingerprint for H5/H6 skip/edit (#925 extension)."""

from __future__ import annotations

import hashlib
import json

from digiquant.olympus.edit_mode.models import TriageSignal
from digiquant.olympus.hermes.state import HermesState

DEFAULT_PRICE_QUIET_THRESHOLD = 0.015


def news_hash_for_ticker(state: HermesState, ticker: str) -> str:
    """Stable hash of digest/news signals relevant to *ticker*."""
    bias = state.phase6_bias_row if isinstance(state.phase6_bias_row, dict) else {}
    payload = {
        "digest_date": (state.phase7_digest or {}).get("date"),
        "bias": bias.get("bias"),
        "invalidation_signals": bias.get("invalidation_signals"),
        "ticker": ticker.upper(),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def price_move_quiet(
    state: HermesState,
    ticker: str,
    *,
    threshold: float = DEFAULT_PRICE_QUIET_THRESHOLD,
) -> bool:
    delta = state.price_deltas.get(ticker)
    if delta is None:
        return True
    return abs(float(delta)) <= threshold


def ticker_triage_signal(
    state: HermesState,
    ticker: str,
    *,
    current_stance: str | None,
    prior_stance: str | None,
    prior_news_hash: str | None = None,
) -> TriageSignal | None:
    """Return quiet/stale for ``resolve_edit_mode``; ``None`` when no prior analyst exists."""
    prior = state.prior_context.prior_analyst_by_ticker.get(ticker)
    if prior is None and prior_stance is None:
        return None

    effective_prior_stance = prior_stance or (prior or {}).get("stance")
    if not effective_prior_stance:
        return TriageSignal(mode="stale")

    stance_quiet = bool(current_stance) and current_stance == effective_prior_stance
    news_quiet = prior_news_hash is None or prior_news_hash == news_hash_for_ticker(state, ticker)
    if price_move_quiet(state, ticker) and news_quiet and stance_quiet:
        return TriageSignal(mode="quiet")
    return TriageSignal(mode="stale")


def deliberation_skip_signal(
    state: HermesState,
    ticker: str,
    *,
    analyst_stance: str,
) -> bool:
    """True when H6 should carry prior deliberation with zero LLM calls."""
    prior_analyst = state.prior_context.prior_analyst_by_ticker.get(ticker, {})
    prior_stance = prior_analyst.get("stance")
    prior_news = str(prior_analyst.get("fingerprint_news_hash") or "")
    signal = ticker_triage_signal(
        state,
        ticker,
        current_stance=analyst_stance,
        prior_stance=prior_stance,
        prior_news_hash=prior_news or None,
    )
    if signal is None or signal.mode != "quiet":
        return False
    # A prior deliberation must exist to carry. ``deliberation/*`` is excluded from
    # latest_segments (#925), so read the slim carry hydrated in preflight; fall back
    # to latest_segments for any caller that still stashes a full payload there.
    slim = state.prior_context.prior_deliberation_by_ticker.get(ticker)
    if isinstance(slim, dict) and slim:
        return True
    row = state.prior_context.latest_segments.get(f"deliberation/{ticker}")
    return isinstance(row, dict) and bool(row.get("payload"))
