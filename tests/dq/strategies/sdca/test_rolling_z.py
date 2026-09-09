"""Tests for the rolling log-price z-score RiskModel fallback (#3175)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from digiquant.strategies.sdca.quantile_rails import MIN_FIT_HISTORY_DAYS
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel, rolling_z_is_fallback_for

pytestmark = pytest.mark.unit


def _short_series(n: int = 60, *, start: date = date(2024, 1, 1), seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = [start + timedelta(days=i) for i in range(n)]
    log_p = np.cumsum(rng.normal(0.0, 0.02, size=n)) + np.log(100.0)
    return (
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("close", np.exp(log_p)),
    )


class TestRollingZRiskModel:
    def test_satisfies_risk_model_protocol(self) -> None:
        dates, price = _short_series()
        model = RollingZRiskModel(dates, price, window=20)
        assert isinstance(model, RiskModel)

    def test_short_synthetic_series_produces_ordered_rails(self) -> None:
        dates, price = _short_series(n=60)
        model = RollingZRiskModel(dates, price, window=20)
        rails = model.rails(dates)
        assert set(rails.columns) == {"low", "median", "high"}
        assert rails.height == dates.len()
        # First observation has no lookback — null rails (no-trade day).
        assert rails["median"][0] is None
        complete = rails.drop_nulls()
        assert complete.height >= 40
        assert (complete["low"] < complete["median"]).all()
        assert (complete["median"] < complete["high"]).all()

    def test_refuses_below_two_observations(self) -> None:
        dates, price = _short_series(n=1)
        with pytest.raises(ValueError, match="at least 2"):
            RollingZRiskModel(dates, price, window=20)

    def test_is_the_fallback_below_trend_fit_floor(self) -> None:
        assert rolling_z_is_fallback_for(MIN_FIT_HISTORY_DAYS - 1)
        assert not rolling_z_is_fallback_for(MIN_FIT_HISTORY_DAYS)
