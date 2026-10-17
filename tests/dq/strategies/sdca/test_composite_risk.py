"""Tests for the composite-risk indicator vote (weighted z-score blend -> 0-100 risk)."""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.composite_risk import (
    IndicatorWeight,
    causal_ema_smooth,
    compute_composite_risk,
)

pytestmark = pytest.mark.unit


class TestCausalEmaSmooth:
    def test_is_causal_later_spike_does_not_change_early_output(self) -> None:
        base = [1.0] * 20
        s1 = causal_ema_smooth(pl.Series(base), half_life=3.0)
        spiked = base.copy()
        spiked[-1] = 100.0
        s2 = causal_ema_smooth(pl.Series(spiked), half_life=3.0)
        assert s1[5] == pytest.approx(s2[5])

    def test_smooths_a_step_into_a_ramp(self) -> None:
        step = [0.0] * 10 + [3.0] * 20
        smoothed = causal_ema_smooth(pl.Series(step), half_life=3.0).to_list()
        # Immediately after the step, output has not fully jumped yet...
        assert 0.0 < smoothed[10] < 3.0
        # ...and converges back to the new level given enough halflives.
        assert smoothed[-1] == pytest.approx(3.0, abs=0.05)

    def test_constant_series_is_unchanged(self) -> None:
        smoothed = causal_ema_smooth(pl.Series([2.0] * 15), half_life=4.0)
        for v in smoothed.to_list():
            assert v == pytest.approx(2.0)

    def test_non_positive_half_life_raises(self) -> None:
        with pytest.raises(ValueError, match="half_life must be > 0"):
            causal_ema_smooth(pl.Series([1.0, 2.0]), half_life=0.0)


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

    def test_zero_weight_null_member_does_not_null_the_blend(self) -> None:
        """``0 × null`` must not wipe a solo extra. Omit unused members."""
        indicators = [
            IndicatorWeight(name="valuation", z=pl.Series([None, 1.0]), weight=0.0),
            IndicatorWeight(name="m2", z=pl.Series([3.0, 3.0]), weight=1.0),
        ]
        result = compute_composite_risk(indicators)
        assert result["composite_z"][0] == pytest.approx(3.0)
        assert result["risk"][0] == pytest.approx(0.0)
        assert result["composite_z"][1] == pytest.approx(3.0)
