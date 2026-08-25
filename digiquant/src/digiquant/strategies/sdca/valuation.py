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

    Rows where any of the four inputs is null pass through as null (no-data
    day). Rows where all four are present must have finite, positive values
    with ``low < median < high``, or this raises ``ValueError``.
    """
    df = pl.DataFrame({"price": price, "low": low, "median": median, "high": high})

    has_data = df.select(pl.all_horizontal(pl.all().is_not_null()).alias("has_data"))["has_data"]
    complete = df.filter(has_data)
    if complete.height:
        for col in ("price", "low", "median", "high"):
            if not complete[col].is_finite().all():
                raise ValueError(f"valuation_z_score requires finite {col} values")
            if not (complete[col] > 0).all():
                raise ValueError(f"valuation_z_score requires positive {col} values")
        if (
            not (complete["low"] < complete["median"]).all()
            or not (complete["median"] < complete["high"]).all()
        ):
            raise ValueError("valuation_z_score requires low < median < high")

    log_price = df["price"].log()
    log_low = df["low"].log()
    log_median = df["median"].log()
    log_high = df["high"].log()

    below = (3.0 * (log_median - log_price) / (log_median - log_low)).clip(0.0, 3.0)
    above = (-3.0 * (log_price - log_median) / (log_high - log_median)).clip(-3.0, 0.0)

    # Gate on `has_data` last: `below`/`above` each read only one of the outer rails
    # (`low` / `high`), so a null in the *other* one would otherwise leave the taken
    # branch finite and emit a real z-score for a no-data day.
    return pl.select(
        pl.when(has_data)
        .then(pl.when(df["price"] <= df["median"]).then(below).otherwise(above))
        .otherwise(None)
        .alias("valuation_z")
    ).to_series()


__all__ = ["valuation_z_score"]
