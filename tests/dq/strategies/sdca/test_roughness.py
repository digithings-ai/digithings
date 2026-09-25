"""Tests for the per-indicator roughness diagnostic (#SDCA index smoothing)."""

from __future__ import annotations

import pytest
import polars as pl
from digiquant.strategies.sdca.composite_risk import Z_TO_RISK_SCALE
from digiquant.strategies.sdca.roughness import compute_indicator_roughness, compute_pool_roughness

pytestmark = pytest.mark.unit


class TestComputeIndicatorRoughness:
    def test_constant_series_has_zero_roughness(self) -> None:
        z = pl.Series("z", [1.0] * 50, dtype=pl.Float64)
        stats = compute_indicator_roughness("flat", z)
        assert stats.name == "flat"
        assert stats.n_days == 50
        assert stats.mean_abs_delta_risk == pytest.approx(0.0)
        assert stats.max_abs_delta_risk == pytest.approx(0.0)
        assert stats.spike_days_gt_2 == 0

    def test_step_function_produces_one_large_spike(self) -> None:
        # 30 days at z=0.0, one jump to z=3.0, 30 more days at z=3.0.
        z = pl.Series("z", [0.0] * 30 + [3.0] * 30, dtype=pl.Float64)
        stats = compute_indicator_roughness("step", z)
        expected_jump = 3.0 * Z_TO_RISK_SCALE
        assert stats.max_abs_delta_risk == pytest.approx(expected_jump)
        assert stats.spike_days_gt_2 == 1
        assert stats.spike_days_gt_5 == (1 if expected_jump > 5.0 else 0)
        # 58 zero-deltas + 1 nonzero delta out of 59 total deltas.
        assert stats.mean_abs_delta_risk == pytest.approx(expected_jump / 59.0)

    def test_ramp_has_no_spikes_above_its_per_step_delta(self) -> None:
        # Linear ramp from 0.0 to 3.0 over 30 days -- per-step delta is small
        # and constant, unlike the step function's single large jump.
        z = pl.Series("z", [round(3.0 * i / 29, 6) for i in range(30)], dtype=pl.Float64)
        stats = compute_indicator_roughness("ramp", z)
        per_step = (3.0 / 29) * Z_TO_RISK_SCALE
        assert stats.max_abs_delta_risk == pytest.approx(per_step, abs=1e-4)
        assert stats.spike_days_gt_2 == 0

    def test_nulls_are_dropped_before_differencing(self) -> None:
        # Leading nulls (e.g. a rolling window's warm-up) must not count as
        # a delta once real values begin.
        z = pl.Series("z", [None, None, 1.0, 1.0, 1.0], dtype=pl.Float64)
        stats = compute_indicator_roughness("warmup", z)
        assert stats.n_days == 3
        assert stats.max_abs_delta_risk == pytest.approx(0.0)

    def test_empty_series_returns_zeroed_stats(self) -> None:
        z = pl.Series("z", [], dtype=pl.Float64)
        stats = compute_indicator_roughness("empty", z)
        assert stats.n_days == 0
        assert stats.mean_abs_delta_risk == pytest.approx(0.0)


class TestComputePoolRoughness:
    def test_returns_one_entry_per_indicator_in_input_order(self) -> None:
        indicators = {
            "a": pl.Series("a", [0.0, 0.0], dtype=pl.Float64),
            "b": pl.Series("b", [0.0, 5.0], dtype=pl.Float64),
        }
        results = compute_pool_roughness(indicators)
        assert [r.name for r in results] == ["a", "b"]
        assert results[0].max_abs_delta_risk == pytest.approx(0.0)
        assert results[1].max_abs_delta_risk == pytest.approx(5.0 * Z_TO_RISK_SCALE)
