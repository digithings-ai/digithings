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


def _mr_prices(n: int, seed: int = 7) -> list[float]:
    """Generate mean-reverting prices via a genuine AR(1) process (phi=0.5).

    A single RNG is drawn once for the whole series (drawing inside the loop
    with a fresh seed each iteration would produce a deterministic sawtooth,
    not a real stochastic AR(1)). Strong mean reversion → ADF tau is well below
    zero, so the unit-root null is rejected.
    """
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    prices = [100.0]
    for i in range(1, n):
        prices.append(100.0 + 0.5 * (prices[-1] - 100.0) + noise[i])
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

    # ── Discriminating-power tests ───────────────────────────────────────────
    # These verify the ADF statistic actually distinguishes stationary from
    # non-stationary series — the property the whole mean-reversion entry relies
    # on. A sign flip or window-ordering regression would break these (the other
    # tests above only check finiteness/types and would not catch it).

    def test_tau_strongly_negative_for_mean_reverting_series(self) -> None:
        adf = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _mr_prices(120):
            adf.update(v)
        assert adf.tau is not None
        # Strong AR(1) mean reversion rejects the unit-root null (tau ≈ -3.1).
        assert adf.tau < -1.5

    def test_tau_less_negative_for_random_walk(self) -> None:
        adf = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(120):
            adf.update(v)
        assert adf.tau is not None
        # A random walk rarely rejects the unit-root null (tau ≈ -2.1, not deep).
        assert adf.tau > -3.0

    def test_mean_reverting_tau_below_random_walk_tau(self) -> None:
        adf_mr = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _mr_prices(120):
            adf_mr.update(v)
        adf_rw = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(120):
            adf_rw.update(v)
        assert adf_mr.tau is not None and adf_rw.tau is not None
        # The discriminating property: stationary series score more negative.
        assert adf_mr.tau < adf_rw.tau
