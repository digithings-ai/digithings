"""Walk-forward schedule, objective, and rails-leakage guards (#3174)."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    SdcaTrialMetrics,
    is_feasible,
    make_walk_forward_folds,
    max_drawdown_magnitude_pct,
    objective_score,
    params_are_valid,
    score_trial_on_folds,
    window_slice,
)

pytestmark = pytest.mark.unit


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        mid = [100.0] * n
        return pl.DataFrame({"low": [50.0] * n, "median": mid, "high": [200.0] * n})


class TestMakeWalkForwardFolds:
    def test_holdout_is_the_tail_and_never_in_folds(self) -> None:
        dates = _dates(60)
        folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
        assert holdout == (dates[48], dates[-1])
        for fold in folds:
            assert fold.oos_end < holdout[0]
            assert fold.is_end < fold.oos_start

    def test_expanding_is_starts_at_first_date(self) -> None:
        dates = _dates(60)
        folds, _ = make_walk_forward_folds(dates)
        assert all(f.is_start == dates[0] for f in folds)
        assert folds[0].is_end <= folds[1].is_end <= folds[2].is_end

    def test_too_few_dates_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 20"):
            make_walk_forward_folds(_dates(10))


class TestObjective:
    def test_infeasible_below_capital_floor_is_neg_inf(self) -> None:
        obj = SdcaOptimizeObjective(capital_deployed_floor_pct=10.0, max_drawdown_cap_pct=50.0)
        metrics = SdcaTrialMetrics(
            vs_flat_dca_pct=12.0,
            vs_lump_pct=-3.0,
            capital_deployed_pct=5.0,
            max_drawdown_pct=10.0,
        )
        assert not is_feasible(metrics, obj)
        assert objective_score(metrics, obj) == float("-inf")

    def test_feasible_score_is_vs_flat_dca_not_vs_lump(self) -> None:
        obj = SdcaOptimizeObjective()
        metrics = SdcaTrialMetrics(
            vs_flat_dca_pct=4.0,
            vs_lump_pct=99.0,
            capital_deployed_pct=40.0,
            max_drawdown_pct=15.0,
        )
        assert objective_score(metrics, obj) == pytest.approx(4.0)

    def test_drawdown_cap_rejects(self) -> None:
        obj = SdcaOptimizeObjective(max_drawdown_cap_pct=20.0)
        metrics = SdcaTrialMetrics(
            vs_flat_dca_pct=8.0,
            vs_lump_pct=0.0,
            capital_deployed_pct=50.0,
            max_drawdown_pct=21.0,
        )
        assert not is_feasible(metrics, obj)


class TestParamsAndWindow:
    def test_empty_dead_zone_is_invalid(self) -> None:
        assert not params_are_valid(
            {
                "buy_max_rate": 10,
                "buy_knee_risk": 50,
                "sell_knee_risk": 50,
                "sell_max_rate": 5,
                "buy_curvature": 1,
                "sell_curvature": 1,
            }
        )

    def test_window_slice_inclusive(self) -> None:
        dates = _dates(5)
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        d, p = window_slice(dates, prices, dates[1], dates[3])
        assert d == dates[1:4]
        assert p == [2.0, 3.0, 4.0]

    def test_drawdown_magnitude_is_percent_not_fraction(self) -> None:
        # 100 → 80 is a 20% drawdown, not 0.20.
        assert max_drawdown_magnitude_pct([100.0, 90.0, 80.0, 85.0]) == pytest.approx(20.0)


class TestRailsRefitPerFold:
    def test_fitter_never_sees_oos_or_holdout_dates(self) -> None:
        dates = _dates(60)
        prices = [100.0 + i for i in range(60)]
        folds, holdout = make_walk_forward_folds(dates)
        seen: list[tuple[date, date]] = []

        def fitter(d: list[date], p: list[float]) -> RiskModel:
            seen.append((d[0], d[-1]))
            assert len(d) == len(p)
            return _ConstRails()

        def evaluator(
            d: list[date],
            p: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            assert isinstance(model, _ConstRails)
            assert 0.5 <= weight <= 1.0
            assert shape.buy_knee_risk < shape.sell_knee_risk
            return SdcaTrialMetrics(
                vs_flat_dca_pct=1.0,
                vs_lump_pct=0.0,
                capital_deployed_pct=40.0,
                max_drawdown_pct=10.0,
            )

        params = {
            "buy_max_rate": 10.0,
            "buy_knee_risk": 35.0,
            "sell_knee_risk": 80.0,
            "sell_max_rate": 10.0,
            "buy_curvature": 1.0,
            "sell_curvature": 2.0,
            "valuation_weight": 1.0,
        }
        scores = score_trial_on_folds(
            params, dates, prices, folds, fitter, evaluator, SdcaOptimizeObjective()
        )
        assert len(scores) == len(folds)
        assert len(seen) == len(folds)
        for fold, window in zip(folds, seen, strict=True):
            assert window == (fold.is_start, fold.is_end)
            assert window[1] < fold.oos_start
            assert window[1] < holdout[0]
