"""Deterministic turnover / min-hold discipline for Hermes rebalance (#859 Phase D)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_entry_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_cash(ticker: str) -> bool:
    return ticker.strip().upper() == "CASH"


def apply_turnover_to_sized_book(
    sized: dict[str, float],
    *,
    current_weights: dict[str, float],
    prior_book: list[dict[str, Any]],
    preferences: dict[str, Any],
    run_date: date,
) -> dict[str, float]:
    """Clamp sized targets toward current weights when inside the no-trade band or min-hold.

    The no-trade band is the larger of an absolute floor (``rebalance_threshold_pct``, pp)
    and a **relative** band (``rebalance_rel_band_pct`` % of the position's own size, #934).
    A relative band keeps a large position from churning on a small drift (a 30% name with a
    3pp move stays put) while small positions still use the absolute floor — research-backed
    turnover discipline that lets the book *evolve* day-over-day instead of rewriting.
    """
    if not current_weights:
        return sized

    threshold = float(preferences.get("rebalance_threshold_pct") or 3.0)  # absolute floor (pp)
    rel_band = float(preferences.get("rebalance_rel_band_pct") or 20.0) / 100.0  # of position size
    holding_days = int(preferences.get("holding_days") or 5)
    entry_by_ticker = {
        str(row["ticker"]): _parse_entry_date(row.get("entry_date"))
        for row in prior_book
        if row.get("ticker")
    }

    out = dict(sized)
    for ticker, current_pct in current_weights.items():
        if _is_cash(ticker) or current_pct <= 0:
            continue
        target_pct = out.get(ticker, 0.0)
        delta = abs(target_pct - current_pct)
        entry = entry_by_ticker.get(ticker)
        inside_hold = False
        if entry is not None:
            inside_hold = (run_date - entry).days < holding_days

        if target_pct <= 0 and inside_hold:
            out[ticker] = current_pct
            continue
        band = max(threshold, rel_band * current_pct)
        if delta < band and target_pct > 0:
            out[ticker] = current_pct
    return out
