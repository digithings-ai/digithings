"""Valuation z-score indicator — mirrors the artifact's ``eqmZScoreAtIndex``.

Positions price in log-space between a ``RiskModel``'s low/median/high rails,
reversed so cheap = +3 (max buy signal) and rich = -3 (max sell signal). This
is the SDCA engine's default/primary indicator; it takes rails as plain
Polars series so it has zero dependency on any specific ``RiskModel``.

``valuation_confluence_z`` blends this whole-history power-law leg
(long-term, unchanged) with a new medium-term leg (``valuation_trend_z``) via
the same agreement-scaled pattern used by the price-oscillator confluences
(``price_oscillators.agreement_scaled_blend``). The medium-term leg is
deliberately *not* a rolling/truncated refit of the power-law's quadratic
fit: ``walk_forward.py``'s "rails leakage" note (#3173) documents that a
quadratic-in-log-time fit on truncated history does not extrapolate, so
using one as a live medium-term signal would reintroduce that instability.
A rolling *linear* regression trend has no such problem — it is a standard,
single-formula technical indicator (a "linear regression channel"), just
applied to log(price) instead of price, and it tracks BTC's secular climb
instead of reading persistently rich against a flat rail the way a
long-window rolling mean would.
"""

from __future__ import annotations

import polars as pl

from digiquant.strategies.sdca.price_oscillators import agreement_scaled_blend

_TREND_WINDOW = 180
_SIGMA_FLOOR = 1e-12
_VALUATION_CONFLUENCE_LONG_WEIGHT = 0.5
_VALUATION_CONFLUENCE_AGREEMENT_BOOST = 0.5
_VALUATION_CONFLUENCE_DISAGREEMENT_DAMP = 0.5


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


def valuation_trend_z(
    dates: pl.Series,
    price: pl.Series,
    *,
    window: int = _TREND_WINDOW,
) -> pl.Series:
    """Distance from a rolling linear-regression trend of ``log(price)``, z-scored.

    Fits an ordinary-least-squares line to the trailing ``window`` days of
    ``log(price)`` and reports today's residual from that line in units of
    the fit's own residual standard error, sign-flipped so price below its
    local trend is cheap (+z) and above is rich (-z) — the same
    Bollinger-style convention as ``sma_band_z``, but against a local trend
    line rather than a flat rolling mean, so a steady secular climb does not
    read as persistently rich.

    A *linear* fit (not the power-law's quadratic-in-log-time) has no
    "rails leakage" (#3173) extrapolation problem on a truncated window, so
    this is safe to compute on a rolling basis unlike a rolling power-law
    refit would be. Requires the full ``window`` of trailing data — a
    regression on a handful of points is not a meaningful trend line, so
    there is no partial-window ramp-up (rows before the first full window
    are null).

    Uses closed-form rolling sums (O(n), not a per-row refit) — validated
    against ``numpy.polyfit`` to float64 precision.
    """
    if dates.len() != price.len():
        raise ValueError("dates and price must be the same length")
    if window < 3:
        raise ValueError("window must be >= 3")

    log_price = price.log()
    idx = pl.Series("idx", range(price.len()), dtype=pl.Float64)
    xy = idx * log_price

    sum_y = log_price.rolling_sum(window_size=window, min_samples=window)
    sum_xy = xy.rolling_sum(window_size=window, min_samples=window)
    sum_y2 = (log_price * log_price).rolling_sum(window_size=window, min_samples=window)

    w = float(window)
    sx = w * (w - 1.0) / 2.0
    sxx = (w - 1.0) * w * (2.0 * w - 1.0) / 6.0
    x_mean = sx / w
    sxx_centered = sxx - w * x_mean * x_mean

    window_start = idx - float(window - 1)
    sxy_rel = sum_xy - window_start * sum_y
    sxy_centered = sxy_rel - sx * (sum_y / w)

    slope = sxy_centered / sxx_centered
    intercept = sum_y / w - slope * x_mean
    predicted_last = intercept + slope * (w - 1.0)
    residual = log_price - predicted_last

    syy_centered = sum_y2 - (sum_y * sum_y) / w
    rss = (syy_centered - slope * sxy_centered).clip(lower_bound=0.0)
    dof = max(w - 2.0, 1.0)
    resid_std = (rss / dof).sqrt().clip(lower_bound=_SIGMA_FLOOR)

    return (-(residual / resid_std)).clip(-3.0, 3.0).alias("valuation_trend")


def valuation_confluence_z(
    dates: pl.Series,
    price: pl.Series,
    low: pl.Series,
    median: pl.Series,
    high: pl.Series,
    *,
    trend_window: int = _TREND_WINDOW,
    long_term_weight: float = _VALUATION_CONFLUENCE_LONG_WEIGHT,
    agreement_boost: float = _VALUATION_CONFLUENCE_AGREEMENT_BOOST,
    disagreement_damp: float = _VALUATION_CONFLUENCE_DISAGREEMENT_DAMP,
) -> pl.Series:
    """Whole-history power-law valuation (long-term) + rolling trend (medium-term).

    Same agreement-scaled blend as ``rsi_confluence_z`` /
    ``macd_confluence_z`` / ``sma_band_confluence_z`` /
    ``rs_eth_confluence_z``. The long-term leg is ``valuation_z_score``
    against the ``RiskModel`` rails, completely unchanged. The medium-term
    leg is ``valuation_trend_z``, which is responsive to few-months
    pullbacks the whole-history quantile bands never approach.
    """
    long_term = valuation_z_score(price, low, median, high)
    medium_term = valuation_trend_z(dates, price, window=trend_window)
    return agreement_scaled_blend(
        long_term,
        medium_term,
        long_term_weight=long_term_weight,
        agreement_boost=agreement_boost,
        disagreement_damp=disagreement_damp,
        name="valuation_z",
    )


__all__ = ["valuation_confluence_z", "valuation_trend_z", "valuation_z_score"]
