"""Stage 0 solo-indicator books: per-series curve search gated on OOS vs-flat."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    indicator_display_name,
)
from digiquant.strategies.sdca.optimize import SDCA_SHAPE_DEFAULTS
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.stage_0 import (
    NAMED_BASELINE,
    POWER_LAW_CODE_ID,
    Stage0Cadence,
    persist_stage_0,
    run_stage_0,
    solo_weights,
)
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics
from digiquant.strategies.sdca.weight_search import optimize_stage_1_survivor_weights

pytestmark = pytest.mark.unit


def _dates(n: int = 80) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
    assert dates and prices
    return _ConstRails()


_SHAPE = SdcaCurveShape(
    buy_max_rate=4.0,
    buy_knee_risk=30.0,
    sell_knee_risk=70.0,
    sell_max_rate=5.0,
    buy_curvature=1.0,
    sell_curvature=2.0,
)

_TRIALS = [{**SDCA_SHAPE_DEFAULTS, "buy_max_rate": 4.0, "sell_max_rate": 5.0}]


def _weight_of(extra_indicators: object, name: str) -> float:
    for ind in extra_indicators or []:
        if getattr(ind, "name", "") == name:
            return float(ind.weight)
    return 0.0


def _evaluator(
    window_dates: list[date],
    window_prices: list[float],
    model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    extra_indicators: object = None,
) -> SdcaTrialMetrics:
    """IS vs OOS split: expanding IS windows start on the first calendar day."""
    assert isinstance(model, _ConstRails)
    is_window = window_dates[0] == date(2020, 1, 1)
    rsi_w = _weight_of(extra_indicators, "weekly_rsi")
    m2_w = _weight_of(extra_indicators, "m2")
    sma_w = _weight_of(extra_indicators, "sma_band")
    if is_window:
        vs_flat = 10.0 + 50.0 * rsi_w + 2.0 * m2_w + 80.0 * sma_w + 0.1 * valuation_weight
    else:
        vs_flat = 1.0 - 20.0 * rsi_w + 5.0 * m2_w + 40.0 * sma_w + 0.1 * valuation_weight
    vs_flat -= 0.01 * abs(shape.buy_max_rate - 4.0)
    return SdcaTrialMetrics(
        vs_flat_dca_pct=vs_flat,
        vs_lump_pct=-1.0,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


def _cadence(sell_days: int) -> Stage0Cadence:
    return Stage0Cadence(
        buy_days=20,
        sell_days=sell_days,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


class TestSoloWeights:
    def test_power_law_omits_extras(self) -> None:
        w = solo_weights(POWER_LAW_CODE_ID)
        assert w.valuation == pytest.approx(1.0)
        assert w.enabled_extras() == {}
        assert indicator_display_name(POWER_LAW_CODE_ID) == "power law"

    def test_extra_omits_unused_valuation(self) -> None:
        w = solo_weights("m2")
        assert w.valuation == pytest.approx(0.0)
        assert w.m2 == pytest.approx(1.0)
        assert w.enabled_extras() == {"m2": 1.0}


class TestStage0OosGate:
    def test_keeps_extra_that_beats_power_law_oos_not_is(self) -> None:
        dates = _dates()
        prices = [100.0 + 0.2 * i for i in range(len(dates))]
        zeros = [0.0] * len(dates)
        extra_z = {"weekly_rsi": zeros, "m2": zeros, "sma_band": zeros}

        def cadence_fn(
            code_id: str,
            *_args: object,
            **_kwargs: object,
        ) -> Stage0Cadence:
            return _cadence(sell_days=0 if code_id == "sma_band" else 8)

        report = run_stage_0(
            dates,
            prices,
            extra_z=extra_z,
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="curve_simulator",
            search_names=("weekly_rsi", "m2", "sma_band"),
            shape_trials=_TRIALS,
            cadence_fn=cadence_fn,
        )
        assert report.evaluator == "curve_simulator"
        assert report.baseline_name == NAMED_BASELINE
        by_id = {row.code_id: row for row in report.solos}
        assert by_id[POWER_LAW_CODE_ID].display_name == "power law"
        assert by_id["weekly_rsi"].keep is False
        assert (
            by_id["weekly_rsi"].mean_is_vs_flat_dca_pct
            > by_id[POWER_LAW_CODE_ID].mean_is_vs_flat_dca_pct
        )
        assert "oos" in (by_id["weekly_rsi"].drop_reason or "").lower()
        assert by_id["m2"].keep is True
        assert by_id["sma_band"].keep is False
        assert "sell" in (by_id["sma_band"].drop_reason or "").lower()
        assert report.survivors == (POWER_LAW_CODE_ID, "m2")
        assert report.beats_flat_dca_oos is False

    def test_no_extra_surviving_is_an_honest_empty_keep(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)

        def evaluator(
            window_dates: list[date],
            window_prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            is_window = window_dates[0] == date(2020, 1, 1)
            extra_w = sum(_weight_of(extra_indicators, n) for n in EXTRA_INDICATOR_NAMES)
            vs = (5.0 if is_window else 2.0) + 0.2 * valuation_weight - 10.0 * extra_w
            return SdcaTrialMetrics(
                vs_flat_dca_pct=vs,
                vs_lump_pct=0.0,
                capital_deployed_pct=40.0,
                max_drawdown_pct=12.0,
            )

        report = run_stage_0(
            dates,
            prices,
            extra_z={"m2": [0.0] * len(dates)},
            rails_fitter=_fitter,
            evaluator=evaluator,
            evaluator_label="curve_simulator",
            search_names=("m2",),
            shape_trials=_TRIALS,
            cadence_fn=lambda *_a, **_k: _cadence(sell_days=4),
        )
        assert report.survivors == (POWER_LAW_CODE_ID,)
        assert report.solos[0].code_id == POWER_LAW_CODE_ID
        m2 = next(row for row in report.solos if row.code_id == "m2")
        assert m2.keep is False


class TestStage1SurvivorWeights:
    def test_grid_excludes_zero_so_drop_cannot_cheaply_win(self) -> None:
        dates = _dates()
        prices = [100.0 + 0.1 * i for i in range(len(dates))]
        zeros = [0.0] * len(dates)

        def evaluator(
            window_dates: list[date],
            window_prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            m2_w = _weight_of(extra_indicators, "m2")
            # Turning m2 off (weight 0) would be the cheap IS winner.
            vs = 10.0 - 4.0 * m2_w + 0.1 * valuation_weight
            return SdcaTrialMetrics(
                vs_flat_dca_pct=vs,
                vs_lump_pct=0.0,
                capital_deployed_pct=40.0,
                max_drawdown_pct=12.0,
            )

        result = optimize_stage_1_survivor_weights(
            dates,
            prices,
            extra_z={"m2": zeros},
            rails_fitter=_fitter,
            evaluator=evaluator,
            shape=_SHAPE,
            survivor_names=(POWER_LAW_CODE_ID, "m2"),
            grid=(0.5, 1.0),
        )
        assert 0.0 not in (0.5, 1.0)
        assert result.weights.m2 > 0.0
        assert result.weights.valuation > 0.0
        assert result.search_names == ("m2",)

    def test_grid_with_zero_is_rejected(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            optimize_stage_1_survivor_weights(
                dates,
                prices,
                extra_z={"m2": [0.0] * len(dates)},
                rails_fitter=_fitter,
                evaluator=_evaluator,
                shape=_SHAPE,
                survivor_names=(POWER_LAW_CODE_ID, "m2"),
                grid=(0.0, 1.0),
            )

    def test_power_law_only_skips_weight_grid(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        result = optimize_stage_1_survivor_weights(
            dates,
            prices,
            extra_z={},
            rails_fitter=_fitter,
            evaluator=_evaluator,
            shape=_SHAPE,
            survivor_names=(POWER_LAW_CODE_ID,),
            grid=(0.5, 1.0),
        )
        assert result.weights == SdcaCompositeWeights()
        assert result.num_evaluations == 0


class TestPersistStage0:
    def test_sidecar_records_evaluator_and_keep_reasons(self, tmp_path: Path) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        report = run_stage_0(
            dates,
            prices,
            extra_z={"m2": [0.0] * len(dates)},
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="curve_simulator",
            search_names=("m2",),
            shape_trials=_TRIALS,
            cadence_fn=lambda *_a, **_k: _cadence(sell_days=3),
        )
        path = persist_stage_0(report, tmp_path / "btc_stage0.json")
        payload = path.read_text()
        assert "curve_simulator" in payload
        assert "power law" in payload
        assert NAMED_BASELINE in payload
        assert report.beats_flat_dca_oos is False
        assert '"beats_flat_dca_oos": true' not in payload


def test_settings_persist_only_when_combined_oos_is_not_worse() -> None:
    from digiquant.strategies.sdca.stage_0 import should_persist_settings

    assert should_persist_settings(-10.0, -7.8) is False
    assert should_persist_settings(-7.8, -7.8) is True
    assert should_persist_settings(-5.0, -7.8) is True
