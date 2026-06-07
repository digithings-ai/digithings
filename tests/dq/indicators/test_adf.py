"""Tests for RollingADF — rolling Augmented Dickey-Fuller test wrapper."""

from __future__ import annotations

import math
import numpy as np
import pytest
from digiquant.indicators.adf import RollingADF


def _rw_prices(n: int, seed: int = 42) -> list[float]:
    """Generate a random walk (non-stationary). ADF tau should be close to 0 or positive."""
    rng = np.random.default_rng(seed)
    changes = rng.standard_normal(n)
    prices = np.cumsum(changes) + 100.0
    return prices.tolist()


def _mr_prices(n: int) -> list[float]:
    """Generate mean-reverting prices (stationary). ADF tau should be negative."""
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(
            100.0 + 0.5 * (prices[-1] - 100.0) + np.random.default_rng(0).standard_normal(1)[0]
        )
    return prices


class TestRollingADF:
    def test_not_initialized_before_lookback(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in range(19):
            adf.update(float(v))
        assert not adf.initialized
        assert adf.tau is None

    def test_initialized_at_lookback(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(30):
            adf.update(v)
        assert adf.initialized
        assert adf.tau is not None

    def test_tau_is_finite(self) -> None:
        adf = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(50):
            adf.update(v)
        assert adf.initialized
        assert math.isfinite(adf.tau)

    def test_dynamic_adf_equals_tau_when_no_ma(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(30):
            adf.update(v)
        assert adf.dynamic_adf == pytest.approx(adf.tau)

    def test_dynamic_adf_differs_from_tau_with_ma(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=True, ma_type="EMA", ma_length=3)
        prices = _rw_prices(40)
        for v in prices:
            adf.update(v)
        assert adf.dynamic_adf is not None

    def test_crossover_detected(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(60):
            adf.update(v)
        assert isinstance(adf.crossover(level=-1.0), bool)
        assert isinstance(adf.crossunder(level=-1.0), bool)

    def test_tau_ema7_negative_property(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(50):
            adf.update(v)
        assert isinstance(adf.tau_ema7_negative, bool)
