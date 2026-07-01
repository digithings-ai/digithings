"""Deterministic turnover / min-hold discipline for Hermes rebalance (#859 Phase D).

Also hosts the mark-to-market drift + rebalancing-cadence logic (#955): the sizer's
no-trade band must compare today's targets against the *drifted* current book, and a
configurable cadence controls how often a calendar rebalance is allowed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any  # noqa  # scored-lint suppression: entry_date coercion

# Cadence values read from config preferences (``preferences["rebalancing_cadence"]``),
# sourced from portfolio.json ``constraints`` during preflight. Default "daily".
_VALID_CADENCES = frozenset({"daily", "weekly", "monthly", "none"})


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


def mark_to_market_weights(
    weights: dict[str, float],
    deltas: dict[str, float],
) -> dict[str, float]:
    """Drift ``weights`` by per-ticker returns since the last run, renormalized (#955).

    Each non-cash position's value moves by ``deltas[ticker]`` (a fractional return,
    e.g. ``0.03`` for +3%); CASH does not drift. Weights are renormalized to the prior
    gross so the book still sums to the same total — a position bought at 15% that
    rallies 3% in a day becomes ~15.4% and cash's *share* shrinks accordingly. Pure: no
    I/O. Returns the input unchanged when it is empty or the drifted total is degenerate.
    """
    if not weights:
        return dict(weights)
    drifted: dict[str, float] = {}
    for ticker, weight in weights.items():
        if _is_cash(ticker):
            drifted[ticker] = weight
        else:
            drifted[ticker] = weight * (1.0 + float(deltas.get(ticker, 0.0)))
    total = sum(drifted.values())
    prior_total = sum(weights.values())
    if total <= 0 or prior_total <= 0:
        return dict(weights)
    scale = prior_total / total
    return {ticker: round(value * scale, 6) for ticker, value in drifted.items()}


def should_rebalance_today(
    cadence: str,
    run_date: date,
    preferences: dict[str, Any] | None = None,
) -> bool:
    """Whether a calendar rebalance is permitted on ``run_date`` for ``cadence`` (#955).

    - ``daily`` → always rebalance (band still suppresses churn).
    - ``weekly`` → on the configured weekday (``rebalance_weekday``, 0=Mon, default Mon).
    - ``monthly`` → on the configured day-of-month (``rebalance_day_of_month``, default 1);
      anchors above 28 are capped to 28 so the day exists in every month (no true
      last-day / month-end firing — day 31 fires on the 28th).
    - ``none`` → never auto-rebalance (drift held; only PM direction changes trade).

    Unknown cadence values fall back to ``daily`` (safe: matches prior behavior).
    """
    prefs = preferences or {}
    normalized = str(cadence or "daily").strip().lower()
    if normalized not in _VALID_CADENCES:
        normalized = "daily"
    if normalized == "daily":
        return True
    if normalized == "none":
        return False
    if normalized == "weekly":
        anchor = int(prefs.get("rebalance_weekday") or 0)
        return run_date.weekday() == max(0, min(6, anchor))
    # monthly
    anchor = int(prefs.get("rebalance_day_of_month") or 1)
    anchor = max(1, min(28, anchor))  # 28 is the safe upper bound across all months
    return run_date.day == anchor


def hold_drifted_book(
    sized: dict[str, float],
    *,
    current_weights: dict[str, float],
) -> dict[str, float]:
    """Non-rebalance-day book: hold drifted weights; honor PM direction changes only (#955).

    On a day the cadence does not permit a calendar rebalance, a continuing held
    position keeps its drifted current weight (no trade) — magnitude trims/adds wait
    for the next scheduled rebalance. PM *direction* decisions are still honored
    immediately: a target of 0 exits the name, and a name with no current weight is a
    new entry booked at its sized target. This is the "weights drift; rebalance only on
    an explicit decision" behavior the configured cadence asks for.
    """
    if not current_weights:
        return sized
    out: dict[str, float] = {}
    for ticker, target in sized.items():
        if _is_cash(ticker):
            continue
        current = float(current_weights.get(ticker, 0.0))
        if target <= 0:
            continue  # PM exit → drop to flat (residual becomes cash)
        if current <= 0:
            out[ticker] = target  # new entry → book at target
        else:
            out[ticker] = current  # continuing position → hold drifted weight
    return out


def apply_rebalancing_cadence(
    sized: dict[str, float],
    *,
    current_weights: dict[str, float],
    prior_book: list[dict[str, Any]],
    preferences: dict[str, Any],
    run_date: date,
) -> dict[str, float]:
    """Dispatch sizing through the rebalancing cadence (#955).

    On a permitted rebalance day, apply the normal no-trade band
    (:func:`apply_turnover_to_sized_book`). Otherwise hold the drifted book
    (:func:`hold_drifted_book`). ``current_weights`` must already be mark-to-market
    drifted (see :func:`mark_to_market_weights`).
    """
    cadence = str(preferences.get("rebalancing_cadence") or "daily")
    if should_rebalance_today(cadence, run_date, preferences):
        return apply_turnover_to_sized_book(
            sized,
            current_weights=current_weights,
            prior_book=prior_book,
            preferences=preferences,
            run_date=run_date,
        )
    return hold_drifted_book(sized, current_weights=current_weights)


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
