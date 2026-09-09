"""Tests for the composite-risk indicator vote (weighted z-score blend -> 0-100 risk)."""

from __future__ import annotations

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
