"""Market breadth derived from already-computed technicals (Pillar 1D).

Breadth answers "how *broad* is the move?" — the single most-cited gap in the
research output (analysts had no breadth signal, so sector reports defaulted to
"no data"). It is derived entirely from ``price_technicals`` columns already
computed daily (``pct_vs_sma50`` / ``pct_vs_sma200``) — no new data source, no
paid feed, no long-history pull. Polars only.

``compute_breadth`` is pure (frame in, dict out) so it unit-tests with a tiny
fixture and no Supabase fake. The reader that fetches the window lives in
``olympus/atlas/data/queries.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous signal-dict values

import polars as pl


def _pct_positive(frame: pl.DataFrame, col: str) -> float | None:
    """Share (0-100) of rows whose ``col`` is > 0, over rows where it is non-null."""
    sub = frame.filter(pl.col(col).is_not_null())
    if sub.is_empty():
        return None
    return round(float((sub[col] > 0).mean()) * 100, 1)


def compute_breadth(tech_window: pl.DataFrame, *, as_of: date) -> dict[str, Any]:
    """Breadth snapshot from a ``price_technicals`` window.

    Args:
        tech_window: long frame with at least ``ticker``, ``date``,
            ``pct_vs_sma50``, ``pct_vs_sma200`` — a few trailing days per ticker
            (the newest row per ticker is "today", the one before it is "prior").
        as_of: the run date (for the ``as_of`` stamp and a ``<= as_of`` filter).

    Returns:
        Compact scalars for the shared context: universe size, % above the
        50/200-day MA, the prior % above 50DMA + a trend label. ``universe_size``
        is 0 (and pct fields absent) when there isn't enough data.
    """
    if tech_window.is_empty():
        return {"as_of": as_of.isoformat(), "universe_size": 0}

    # Supabase hands dates back as ISO strings; tests may pass real dates.
    if tech_window.schema.get("date") == pl.Utf8:
        tech_window = tech_window.with_columns(pl.col("date").str.to_date())

    df = (
        tech_window.select(
            pl.col("ticker").cast(pl.Utf8),
            pl.col("date").cast(pl.Date),
            pl.col("pct_vs_sma50").cast(pl.Float64),
            pl.col("pct_vs_sma200").cast(pl.Float64),
        )
        .filter(pl.col("date") <= as_of)
        .sort(["ticker", "date"])
    )
    if df.is_empty():
        return {"as_of": as_of.isoformat(), "universe_size": 0}

    current = df.group_by("ticker", maintain_order=True).tail(1)
    # Prior = second-newest row per ticker, but ONLY for tickers that actually have a
    # prior day in the window (>= 2 rows). Never let "prior" collapse to "current" for
    # single-row tickers — that would make pct_above_50dma_prior / breadth_trend lie.
    tail2 = df.group_by("ticker", maintain_order=True).tail(2)
    multi_row = tail2.group_by("ticker").len().filter(pl.col("len") >= 2)["ticker"]
    prior = (
        tail2.filter(pl.col("ticker").is_in(multi_row))
        .group_by("ticker", maintain_order=True)
        .head(1)
    )

    pct50 = _pct_positive(current, "pct_vs_sma50")
    pct200 = _pct_positive(current, "pct_vs_sma200")
    pct50_prior = _pct_positive(prior, "pct_vs_sma50")

    if pct50 is not None and pct50_prior is not None:
        trend = (
            "improving"
            if pct50 > pct50_prior
            else "deteriorating"
            if pct50 < pct50_prior
            else "flat"
        )
    else:
        trend = "flat"

    return {
        "as_of": as_of.isoformat(),
        "universe_size": current.height,
        "pct_above_50dma": pct50,
        "pct_above_200dma": pct200,
        "pct_above_50dma_prior": pct50_prior,
        "breadth_trend": trend,
    }


__all__ = ["compute_breadth"]
