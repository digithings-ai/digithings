"""Baseline-relative evaluation vs the naive risk50-linear curve (post-mortem follow-up)."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.baseline_evaluator import (
    compare_to_baseline,
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics

pytestmark = pytest.mark.unit


def _v_cycle(
    n_cheap: int = 40, n_mid: int = 30, n_rich: int = 40
) -> tuple[pl.Series, pl.Series, pl.Series]:
    """Price dips then rips; risk is cheap at the trough and rich at the peak."""
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
    shifted = [date(2022, 1, 1) + timedelta(days=i) for i in range(n_cheap + n_mid)]
    shifted.extend(date(2025, 6, 1) + timedelta(days=i) for i in range(n_rich))
    return pl.Series("date", shifted, dtype=pl.Date), pl.Series(prices), pl.Series(risks)


class TestCompareToBaseline:
    def test_a_shape_timed_to_the_cycle_beats_the_naive_baseline(self) -> None:
        dates, prices, risk = _v_cycle()
        good = SdcaCurveShape(
            buy_max_rate=20.0,
            buy_knee_risk=12.0,
            sell_knee_risk=88.0,
            sell_max_rate=20.0,
            buy_curvature=1.0,
            sell_curvature=1.0,
        )
        result = compare_to_baseline(dates, prices, risk, good, 1000.0)
        assert result.beats_baseline is True
        assert result.candidate.total_return_pct > result.baseline.total_return_pct
        assert result.candidate.risk_adjusted_return > result.baseline.risk_adjusted_return

    def test_a_nearly_flat_shape_underperforms_the_naive_baseline(self) -> None:
        dates, prices, risk = _v_cycle()
        flat = SdcaCurveShape(
            buy_max_rate=0.5,
            buy_knee_risk=40.0,
            sell_knee_risk=60.0,
            sell_max_rate=0.5,
            buy_curvature=1.0,
            sell_curvature=1.0,
        )
        result = compare_to_baseline(dates, prices, risk, flat, 1000.0)
        assert result.beats_baseline is False
        assert result.candidate.total_return_pct < result.baseline.total_return_pct
        assert result.candidate.risk_adjusted_return < result.baseline.risk_adjusted_return

    def test_baseline_uses_candidates_own_buy_max_rate_by_default(self) -> None:
        dates, prices, risk = _v_cycle()
        shape = SdcaCurveShape(
            buy_max_rate=15.0,
            buy_knee_risk=25.0,
            sell_knee_risk=70.0,
            sell_max_rate=3.0,
            buy_curvature=1.0,
            sell_curvature=2.0,
        )
        result = compare_to_baseline(dates, prices, risk, shape, 1000.0)
        assert result.baseline.shape.buy_max_rate == pytest.approx(15.0)
        assert result.baseline.shape.sell_max_rate == pytest.approx(15.0)

    def test_explicit_baseline_max_rate_overrides_the_candidates_rate(self) -> None:
        dates, prices, risk = _v_cycle()
        shape = SdcaCurveShape(
            buy_max_rate=15.0,
            buy_knee_risk=25.0,
            sell_knee_risk=70.0,
            sell_max_rate=3.0,
            buy_curvature=1.0,
            sell_curvature=2.0,
        )
        result = compare_to_baseline(dates, prices, risk, shape, 1000.0, baseline_max_rate=4.0)
        assert result.baseline.shape.buy_max_rate == pytest.approx(4.0)
        assert result.baseline.shape.sell_max_rate == pytest.approx(4.0)


_HIDDEN = {
    "buy_max_rate": 8.0,
    "buy_knee_risk": 30.0,
    "sell_knee_risk": 70.0,
    "sell_max_rate": 6.0,
    "buy_curvature": 1.0,
    "sell_curvature": 2.0,
    "power_law_weight": 1.0,
    "m2_weight": 0.0,
}


def _dates(n: int = 200) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
    assert dates and prices and len(dates) == len(prices)
    return _ConstRails()


def _distance(shape: SdcaCurveShape, weight: float, m2_weight: float = 0.0) -> float:
    return (
        (shape.buy_max_rate - _HIDDEN["buy_max_rate"]) ** 2
        + ((shape.buy_knee_risk - _HIDDEN["buy_knee_risk"]) / 10.0) ** 2
        + ((shape.sell_knee_risk - _HIDDEN["sell_knee_risk"]) / 10.0) ** 2
        + (shape.sell_max_rate - _HIDDEN["sell_max_rate"]) ** 2
        + (weight - _HIDDEN["power_law_weight"]) ** 2
        + (m2_weight - _HIDDEN.get("m2_weight", 0.0)) ** 2
    )


def _evaluator(
    dates: list[date],
    prices: list[float],
    model: RiskModel,
    shape: SdcaCurveShape,
    power_law_weight: float,
    extra_indicators: object = None,
) -> SdcaTrialMetrics:
    assert isinstance(model, _ConstRails)
    extras = extra_indicators or []
    m2_w = 0.0
    for ind in extras:
        if getattr(ind, "name", "") == "m2":
            m2_w = float(ind.weight)
    vs_flat = 5.0 - _distance(shape, power_law_weight, m2_w) - 0.02 * len(dates)
    return SdcaTrialMetrics(
        vs_flat_dca_pct=vs_flat,
        vs_lump_pct=-1.0,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


class TestRunSdcaWalkForwardVsBaseline:
    """Synthetic evaluator scores exactly-``_HIDDEN`` highest; the naive
    risk50-linear baseline (knees ~50, curvature 1) sits far from ``_HIDDEN``
    (knees 30/70, sell_curvature 2), so a candidate matching ``_HIDDEN``
    must clear it under identical walk-forward folds.
    """

    def test_candidate_matching_the_hidden_optimum_beats_the_baseline(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        result = run_sdca_walk_forward_vs_baseline(
            dates,
            prices,
            _HIDDEN,
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="test",
        )
        assert result.beats_baseline_oos is True
        assert result.delta_mean_oos_vs_flat_dca_pct == pytest.approx(
            result.candidate.mean_oos_vs_flat_dca_pct - result.baseline.mean_oos_vs_flat_dca_pct
        )
        assert result.candidate.mean_oos_vs_flat_dca_pct > result.baseline.mean_oos_vs_flat_dca_pct

    def test_both_runs_share_identical_folds_and_holdout(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        result = run_sdca_walk_forward_vs_baseline(
            dates,
            prices,
            _HIDDEN,
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="test",
        )
        assert result.candidate.folds == result.baseline.folds
        assert result.candidate.holdout == result.baseline.holdout

    def test_baseline_keeps_the_candidates_indicator_weights_and_only_swaps_shape(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        result = run_sdca_walk_forward_vs_baseline(
            dates,
            prices,
            _HIDDEN,
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="test",
        )
        baseline_params = result.baseline.best_params
        assert baseline_params["power_law_weight"] == pytest.approx(_HIDDEN["power_law_weight"])
        assert baseline_params["m2_weight"] == pytest.approx(_HIDDEN["m2_weight"])
        # Shape is the naive linear ramp, not the hidden optimum's shape.
        assert baseline_params["buy_knee_risk"] == pytest.approx(49.9)
        assert baseline_params["sell_knee_risk"] == pytest.approx(50.1)
        assert baseline_params["buy_curvature"] == pytest.approx(1.0)
        assert baseline_params["sell_curvature"] == pytest.approx(1.0)
        assert baseline_params["buy_max_rate"] == pytest.approx(_HIDDEN["buy_max_rate"])

    def test_fold_weighting_threads_through_to_both_runs(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        result = run_sdca_walk_forward_vs_baseline(
            dates,
            prices,
            _HIDDEN,
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="test",
            fold_weighting="duration",
        )
        assert result.candidate.fold_weighting == "duration"
        assert result.baseline.fold_weighting == "duration"
