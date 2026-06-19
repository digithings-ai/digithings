"""Deterministic Hermes focus-list selection (#696).

Phase 7C/7CD per-ticker deliberation previously fanned out over the first
``ATLAS_MAX_ANALYSTS`` tickers of the watchlist — an arbitrary alphabetical
slice. The focus list applies the same analytical depth where it matters
instead: **current portfolio holdings** (reviewed every day, always included)
plus the **top-scored opportunity candidates** ranked by simple, explainable
technical signals from ``price_technicals``. Zero LLM calls — one bulk
Supabase read; thematic market coverage is unchanged (phases 1-6 research the
whole market regardless).

**Interim roster (not thesis-first):** the intended Hermes entry translates
Atlas research into theses and maps vehicles per thesis before analysts run
(h1–h4 in ``hermes/docs/HERMES_SUBGRAPH.md``). Until that pipeline is wired,
this module supplies the Phase 7C fan-out list. See ``hermes/docs/ARCHITECTURE.md``.

The score is intentionally legible (trend + momentum + strength − stretch),
not a black box — it decides *where to spend deliberation*, never *what to
trade*; the PM still sees the full research context.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

from digiquant.olympus.atlas.data.queries import TECHNICAL_COLUMNS

logger = logging.getLogger(__name__)

_DEFAULT_TOP_N = 5


def _focus_top_n() -> int:
    """Opportunity-candidate count (env ``HERMES_FOCUS_TOP_N``, default 5)."""
    try:
        n = int(os.environ.get("HERMES_FOCUS_TOP_N", str(_DEFAULT_TOP_N)) or _DEFAULT_TOP_N)
    except ValueError:
        return _DEFAULT_TOP_N
    return max(0, n)


def load_portfolio_holdings() -> list[str]:
    """Tickers of current positions from ``config/portfolio.json`` ([] if absent)."""
    from digiquant.olympus.atlas.graph import _atlas_config_root

    path = _atlas_config_root() / "portfolio.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("portfolio.json unreadable (%s); no holdings in focus list", exc)
        return []
    tickers: list[str] = []
    for pos in data.get("positions") or []:
        ticker = str(pos.get("ticker") or "").strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def holdings_from_prior_book(prior_book: list[dict[str, Any]]) -> list[str]:
    """Non-cash tickers from materialized ``positions`` rows (preferred over portfolio.json)."""
    tickers: list[str] = []
    for row in prior_book:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker == "CASH":
            continue
        if ticker not in tickers:
            tickers.append(ticker)
    return tickers


def score_technicals(row: dict[str, Any]) -> float:
    """Legible long-bias opportunity score from one ``price_technicals`` row.

    trend (above 50/200-day SMA) + momentum (21-day ROC, clamped) +
    strength (ADX ≥ 25) − stretch (RSI beyond 25/75).
    """

    def _num(key: str) -> float | None:
        v = row.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    score = 0.0
    pct50 = _num("pct_vs_sma50")
    pct200 = _num("pct_vs_sma200")
    roc = _num("roc_21")
    adx = _num("adx_14")
    rsi = _num("rsi_14")
    if pct50 is not None and pct50 > 0:
        score += 1.0
    if pct200 is not None and pct200 > 0:
        score += 1.0
    if roc is not None:
        score += max(-2.0, min(2.0, roc / 5.0))
    if adx is not None and adx >= 25:
        score += 0.5
    if rsi is not None and (rsi > 75 or rsi < 25):
        score -= 1.0
    return score


def select_focus_tickers(
    *,
    client: Any,
    watchlist: list[str] | tuple[str, ...],
    run_date: date,
    top_n: int | None = None,
    price_window_days: int = 7,
    holdings: list[str] | None = None,
) -> list[str]:
    """Holdings + top-``top_n`` scored watchlist tickers (holdings first, deduped).

    ``holdings`` overrides ``portfolio.json`` when provided (e.g. from Supabase
    ``positions`` via preflight ``prior_book``).
    """
    n = _focus_top_n() if top_n is None else max(0, top_n)
    holdings_list = list(holdings) if holdings is not None else load_portfolio_holdings()
    seen: set[str] = set(holdings_list)
    candidates: list[str] = []
    for ticker in watchlist:
        if ticker not in seen:
            seen.add(ticker)
            candidates.append(ticker)
    if not candidates or n == 0:
        logger.info("hermes focus list (%d): %s", len(holdings_list), ", ".join(holdings_list))
        return list(holdings_list)
    try:
        since = (run_date - timedelta(days=price_window_days)).isoformat()
        resp = (
            client.table("price_technicals")
            .select(",".join(("ticker", *TECHNICAL_COLUMNS)))
            .in_("ticker", candidates)
            .gte("date", since)
            .order("date", desc=True)
            .limit(len(candidates) * price_window_days)
            .execute()
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in getattr(resp, "data", None) or []:
            ticker = row.get("ticker")
            if ticker and ticker not in latest:
                latest[ticker] = row
        ranked = sorted(
            (t for t in candidates if t in latest),
            key=lambda t: score_technicals(latest[t]),
            reverse=True,
        )
        top = ranked[:n]
    except Exception as exc:  # noqa: BLE001 — scoring is best-effort routing, never fatal
        logger.warning("focus scoring unavailable (%s); using watchlist head", exc)
        top = candidates[:n]
    focus = [*holdings_list, *top]
    logger.info("hermes focus list (%d): %s", len(focus), ", ".join(focus))
    return focus
