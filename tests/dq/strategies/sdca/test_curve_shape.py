"""Tests for SdcaCurveShape — parametric generator for the 21-node runtime curve (#3169)."""

from __future__ import annotations

import itertools

import pytest
from digiquant.strategies.sdca.curve import RISK_NODES, AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape

pytestmark = pytest.mark.unit


def _shape(**overrides: float) -> SdcaCurveShape:
    params: dict[str, float] = {
        "buy_max_rate": 10.0,
        "buy_knee_risk": 35.0,
        "sell_knee_risk": 80.0,
        "sell_max_rate": 10.0,
        "buy_curvature": 1.0,
        "sell_curvature": 1.0,
    }
    params.update(overrides)
    return SdcaCurveShape(**params)


class TestSdcaCurveShapeNodes:
    def test_to_nodes_has_21_and_is_accepted_by_accum_dist_curve(self) -> None:
        nodes = _shape().to_nodes()
        assert len(nodes) == 21
        curve = AccumDistCurve(nodes)
        assert curve.nodes == nodes

    def test_risk_0_is_buy_max_rate(self) -> None:
        assert _shape(buy_max_rate=7.5).rate_at(0.0) == pytest.approx(7.5)

    def test_risk_100_is_minus_sell_max_rate(self) -> None:
        assert _shape(sell_max_rate=4.0).rate_at(100.0) == pytest.approx(-4.0)

    def test_dead_zone_is_exactly_zero(self) -> None:
        shape = _shape(buy_knee_risk=30.0, sell_knee_risk=70.0)
        for risk in (30.0, 40.0, 50.0, 70.0):
            assert shape.rate_at(risk) == pytest.approx(0.0)

    def test_linear_buy_ramps_to_zero_at_knee(self) -> None:
        shape = _shape(buy_max_rate=10.0, buy_knee_risk=40.0, buy_curvature=1.0)
        assert shape.rate_at(20.0) == pytest.approx(5.0)

    def test_curvature_gt_1_is_back_loaded_toward_extreme(self) -> None:
        linear = _shape(buy_curvature=1.0).rate_at(10.0)
        curved = _shape(buy_curvature=2.0).rate_at(10.0)
        # Mid-span of the buy side: t=(35-10)/35≈0.71; 0.71^2 < 0.71 so curved
        # is smaller until the extreme — back-loaded.
        assert curved < linear

    def test_long_only_shape_never_sells(self) -> None:
        nodes = _shape(sell_knee_risk=100.0, sell_max_rate=0.0).to_nodes()
        assert all(n >= 0.0 for n in nodes)
        AccumDistCurve(nodes)


class TestSdcaCurveShapeConstruction:
    def test_rejects_empty_dead_zone(self) -> None:
        with pytest.raises(ValueError, match="dead zone"):
            _shape(buy_knee_risk=50.0, sell_knee_risk=50.0)

    def test_rejects_inverted_dead_zone(self) -> None:
        with pytest.raises(ValueError, match="dead zone"):
            _shape(buy_knee_risk=80.0, sell_knee_risk=20.0)

    def test_rejects_sell_rate_above_100(self) -> None:
        with pytest.raises(ValueError):
            _shape(sell_max_rate=100.1)

    def test_rejects_buy_rate_above_100(self) -> None:
        with pytest.raises(ValueError):
            _shape(buy_max_rate=101.0)

    def test_rejects_curvature_below_1(self) -> None:
        with pytest.raises(ValueError):
            _shape(buy_curvature=0.5)

    def test_rejects_sell_without_room_above_knee(self) -> None:
        with pytest.raises(ValueError, match="sell_knee_risk"):
            _shape(sell_knee_risk=100.0, sell_max_rate=10.0)


class TestSdcaCurveShapePropertySweep:
    """Parameter sweep: every valid combo satisfies sign, monotonicity, dead zone."""

    def test_invariants_across_parameter_space(self) -> None:
        buy_max = (0.5, 10.0, 100.0)
        buy_knees = (5.0, 25.0, 40.0)
        sell_knees = (50.0, 80.0, 99.0)
        sell_max = (0.0, 10.0, 100.0)
        curvatures = (1.0, 1.5, 3.0)
        n_ok = 0
        for bmax, bk, sk, smax, bc, sc in itertools.product(
            buy_max, buy_knees, sell_knees, sell_max, curvatures, curvatures
        ):
            if not (bk < sk):
                continue
            if smax > 0.0 and sk >= 100.0:
                continue
            shape = SdcaCurveShape(
                buy_max_rate=bmax,
                buy_knee_risk=bk,
                sell_knee_risk=sk,
                sell_max_rate=smax,
                buy_curvature=bc,
                sell_curvature=sc,
            )
            nodes = shape.to_nodes()
            assert len(nodes) == len(RISK_NODES)
            AccumDistCurve(nodes)
            for risk, node in zip(RISK_NODES, nodes, strict=True):
                if risk < bk:
                    assert node > 0.0
                elif risk <= sk:
                    assert node == pytest.approx(0.0)
                else:
                    if smax > 0.0:
                        assert node < 0.0
                    else:
                        assert node == pytest.approx(0.0)
            assert all(nodes[i] <= nodes[i - 1] + 1e-12 for i in range(1, len(nodes)))
            n_ok += 1
        assert n_ok >= 100
