"""Tests for AccumDistCurve — 21-node piecewise-linear accumulation/distribution curve."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.curve import AccumDistCurve

pytestmark = pytest.mark.unit


class TestAccumDistCurveDefaultNodes:
    def test_value_at_risk_0_is_10(self) -> None:
        curve = AccumDistCurve()
        assert curve.value_at_risk(0.0) == pytest.approx(10.0)

    def test_value_at_risk_100_is_minus_10(self) -> None:
        curve = AccumDistCurve()
        assert curve.value_at_risk(100.0) == pytest.approx(-10.0)

    def test_value_at_risk_50_is_0(self) -> None:
        curve = AccumDistCurve()
        assert curve.value_at_risk(50.0) == pytest.approx(0.0)

    def test_interpolates_between_20_and_25(self) -> None:
        curve = AccumDistCurve()
        # node(20)=6.5, node(25)=4.0 -> at 22.5, halfway: 5.25
        assert curve.value_at_risk(22.5) == pytest.approx(5.25)

    def test_clamps_risk_below_0(self) -> None:
        curve = AccumDistCurve()
        assert curve.value_at_risk(-15.0) == pytest.approx(10.0)

    def test_clamps_risk_above_100(self) -> None:
        curve = AccumDistCurve()
        assert curve.value_at_risk(150.0) == pytest.approx(-10.0)


class TestAccumDistCurveConfigurable:
    def test_rejects_wrong_node_count(self) -> None:
        with pytest.raises(ValueError, match="21 nodes"):
            AccumDistCurve(nodes=[1.0, 2.0, 3.0])

    def test_accepts_custom_long_only_curve(self) -> None:
        all_positive = tuple(5.0 for _ in range(21))
        curve = AccumDistCurve(nodes=all_positive)
        for risk in (0.0, 25.0, 50.0, 75.0, 100.0):
            assert curve.value_at_risk(risk) == pytest.approx(5.0)

    def test_accepts_custom_signed_distribution_curve(self) -> None:
        nodes = tuple(10.0 - i for i in range(21))  # 10.0 down to -10.0
        curve = AccumDistCurve(nodes=nodes)
        assert curve.value_at_risk(0.0) == pytest.approx(10.0)
        assert curve.value_at_risk(100.0) == pytest.approx(-10.0)

    def test_rejects_nan_node(self) -> None:
        nodes = (float("nan"),) + tuple(0.0 for _ in range(20))
        with pytest.raises(ValueError, match="finite"):
            AccumDistCurve(nodes=nodes)

    def test_rejects_infinite_node(self) -> None:
        nodes = (float("inf"),) + tuple(0.0 for _ in range(20))
        with pytest.raises(ValueError, match="finite"):
            AccumDistCurve(nodes=nodes)


class TestAccumDistCurveNonFiniteRisk:
    def test_rejects_nan_risk(self) -> None:
        curve = AccumDistCurve()
        with pytest.raises(ValueError, match="finite"):
            curve.value_at_risk(float("nan"))

    def test_rejects_positive_infinite_risk(self) -> None:
        curve = AccumDistCurve()
        with pytest.raises(ValueError, match="finite"):
            curve.value_at_risk(float("inf"))

    def test_rejects_negative_infinite_risk(self) -> None:
        curve = AccumDistCurve()
        with pytest.raises(ValueError, match="finite"):
            curve.value_at_risk(float("-inf"))
