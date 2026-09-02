"""Rolling log-price z-score ``RiskModel`` — short-history fallback (#3175).

For series where a trend fit is unjustifiable (below
``MIN_FIT_HISTORY_DAYS``, or an asset with no long-run valuation thesis).
Degrades to "cheap relative to recent history" rather than pretending to
know a long-run trend.

The ``RiskModel`` protocol is ``rails(dates)`` only, so this stores the
``(date, price)`` history at construction and evaluates a causal rolling
log-mean / log-std. Days before ``min_samples`` have null rails (no-trade).
"""

from __future__ import annotations

import polars as pl

from digiquant.strategies.sdca.quantile_rails import MIN_FIT_HISTORY_DAYS

DEFAULT_ROLLING_WINDOW = 90
_MIN_SAMPLES = 2
_SIGMA_FLOOR = 1e-8


class RollingZRiskModel:
    """``RiskModel``: rolling log-price mean ± z·std as median / low / high."""

    def __init__(
        self,
        dates: pl.Series,
        price: pl.Series,
        *,
        window: int = DEFAULT_ROLLING_WINDOW,
        z: float = 1.0,
    ) -> None:
        if window < _MIN_SAMPLES:
            raise ValueError(f"rolling-z window must be >= {_MIN_SAMPLES}, got {window}")
        if z <= 0:
            raise ValueError(f"rolling-z z must be positive, got {z}")
        if dates.dtype != pl.Date:
            raise ValueError(f"RollingZRiskModel requires dates to be pl.Date, got {dates.dtype}")
        if dates.len() < _MIN_SAMPLES:
            raise ValueError(
                f"RollingZRiskModel requires at least {_MIN_SAMPLES} observations, "
                f"got {dates.len()}"
            )
        if price.len() != dates.len():
            raise ValueError(
                f"RollingZRiskModel requires dates and price to have the same length, "
                f"got {dates.len()}, {price.len()}"
            )
        if dates.is_null().any() or price.is_null().any():
            raise ValueError("RollingZRiskModel requires dates and price to have no null values")
        if not price.is_finite().all() or not (price > 0).all():
            raise ValueError("RollingZRiskModel requires price to be finite and positive")
        date_list = dates.to_list()
        if any(date_list[i] >= date_list[i + 1] for i in range(len(date_list) - 1)):
            raise ValueError("RollingZRiskModel requires dates to be strictly increasing")

        frame = pl.DataFrame({"date": dates, "price": price}).sort("date")
        frame = frame.with_columns(pl.col("price").log().alias("log_p"))
        frame = frame.with_columns(
            pl.col("log_p").rolling_mean(window_size=window, min_samples=_MIN_SAMPLES).alias("mu"),
            pl.col("log_p")
            .rolling_std(window_size=window, min_samples=_MIN_SAMPLES)
            .alias("sigma"),
        )
        self._history = frame.select("date", "mu", "sigma")
        self.window = window
        self.z = z

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        """Causal rolling log-price rails; null until ``min_samples`` observations."""
        if dates.dtype != pl.Date:
            raise ValueError(f"rails requires dates to be pl.Date, got {dates.dtype}")
        if dates.len() == 0:
            raise ValueError("rails requires at least one row")
        if dates.is_null().any():
            raise ValueError("rails requires dates to have no null values")

        lookback = self._history.with_columns(
            (pl.col("mu") - self.z * pl.col("sigma").clip(lower_bound=_SIGMA_FLOOR))
            .exp()
            .alias("low"),
            pl.col("mu").exp().alias("median"),
            (pl.col("mu") + self.z * pl.col("sigma").clip(lower_bound=_SIGMA_FLOOR))
            .exp()
            .alias("high"),
        ).select("date", "low", "median", "high")
        requested = pl.DataFrame({"date": dates})
        joined = requested.join(lookback, on="date", how="left")
        return joined.select("low", "median", "high")


def rolling_z_is_fallback_for(n_rows: int) -> bool:
    """True when a trend fit would refuse this series (below ``MIN_FIT_HISTORY_DAYS``)."""
    return n_rows < MIN_FIT_HISTORY_DAYS


__all__ = [
    "DEFAULT_ROLLING_WINDOW",
    "RollingZRiskModel",
    "rolling_z_is_fallback_for",
]
