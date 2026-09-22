"""Tests for the composite-risk indicator vote (weighted z-score blend -> 0-100 risk)."""

from __future__ import annotations

import math

import polars as pl
import pytest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk

pytestmark = pytest.mark.unit


class TestComputeCompositeRisk:
    def test_single_indicator_cheap_gives_risk_0(self) -> None:
        indicators = [IndicatorWeight(name="val", z=pl.Series([3.0]), weight=1.0)]
        result = compute_composite_risk(indicators)
        assert result["risk"][0] == pytest.approx(0.0)

    def test_single_indicator_rich_gives_risk_100(self) -> None:
        indicators = [IndicatorWeight(name="val", z=pl.Series([-3.0]), weight=1.0)]
        result = compute_composite_risk(indicators)
        assert result["risk"][0] == pytest.approx(100.0)

    def test_single_indicator_neutral_gives_risk_50(self) -> None:
        indicators = [IndicatorWeight(name="val", z=pl.Series([0.0]), weight=1.0)]
        result = compute_composite_risk(indicators)
        assert result["risk"][0] == pytest.approx(50.0)

    def test_equal_weighted_two_indicators_average(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=1.0),
            IndicatorWeight(name="b", z=pl.Series([-3.0]), weight=1.0),
        ]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] == pytest.approx(0.0)
        assert result["risk"][0] == pytest.approx(50.0)

    def test_weighted_vote_skews_toward_heavier_indicator(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=5.0),
            IndicatorWeight(name="b", z=pl.Series([-3.0]), weight=1.0),
        ]
        result = compute_composite_risk(indicators)
        # (3*5 + -3*1) / 6 = 2.0
        assert result["composite_z"][0] == pytest.approx(2.0)

    def test_disabled_indicator_excluded_from_blend(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=1.0, enabled=True),
            IndicatorWeight(name="b", z=pl.Series([-3.0]), weight=1.0, enabled=False),
        ]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] == pytest.approx(3.0)

    def test_composite_z_clamped_to_plus_minus_3(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([10.0]), weight=1.0)]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] == pytest.approx(3.0)

    def test_any_enabled_indicator_null_gives_null_row_no_partial_blend(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0, None]), weight=1.0),
            IndicatorWeight(name="b", z=pl.Series([2.0, 1.0]), weight=1.0),
        ]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] is not None
        assert result["composite_z"][1] is None
        assert result["risk"][1] is None

    def test_no_enabled_indicators_raises(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0]), weight=1.0, enabled=False)]
        with pytest.raises(ValueError, match="at least one"):
            compute_composite_risk(indicators)

    def test_empty_indicator_list_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            compute_composite_risk([])

    def test_duplicate_enabled_indicator_names_raises(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=1.0),
            IndicatorWeight(name="a", z=pl.Series([-3.0]), weight=1.0),
        ]
        with pytest.raises(ValueError, match="duplicate"):
            compute_composite_risk(indicators)

    def test_duplicate_disabled_indicator_name_is_fine(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=1.0, enabled=True),
            IndicatorWeight(name="a", z=pl.Series([-3.0]), weight=1.0, enabled=False),
        ]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] == pytest.approx(3.0)

    def test_zero_total_weight_raises(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([3.0]), weight=1.0),
            IndicatorWeight(name="b", z=pl.Series([-3.0]), weight=-1.0),
        ]
        with pytest.raises(ValueError, match="total weight"):
            compute_composite_risk(indicators)


class TestRollingCompositeNormalization:
    """``rolling_window`` re-normalizes the blend before the ``[-3, 3]`` clip."""

    def test_default_none_matches_plain_clip(self) -> None:
        z = [3.0, 1.0, -2.0, 10.0, -10.0, 0.0]
        indicators = [IndicatorWeight(name="a", z=pl.Series(z), weight=1.0)]
        off = compute_composite_risk(indicators)
        explicit_off = compute_composite_risk(indicators, rolling_window=None)
        assert off["composite_z"].to_list() == explicit_off["composite_z"].to_list()
        assert off["composite_z"].to_list() == [3.0, 1.0, -2.0, 3.0, -3.0, 0.0]

    def test_warmup_rows_are_null_until_min_samples(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0] * 10), weight=1.0)]
        result = compute_composite_risk(indicators, rolling_window=10, rolling_min_samples=5)
        assert result["composite_z"][:4].to_list() == [None, None, None, None]
        assert result["composite_z"][4] is not None

    def test_min_samples_defaults_to_half_window_floored_at_20(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0] * 200), weight=1.0)]
        result = compute_composite_risk(indicators, rolling_window=100)
        # default min_samples = max(20, 100 // 2) = 50
        assert result["composite_z"][48] is None
        assert result["composite_z"][49] is not None

    def test_flat_series_gives_null_not_nan_at_zero_sigma(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([2.0] * 30), weight=1.0)]
        result = compute_composite_risk(indicators, rolling_window=10, rolling_min_samples=5)
        z = result["composite_z"][-1]
        assert z is not None
        assert math.isfinite(z)

    def test_restabilizes_a_drifting_series_flat_expanding_would_not(self) -> None:
        # A slow upward drift plus a late spike: an expanding/whole-history z
        # would keep sliding as history accumulates. A short rolling window
        # should read the late spike as extreme relative to its own recent
        # regime, not muted by years of prior, lower-level history.
        drift = [float(i) * 0.01 for i in range(300)]
        spike = drift[:-1] + [drift[-2] + 5.0]
        indicators = [IndicatorWeight(name="a", z=pl.Series(spike), weight=1.0)]
        rolling = compute_composite_risk(indicators, rolling_window=30, rolling_min_samples=15)
        assert rolling["composite_z"][-1] == pytest.approx(3.0)

    def test_rolling_window_below_2_raises(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0, 2.0, 3.0]), weight=1.0)]
        with pytest.raises(ValueError, match="rolling_window must be >= 2"):
            compute_composite_risk(indicators, rolling_window=1)

    def test_null_indicator_row_still_nulls_composite_and_risk(self) -> None:
        indicators = [
            IndicatorWeight(name="a", z=pl.Series([1.0] * 10 + [None] + [1.0] * 10), weight=1.0)
        ]
        result = compute_composite_risk(indicators, rolling_window=10, rolling_min_samples=5)
        assert result["composite_z"][10] is None
        assert result["risk"][10] is None

    def test_rolling_blend_of_two_indicators_uses_weighted_average_as_input(self) -> None:
        a = [1.0] * 40
        b = [-1.0] * 39 + [5.0]
        indicators = [
            IndicatorWeight(name="a", z=pl.Series(a), weight=1.0),
            IndicatorWeight(name="b", z=pl.Series(b), weight=1.0),
        ]
        rolling = compute_composite_risk(indicators, rolling_window=20, rolling_min_samples=10)
        # weighted avg is flat 0.0 for 39 rows then jumps to 2.0 on the last row
        assert rolling["composite_z"][-1] == pytest.approx(3.0)


class TestCompositeSmoothing:
    """``smoothing_window`` is a causal rolling mean applied after the clip/renorm.

    Distinct from ``rolling_window``: that re-normalizes against a trailing
    distribution and can amplify a sudden move; this damps noise directly.
    """

    def test_default_none_leaves_composite_unsmoothed(self) -> None:
        z = [3.0, -3.0, 3.0, -3.0]
        indicators = [IndicatorWeight(name="a", z=pl.Series(z), weight=1.0)]
        off = compute_composite_risk(indicators)
        explicit_off = compute_composite_risk(indicators, smoothing_window=None)
        assert off["composite_z"].to_list() == explicit_off["composite_z"].to_list()
        assert off["composite_z"].to_list() == z

    def test_smoothing_damps_an_alternating_series(self) -> None:
        z = [3.0, -3.0] * 20
        indicators = [IndicatorWeight(name="a", z=pl.Series(z), weight=1.0)]
        result = compute_composite_risk(indicators, smoothing_window=10, smoothing_min_samples=5)
        last = result["composite_z"][-1]
        assert last is not None
        assert abs(last) < 1.0

    def test_smoothing_stays_within_plus_minus_3(self) -> None:
        z = [3.0] * 25 + [-3.0] * 25
        indicators = [IndicatorWeight(name="a", z=pl.Series(z), weight=1.0)]
        result = compute_composite_risk(indicators, smoothing_window=10, smoothing_min_samples=5)
        for v in result["composite_z"].drop_nulls().to_list():
            assert -3.0 <= v <= 3.0

    def test_warmup_rows_are_null_until_min_samples(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0] * 10), weight=1.0)]
        result = compute_composite_risk(indicators, smoothing_window=10, smoothing_min_samples=5)
        assert result["composite_z"][:4].to_list() == [None, None, None, None]
        assert result["composite_z"][4] is not None

    def test_min_samples_defaults_to_half_window_floored_at_20(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0] * 200), weight=1.0)]
        result = compute_composite_risk(indicators, smoothing_window=100)
        # default min_samples = max(20, 100 // 2) = 50
        assert result["composite_z"][48] is None
        assert result["composite_z"][49] is not None

    def test_smoothing_window_below_2_raises(self) -> None:
        indicators = [IndicatorWeight(name="a", z=pl.Series([1.0, 2.0, 3.0]), weight=1.0)]
        with pytest.raises(ValueError, match="smoothing_window must be >= 2"):
            compute_composite_risk(indicators, smoothing_window=1)

    def test_smoothing_composes_with_rolling_renormalization(self) -> None:
        # Smoothing applies to the already rolling-renormalized composite_z,
        # not to the pre-renormalization weighted average.
        z = [1.0] * 60
        indicators = [IndicatorWeight(name="a", z=pl.Series(z), weight=1.0)]
        both = compute_composite_risk(
            indicators,
            rolling_window=20,
            rolling_min_samples=10,
            smoothing_window=10,
            smoothing_min_samples=5,
        )
        rolling_only = compute_composite_risk(indicators, rolling_window=20, rolling_min_samples=10)
        # A flat input renormalizes to a flat (null-sigma-floored) series, so
        # smoothing a flat series is a no-op — this just proves both stages ran
        # without erroring and produced finite output.
        assert both["composite_z"][-1] is not None
        assert rolling_only["composite_z"][-1] is not None
