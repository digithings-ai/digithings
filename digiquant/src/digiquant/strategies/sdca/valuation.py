"""Valuation z-score indicator — mirrors the artifact's ``eqmZScoreAtIndex``.

Positions price in log-space between a ``RiskModel``'s low/median/high rails,
reversed so cheap = +3 (max buy signal) and rich = -3 (max sell signal). This
is the SDCA engine's default/primary indicator; it takes rails as plain
Polars series so it has zero dependency on any specific ``RiskModel``.
"""

from __future__ import annotations

import polars as pl


def valuation_z_score(
    price: pl.Series,
    low: pl.Series,
    median: pl.Series,
    high: pl.Series,
) -> pl.Series:
    """Log-space position of ``price`` within ``[low, median, high]``, in [-3, 3].

    ``price <= median``: z = clamp(3 * (log(median)-log(price)) / (log(median)-log(low)), 0, 3)
    ``price > median``:  z = clamp(-3 * (log(price)-log(median)) / (log(high)-log(median)), -3, 0)
    """
    df = pl.DataFrame({"price": price, "low": low, "median": median, "high": high})
    log_price = df["price"].log()
    log_low = df["low"].log()
    log_median = df["median"].log()
    log_high = df["high"].log()

    below = (3.0 * (log_median - log_price) / (log_median - log_low)).clip(0.0, 3.0)
    above = (-3.0 * (log_price - log_median) / (log_high - log_median)).clip(-3.0, 0.0)

    return pl.select(
        pl.when(df["price"] <= df["median"]).then(below).otherwise(above).alias("valuation_z")
    ).to_series()


__all__ = ["valuation_z_score"]
