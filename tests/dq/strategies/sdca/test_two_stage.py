"""Two-stage SDCA fit: freeze Stage A weights, search curve, persist both variants."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca import two_stage as two_stage_mod
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import SDCA_SHAPE_DEFAULTS
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.two_stage import (
    SdcaTwoStageProvenance,
    freeze_weight_params,
    persist_two_stage,
    run_stage_b_frozen,
    stage_b_trials,
)
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics

pytestmark = pytest.mark.unit


def _dates(n: int = 60) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
    assert dates and prices
    return _ConstRails()


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
    rsi_w = 0.0
    for ind in extras:
        if getattr(ind, "name", "") == "weekly_rsi":
            rsi_w = float(ind.weight)
    vs_flat = (
        8.0
        - abs(shape.buy_max_rate - 8.0)
        - abs(shape.buy_knee_risk - 30.0) / 10.0
        - abs(rsi_w - 0.4)
        - 0.01 * len(dates)
    )
    return SdcaTrialMetrics(
        vs_flat_dca_pct=vs_flat,
        vs_lump_pct=-1.0,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


class TestFreezeAndStageBTrials:
    def test_freeze_emits_all_weight_keys(self) -> None:
        w = SdcaCompositeWeights(power_law=0.6, weekly_rsi=0.4)
        frozen = freeze_weight_params(w)
        assert frozen["power_law_weight"] == pytest.approx(0.6)
        assert frozen["weekly_rsi_weight"] == pytest.approx(0.4)
        assert frozen["weekly_macd_weight"] == pytest.approx(0.0)
        assert frozen["sma_band_weight"] == pytest.approx(0.0)

    def test_stage_b_trials_hold_weights_fixed(self) -> None:
        w = SdcaCompositeWeights(power_law=0.7, weekly_rsi=0.3)
        trials = stage_b_trials(
            w,
            [
                {**SDCA_SHAPE_DEFAULTS, "buy_max_rate": 5.0},
                {**SDCA_SHAPE_DEFAULTS, "buy_max_rate": 12.0},
            ],
        )
        assert len(trials) == 2
        assert {t["buy_max_rate"] for t in trials} == {5.0, 12.0}
        assert all(t["weekly_rsi_weight"] == pytest.approx(0.3) for t in trials)
        assert all(t["power_law_weight"] == pytest.approx(0.7) for t in trials)


class TestStageBFrozenSearch:
    def test_picks_closer_curve_with_frozen_weights(self) -> None:
        dates = _dates()
        prices = [100.0 + i for i in range(len(dates))]
        weights = SdcaCompositeWeights(power_law=0.6, weekly_rsi=0.4)
        extra_z = {"weekly_rsi": [0.0] * len(dates)}
        hidden = {
            **SDCA_SHAPE_DEFAULTS,
            "buy_max_rate": 8.0,
            "buy_knee_risk": 30.0,
            **freeze_weight_params(weights),
        }
        worse = {
            **SDCA_SHAPE_DEFAULTS,
            "buy_max_rate": 20.0,
            "buy_knee_risk": 15.0,
            **freeze_weight_params(weights),
        }
        result = run_stage_b_frozen(
            dates,
            prices,
            [worse, hidden],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
            extra_z=extra_z,
        )
        assert result.best_params["buy_max_rate"] == pytest.approx(8.0)
        assert result.best_params["weekly_rsi_weight"] == pytest.approx(0.4)
        assert result.best_params["power_law_weight"] == pytest.approx(0.6)


class TestCurveSimEvaluator:
    def test_returns_finite_dca_metrics(self) -> None:
        dates = _dates(40)
        prices = [100.0 + 0.5 * i for i in range(len(dates))]
        shape = SdcaCurveShape(
            buy_max_rate=10.0,
            buy_knee_risk=35.0,
            sell_knee_risk=80.0,
            sell_max_rate=5.0,
            buy_curvature=1.0,
            sell_curvature=2.0,
        )
        metrics = evaluate_sdca_trial_curve_sim(
            dates, prices, _ConstRails(), shape, 1.0, extra_indicators=[]
        )
        assert isinstance(metrics.vs_flat_dca_pct, float)
        assert metrics.capital_deployed_pct >= 0.0
        assert metrics.max_drawdown_pct >= 0.0


class TestPersistTwoStage:
    def test_writes_aggressive_and_regularized_sidecars(self, tmp_path: Path) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        weights = SdcaCompositeWeights(power_law=0.63, weekly_rsi=0.37)
        extra_z = {"weekly_rsi": [0.0] * len(dates)}
        stage_b = run_stage_b_frozen(
            dates,
            prices,
            [{**SDCA_SHAPE_DEFAULTS, **freeze_weight_params(weights)}],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
            extra_z=extra_z,
        )
        windows = SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=date(2020, 1, 1),
                    end=date(2020, 1, 10),
                ),
            )
        )
        pair = persist_two_stage(
            stage_a_weights=weights,
            stage_b=stage_b,
            windows=windows,
            dest_dir=tmp_path,
            notes="unit-test two-stage persist",
        )
        aggressive = json.loads((tmp_path / "btc_composite_aggressive.json").read_text())
        regularized = json.loads((tmp_path / "btc_composite_regularized.json").read_text())
        assert pair.aggressive.variant == "aggressive"
        assert pair.regularized.variant == "regularized"
        assert aggressive["variant"] == "aggressive"
        assert regularized["variant"] == "regularized"
        assert aggressive["evaluator"] == "synthetic_fixture"
        assert aggressive["stage_a_weights"]["power_law"] == pytest.approx(0.63)
        assert aggressive["stage_a_weights"]["weekly_rsi"] == pytest.approx(0.37)
        assert regularized["stage_a_weights"]["power_law"] == pytest.approx(0.6)
        assert regularized["stage_a_weights"]["weekly_rsi"] == pytest.approx(0.4)
        assert regularized["stage_b_params"]["buy_max_rate"] < aggressive["stage_b_params"][
            "buy_max_rate"
        ] or regularized["stage_b_params"]["buy_max_rate"] == pytest.approx(
            aggressive["stage_b_params"]["buy_max_rate"] * 0.7
        )
        SdcaTwoStageProvenance.model_validate_json(
            (tmp_path / "btc_composite_aggressive.json").read_text()
        )
        SdcaTwoStageProvenance.model_validate_json(
            (tmp_path / "btc_composite_regularized.json").read_text()
        )
        assert (
            "overfit" in pair.aggressive.notes.lower()
            or "overfit" in pair.regularized.notes.lower()
        )


class TestCheckedInTwoStageProvenance:
    def test_sidecars_roundtrip_and_record_honest_oos(self) -> None:
        dest = Path(two_stage_mod.__file__).resolve().parent
        aggressive = SdcaTwoStageProvenance.model_validate_json(
            (dest / "btc_composite_aggressive.json").read_text()
        )
        regularized = SdcaTwoStageProvenance.model_validate_json(
            (dest / "btc_composite_regularized.json").read_text()
        )
        assert aggressive.variant == "aggressive"
        assert regularized.variant == "regularized"
        assert aggressive.evaluator == "curve_simulator"
        assert regularized.evaluator == "curve_simulator"
        assert aggressive.beats_flat_dca_oos is False
        assert regularized.oos_from_aggressive is True
        assert aggressive.oos_from_aggressive is False
        assert "overfit" in aggressive.notes.lower()
        names = {w.name for w in aggressive.windows}
        assert names == {
            "2017_peak",
            "2018_trough",
            "2021_peak",
            "2022_trough",
            "2025_peak",
        }
        assert regularized.stage_b_params["buy_max_rate"] == pytest.approx(
            round(float(aggressive.stage_b_params["buy_max_rate"]) * 0.7, 1)
        )
