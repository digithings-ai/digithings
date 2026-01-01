"""Low-level, reusable Polars indicator primitives (Track E, issue #137).

Promoted out of :mod:`digiquant.data.prices.technicals` so the technicals
pipeline and the causal levels engine share one Wilder/ATR implementation
instead of duplicating the formulas. Everything here is a pure ``pl.Expr``
with no I/O and no hidden state — callers compose the returned expressions
into their own ``with_columns`` pipelines.

Wilder smoothing (RMA) is ``alpha = 1/length`` with ``adjust=False``; this
matches ``pandas_ta`` and NautilusTrader's ``MovingAverageType.WILDER`` (see
``tests/dq/data/test_levels_nautilus.py``).
"""

from __future__ import annotations

import polars as pl


def wilder_ema(expr: pl.Expr, length: int) -> pl.Expr:
    """Wilder (RMA) smoothing: ``alpha = 1/length``, ``adjust=False``."""
    return expr.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)


def true_range() -> pl.Expr:
    """Causal true range from ``high``/``low``/``close`` columns.

    ``max(high - low, |high - prev_close|, |low - prev_close|)``; the first row
    has no previous close, so it degrades to ``high - low``.
    """
    prev_close = pl.col("close").shift(1)
    hl = pl.col("high") - pl.col("low")
    hc = (pl.col("high") - prev_close).abs()
    lc = (pl.col("low") - prev_close).abs()
    return pl.max_horizontal(hl, hc, lc)


def atr(length: int) -> pl.Expr:
    """Wilder ATR, aliased ``atr_{length}`` to match ``TECHNICAL_COLUMNS``."""
    return wilder_ema(true_range(), length).alias(f"atr_{length}")


__all__ = ["atr", "true_range", "wilder_ema"]
