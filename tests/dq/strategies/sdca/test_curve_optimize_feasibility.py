"""Feasibility-aware curve scoring: penalty behavior only (#3174 follow-up).

Focused on ``score_shape_on_index_feasibility_aware`` and its penalty band --
not a re-test of ``score_shape_on_index`` / ``fill_concentration`` /
``search_wide_knee_curve``, which ``test_curve_optimize.py`` already covers
and which this module does not modify.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_optimize import score_shape_on_index
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    CAPITAL_DEPLOYED_COMFORT_PCT,
    CAPITAL_DEPLOYED_FLOOR_PCT,
    CAPITAL_DEPLOYED_UPPER_PCT,
    INFEASIBLE_SCORE,
    MAX_DRAWDOWN_CAP_PCT,
    MAX_DRAWDOWN_COMFORT_PCT,
    _capital_deployed_penalty,
    _drawdown_penalty,
    score_shape_on_index_feasibility_aware,
    search_wide_knee_curve_feasibility_aware,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.walk_forward import SdcaOptimizeObjective

pytestmark = pytest.mark.unit


def _shape(**overrides: float) -> SdcaCurveShape:
    params: dict[str, float] = {
        "buy_max_rate": 3.0,
        "buy_knee_risk": 25.0,
        "sell_knee_risk": 70.0,
        "sell_max_rate": 3.0,
        "buy_curvature": 1.0,
        "sell_curvature": 2.0,
    }
    params.update(overrides)
    return SdcaCurveShape(**params)


def _v_cycle(
    n_cheap: int = 40, n_mid: int = 30, n_rich: int = 40
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """Price dips then rips; risk is cheap at the trough and rich at the peak.

    Crosses the default shape's buy (25) and sell (70) knees, so it trades
    normally and lands well above ``CAPITAL_DEPLOYED_COMFORT_PCT``.
    """
    prices: list[float] = []
    risks: list[float] = []
    for i in range(n_cheap):
        t = i / max(n_cheap - 1, 1)
        prices.append(50.0 - 10.0 * t)
        risks.append(5.0 + 7.0 * t)
    for i in range(n_mid):
        t = i / max(n_mid - 1, 1)
        prices.append(40.0 + 40.0 * t)
        risks.append(40.0 + 20.0 * t)
    for i in range(n_rich):
        t = i / max(n_rich - 1, 1)
        prices.append(80.0 + 40.0 * t)
        risks.append(80.0 + 15.0 * t)
    # Rich window lands in 2025 so CurveOptimizeGates' default
    # require_2025_sells doesn't reject an otherwise-healthy shape (mirrors
    # test_curve_optimize.py's _v_cycle).
    shifted = [date(2022, 1, 1) + timedelta(days=i) for i in range(n_cheap + n_mid)]
    shifted.extend(date(2025, 6, 1) + timedelta(days=i) for i in range(n_rich))
    return pl.Series("date", shifted, dtype=pl.Date), pl.Series(prices), pl.Series(risks)


def _dead_zone(n: int = 120) -> tuple[pl.Series, pl.Series, pl.Series]:
    """Risk pinned inside the default shape's dead zone (25-70) the whole run.

    Never crosses a knee, so the default shape never buys or sells --
    capital_deployed_pct is exactly 0%.
    """
    dates = pl.Series(
        "date", [date(2022, 1, 1) + timedelta(days=i) for i in range(n)], dtype=pl.Date
    )
    prices = pl.Series([100.0 + i for i in range(n)])
    risk = pl.Series([50.0] * n)
    return dates, prices, risk


def _dip_cycle(
    dip_frac: float, n_pre: int = 40, n_dip: int = 20, n_flat: int = 20, n_rich: int = 40
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """Mild pre-decline, then a dip of ``dip_frac`` off a $90 base, then a rip.

    Calibrated (see the 2026-09-24 recalibration round 2's drawdown-gate
    diagnostic sweep, re-run after ``MAX_DRAWDOWN_CAP_PCT``/
    ``MAX_DRAWDOWN_COMFORT_PCT`` moved from 30.0/25.0 to 50.0/45.0) so that
    ``dip_frac`` maps monotonically onto ``base.max_drawdown_pct`` for a
    given ``n_pre``. ``dip_frac`` alone tops out well short of the new cap
    -- capital already deployed pre-dip is the ceiling on how much of the
    portfolio can draw down, since BTC value can't go below zero, so
    ``n_pre`` (how many buy-favorable days run before the dip, deploying
    more capital) is the lever that raises the achievable ceiling, not a
    deeper ``dip_frac`` alone. With the default ``n_pre=40`` and
    ``_shape(buy_max_rate=15.0)``: 0.50 -> ~24.4% (below comfort, capital
    deployed ~43%). Widening ``n_pre`` to 60 with ``dip_frac=0.78`` ->
    ~47.6% (soft zone, capital deployed ~57%); ``n_pre=80`` with
    ``dip_frac=0.80`` -> ~57.3% (comfortably above the 50% cap, capital
    deployed ~68%) -- both stay well clear of
    ``CAPITAL_DEPLOYED_COMFORT_PCT`` (15%), isolating the drawdown gate
    from the capital-deployed gate.
    """
    prices: list[float] = []
    risks: list[float] = []
    for i in range(n_pre):
        t = i / max(n_pre - 1, 1)
        prices.append(100.0 - 10.0 * t)
        risks.append(20.0 + 5.0 * t)
    p0 = 90.0
    for i in range(n_dip):
        t = i / max(n_dip - 1, 1)
        prices.append(p0 - (p0 * dip_frac) * t)
        risks.append(25.0 + 10.0 * t)
    pbot = p0 * (1 - dip_frac)
    for i in range(n_flat):
        t = i / max(n_flat - 1, 1)
        prices.append(pbot + 3.0 * t)
        risks.append(35.0 + 10.0 * t)
    for i in range(n_rich):
        t = i / max(n_rich - 1, 1)
        prices.append(pbot + 3.0 + 70.0 * t)
        risks.append(45.0 + 40.0 * t)
    # Rich window lands in 2025, same require_2025_sells rationale as _v_cycle.
    shifted = [date(2022, 1, 1) + timedelta(days=i) for i in range(n_pre + n_dip + n_flat)]
    shifted.extend(date(2025, 6, 1) + timedelta(days=i) for i in range(n_rich))
    return pl.Series("date", shifted, dtype=pl.Date), pl.Series(prices), pl.Series(risks)


class TestCapitalDeployedPenalty:
    """Direct tests of the ``(floor, comfort, upper)`` band, edge to edge."""

    def test_floor_matches_walk_forward_gate_default(self) -> None:
        assert CAPITAL_DEPLOYED_FLOOR_PCT == SdcaOptimizeObjective().capital_deployed_floor_pct

    def test_below_floor_hard_rejects(self) -> None:
        score, reject = _capital_deployed_penalty(CAPITAL_DEPLOYED_FLOOR_PCT - 0.01, 5.0)
        assert reject is True
        assert score == INFEASIBLE_SCORE

    def test_negative_net_seller_hard_rejects(self) -> None:
        score, reject = _capital_deployed_penalty(-35.0, 5.0)
        assert reject is True
        assert score == INFEASIBLE_SCORE

    def test_above_upper_bound_hard_rejects(self) -> None:
        score, reject = _capital_deployed_penalty(CAPITAL_DEPLOYED_UPPER_PCT + 0.01, 5.0)
        assert reject is True
        assert score == INFEASIBLE_SCORE

    def test_at_floor_exactly_is_feasible_but_penalized(self) -> None:
        score, reject = _capital_deployed_penalty(CAPITAL_DEPLOYED_FLOOR_PCT, 5.0)
        assert reject is False
        assert score < 5.0

    def test_soft_zone_penalty_shrinks_toward_comfort_line(self) -> None:
        near_floor_score, _ = _capital_deployed_penalty(CAPITAL_DEPLOYED_FLOOR_PCT + 0.5, 5.0)
        near_comfort_score, _ = _capital_deployed_penalty(CAPITAL_DEPLOYED_COMFORT_PCT - 0.5, 5.0)
        assert near_floor_score < near_comfort_score < 5.0

    def test_at_and_above_comfort_line_is_unpenalized(self) -> None:
        at_comfort, reject_a = _capital_deployed_penalty(CAPITAL_DEPLOYED_COMFORT_PCT, 5.0)
        well_above, reject_b = _capital_deployed_penalty(CAPITAL_DEPLOYED_UPPER_PCT, 5.0)
        assert reject_a is False
        assert reject_b is False
        assert at_comfort == pytest.approx(5.0)
        assert well_above == pytest.approx(5.0)


class TestDrawdownPenalty:
    """Direct tests of the ``(comfort, cap)`` band, edge to edge."""

    def test_below_comfort_is_unpenalized(self) -> None:
        score, reject = _drawdown_penalty(MAX_DRAWDOWN_COMFORT_PCT - 5.0, 5.0)
        assert reject is False
        assert score == pytest.approx(5.0)

    def test_at_comfort_exactly_is_unpenalized(self) -> None:
        score, reject = _drawdown_penalty(MAX_DRAWDOWN_COMFORT_PCT, 5.0)
        assert reject is False
        assert score == pytest.approx(5.0)

    def test_just_above_comfort_is_penalized_but_feasible(self) -> None:
        score, reject = _drawdown_penalty(MAX_DRAWDOWN_COMFORT_PCT + 0.5, 5.0)
        assert reject is False
        assert score < 5.0

    def test_soft_zone_penalty_grows_toward_cap_line(self) -> None:
        near_comfort_score, _ = _drawdown_penalty(MAX_DRAWDOWN_COMFORT_PCT + 0.5, 5.0)
        near_cap_score, _ = _drawdown_penalty(MAX_DRAWDOWN_CAP_PCT - 0.5, 5.0)
        assert near_cap_score < near_comfort_score < 5.0

    def test_at_cap_exactly_is_feasible_but_fully_penalized(self) -> None:
        score, reject = _drawdown_penalty(MAX_DRAWDOWN_CAP_PCT, 5.0)
        assert reject is False
        # Full soft-zone deduction (overage_frac == 1.0) but not yet rejected.
        assert score == pytest.approx(0.0)

    def test_above_cap_hard_rejects(self) -> None:
        score, reject = _drawdown_penalty(MAX_DRAWDOWN_CAP_PCT + 0.01, 5.0)
        assert reject is True
        assert score == INFEASIBLE_SCORE


class TestScoreShapeOnIndexFeasibilityAware:
    def test_zero_capital_deployed_scores_materially_worse_than_unpenalized(self) -> None:
        dates, prices, risk = _dead_zone()
        shape = _shape()
        base = score_shape_on_index(dates, prices, risk, shape, 1000.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, shape, 1000.0)

        assert aware.capital_deployed_pct == pytest.approx(0.0)
        # Unpenalized score is unaffected (no trades -> ~0 return, ~0 drawdown).
        assert aware.risk_adjusted_return == pytest.approx(base.risk_adjusted_return)
        # The feasibility-aware score is not just lower, it is hard-rejected.
        assert aware.capital_deployed_reject is True
        assert aware.feasibility_adjusted_score == INFEASIBLE_SCORE
        assert aware.feasibility_adjusted_score < aware.risk_adjusted_return - 100.0

    def test_healthy_capital_deployment_scores_about_the_same(self) -> None:
        dates, prices, risk = _v_cycle()
        # A faster buy rate than the conservative default (3%/day) so the
        # run ends comfortably above CAPITAL_DEPLOYED_COMFORT_PCT, not just
        # over the bare floor.
        shape = _shape(buy_max_rate=15.0)
        base = score_shape_on_index(dates, prices, risk, shape, 1000.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, shape, 1000.0)

        assert aware.capital_deployed_pct > CAPITAL_DEPLOYED_COMFORT_PCT, (
            f"fixture drifted below the comfort line "
            f"({aware.capital_deployed_pct}); this test needs deployment "
            "comfortably above CAPITAL_DEPLOYED_COMFORT_PCT to be meaningful"
        )
        assert aware.capital_deployed_reject is False
        assert aware.risk_adjusted_return == pytest.approx(base.risk_adjusted_return)
        assert aware.feasibility_adjusted_score == pytest.approx(base.risk_adjusted_return)

    def test_existing_reject_reasons_still_hard_reject_regardless_of_capital_deployed(
        self,
    ) -> None:
        dates, prices, risk = _v_cycle()
        long_only = _shape(sell_max_rate=0.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, long_only, 1000.0)

        assert aware.base.feasible is False
        assert "long_only" in aware.base.reject_reasons
        assert aware.capital_deployed_reject is True
        assert aware.feasibility_adjusted_score == INFEASIBLE_SCORE

    def test_does_not_mutate_score_shape_on_index_return_type(self) -> None:
        dates, prices, risk = _v_cycle()
        shape = _shape()
        base = score_shape_on_index(dates, prices, risk, shape, 1000.0)
        assert not hasattr(base, "capital_deployed_pct")
        assert not hasattr(base, "feasibility_adjusted_score")

    def test_below_drawdown_comfort_is_unpenalized_by_drawdown_gate(self) -> None:
        dates, prices, risk = _dip_cycle(0.50)
        shape = _shape(buy_max_rate=15.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, shape, 1000.0)

        assert aware.base.max_drawdown_pct < MAX_DRAWDOWN_COMFORT_PCT, (
            f"fixture drifted above the comfort line "
            f"({aware.base.max_drawdown_pct}); this test needs drawdown "
            "comfortably below MAX_DRAWDOWN_COMFORT_PCT to be meaningful"
        )
        assert aware.capital_deployed_reject is False
        assert aware.drawdown_reject is False
        assert aware.feasibility_adjusted_score == pytest.approx(aware.risk_adjusted_return)

    def test_soft_zone_drawdown_penalty_isolated_from_capital_deployed_gate(self) -> None:
        dates, prices, risk = _dip_cycle(0.78, n_pre=60)
        shape = _shape(buy_max_rate=15.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, shape, 1000.0)

        assert MAX_DRAWDOWN_COMFORT_PCT < aware.base.max_drawdown_pct < MAX_DRAWDOWN_CAP_PCT, (
            f"fixture drifted out of the soft zone "
            f"({aware.base.max_drawdown_pct}); this test needs drawdown "
            "strictly between comfort and cap to be meaningful"
        )
        assert aware.capital_deployed_reject is False
        assert aware.drawdown_reject is False
        expected_score, expected_reject = _drawdown_penalty(
            aware.base.max_drawdown_pct, aware.risk_adjusted_return
        )
        assert expected_reject is False
        assert aware.feasibility_adjusted_score == pytest.approx(expected_score)
        assert aware.feasibility_adjusted_score < aware.risk_adjusted_return
        assert aware.feasibility_adjusted_score > INFEASIBLE_SCORE

    def test_hard_reject_above_drawdown_cap_isolated_from_capital_deployed_gate(self) -> None:
        dates, prices, risk = _dip_cycle(0.80, n_pre=80)
        shape = _shape(buy_max_rate=15.0)
        aware = score_shape_on_index_feasibility_aware(dates, prices, risk, shape, 1000.0)

        assert aware.base.max_drawdown_pct > MAX_DRAWDOWN_CAP_PCT, (
            f"fixture drifted below the cap line ({aware.base.max_drawdown_pct}); "
            "this test needs drawdown comfortably above MAX_DRAWDOWN_CAP_PCT "
            "to be meaningful"
        )
        assert aware.base.feasible is True
        assert aware.capital_deployed_reject is False
        assert aware.drawdown_reject is True
        assert aware.feasibility_adjusted_score == INFEASIBLE_SCORE


class TestSearchWideKneeCurveFeasibilityAware:
    def test_runs_and_avoids_a_hard_rejected_best(self) -> None:
        dates, prices, risk = _v_cycle()
        result = search_wide_knee_curve_feasibility_aware(
            dates,
            prices,
            risk,
            initial_cash=1000.0,
            n_random=20,
            seed=7,
            include_grid=False,
        )
        assert result.num_evaluations > 0
        assert result.best.capital_deployed_reject is False
        assert result.best.feasibility_adjusted_score > INFEASIBLE_SCORE
