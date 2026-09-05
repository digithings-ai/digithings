"""Stage A weight search scored by backtest, not cycle-window overlap."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
)
from digiquant.strategies.sdca.optimize import drop_extras_missing_sources
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.stage_a import CombinedCycleOverlapScore
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics
from digiquant.strategies.sdca.weight_search import (
    CycleOverlapPeriodSearchResult,
    optimize_stage_a_by_backtest,
    search_names_with_data,
    search_oscillator_periods_by_backtest,
    search_oscillator_periods_by_cycle_overlap,
)

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


def test_search_names_with_data_keeps_allowlist_that_has_z() -> None:
    extra_z = {"weekly_rsi": [0.0], "m2": [1.0], "sma_band": [0.0]}
    names = search_names_with_data(EXTRA_INDICATOR_NAMES, extra_z)
    assert names == ("m2", "weekly_rsi", "sma_band")
    assert "dxy" not in names
    assert "weekly_macd" not in names


def test_backtest_search_keeps_helpful_extra_and_drops_harmful() -> None:
    """Keep/drop is vs_flat_dca on in-sample folds, not cycle overlap."""
    dates = _dates()
    prices = [100.0 + 0.2 * i for i in range(len(dates))]
    zeros = [0.0] * len(dates)
    extra_z = {
        "weekly_rsi": zeros,
        "m2": zeros,
        "sma_band": zeros,
    }

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        assert isinstance(model, _ConstRails)
        rsi_w = m2_w = 0.0
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                rsi_w = float(ind.weight)
            elif getattr(ind, "name", "") == "m2":
                m2_w = float(ind.weight)
        vs_flat = 10.0 + 5.0 * rsi_w - 8.0 * m2_w + 0.1 * power_law_weight
        return SdcaTrialMetrics(
            vs_flat_dca_pct=vs_flat - 0.001 * len(window_dates),
            vs_lump_pct=-1.0,
            capital_deployed_pct=40.0,
            max_drawdown_pct=12.0,
        )

    result = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
        search_names=("weekly_rsi", "m2", "sma_band"),
        grid=(0.0, 1.0),
        power_law_grid=(1.0,),
    )
    assert result.weights.weekly_rsi == pytest.approx(1.0)
    assert result.weights.m2 == pytest.approx(0.0)
    assert result.weights.sma_band == pytest.approx(0.0)
    assert result.weights.power_law == pytest.approx(1.0)
    assert result.num_evaluations > 0
    assert result.mean_is_vs_flat_dca_pct > result.mean_oos_vs_flat_dca_pct - 50.0


def test_backtest_search_does_not_drop_all_on_high_drawdown() -> None:
    """IS drawdown above the Stage B 50% cap must not zero the extra grid."""
    dates = _dates()
    prices = [100.0 + 0.2 * i for i in range(len(dates))]
    zeros = [0.0] * len(dates)

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        rsi_w = 0.0
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                rsi_w = float(ind.weight)
        return SdcaTrialMetrics(
            vs_flat_dca_pct=4.0 + 3.0 * rsi_w,
            vs_lump_pct=-1.0,
            capital_deployed_pct=40.0,
            max_drawdown_pct=61.0,
        )

    result = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z={"weekly_rsi": zeros},
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
        search_names=("weekly_rsi",),
        grid=(0.0, 1.0),
        power_law_grid=(1.0,),
    )
    assert result.weights.weekly_rsi == pytest.approx(1.0)


def test_backtest_search_keeps_extra_when_early_fold_is_all_cash() -> None:
    """Early expanding IS windows can sit all-cash in the sell zone (#0d7a6f81).

    Stage A ranks by mean IS vs-flat-DCA across folds — not an all-folds
    capital-deployed floor. Requiring every fold to clear 10% deployed used
    to drop the whole extra grid when the first window never bought.
    """
    dates = _dates()
    prices = [100.0 + 0.2 * i for i in range(len(dates))]
    zeros = [0.0] * len(dates)

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        rsi_w = 0.0
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                rsi_w = float(ind.weight)
        # Short early windows: all-cash (0% deployed). Longer windows trade.
        deployed = 0.0 if len(window_dates) < 40 else 40.0
        return SdcaTrialMetrics(
            vs_flat_dca_pct=4.0 + 3.0 * rsi_w,
            vs_lump_pct=-1.0,
            capital_deployed_pct=deployed,
            max_drawdown_pct=12.0,
        )

    result = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z={"weekly_rsi": zeros},
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
        search_names=("weekly_rsi",),
        grid=(0.0, 1.0),
        power_law_grid=(1.0,),
    )
    assert result.weights.weekly_rsi == pytest.approx(1.0)
    assert any(not score.feasible for score in result.fold_scores)
    assert any(score.feasible for score in result.fold_scores)


def test_backtest_search_skips_enabled_extra_without_z() -> None:
    dates = _dates()
    prices = [100.0] * len(dates)

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        return SdcaTrialMetrics(
            vs_flat_dca_pct=float(power_law_weight),
            vs_lump_pct=0.0,
            capital_deployed_pct=40.0,
            max_drawdown_pct=10.0,
        )

    result = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z={"weekly_rsi": [0.0] * len(dates)},
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
        search_names=("weekly_rsi", "dxy"),
        grid=(0.0, 1.0),
        power_law_grid=(1.0,),
    )
    assert "dxy" not in result.weights.enabled_extras()
    assert result.weights.dxy == pytest.approx(0.0)


def test_period_search_picks_the_best_synthetic_period() -> None:
    """Same folds/evaluator/rank machinery as weight search, gridded over params."""
    dates = _dates()
    prices = [100.0 + 0.2 * i for i in range(len(dates))]
    n = len(dates)
    param_z = {5: 0.5, 14: 1.0, 30: 2.0}

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        rsi_z_mean = 0.0
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                vals = [v for v in ind.z.to_list() if v is not None]
                rsi_z_mean = sum(vals) / len(vals) if vals else 0.0
        return SdcaTrialMetrics(
            vs_flat_dca_pct=10.0 + 2.0 * rsi_z_mean - 0.001 * len(window_dates),
            vs_lump_pct=-1.0,
            capital_deployed_pct=40.0,
            max_drawdown_pct=12.0,
        )

    def compute_indicator_z(params: dict) -> list[float]:
        return [param_z[params["period"]]] * n

    result = search_oscillator_periods_by_backtest(
        dates,
        prices,
        indicator_name="weekly_rsi",
        param_candidates=[{"period": 5}, {"period": 14}, {"period": 30}],
        compute_indicator_z=compute_indicator_z,
        base_extra_z={},
        base_weights=SdcaCompositeWeights(power_law=1.0),
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
    )
    assert result.indicator_name == "weekly_rsi"
    assert result.best.params == {"period": 30}
    assert result.num_evaluations == 3
    assert len(result.all_scores) == 3
    assert isinstance(result.best.mean_oos_vs_flat_dca_pct, float)


def test_period_search_probes_indicator_weight_regardless_of_base() -> None:
    """indicator_name is forced to probe_weight even when base_weights has it at 0."""
    dates = _dates()
    prices = [100.0] * len(dates)
    seen_weights: list[float] = []

    def evaluator(
        window_dates: list[date],
        window_prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                seen_weights.append(float(ind.weight))
        return SdcaTrialMetrics(
            vs_flat_dca_pct=1.0, vs_lump_pct=0.0, capital_deployed_pct=40.0, max_drawdown_pct=10.0
        )

    search_oscillator_periods_by_backtest(
        dates,
        prices,
        indicator_name="weekly_rsi",
        param_candidates=[{"period": 5}],
        compute_indicator_z=lambda params: [0.0] * len(dates),
        base_extra_z={},
        base_weights=SdcaCompositeWeights(power_law=1.0),  # weekly_rsi defaults to 0.0
        rails_fitter=_fitter,
        evaluator=evaluator,
        shape=_SHAPE,
        probe_weight=1.0,
    )
    assert seen_weights, "evaluator never saw the probed indicator"
    assert all(w == pytest.approx(1.0) for w in seen_weights)


def test_period_search_rejects_empty_param_candidates() -> None:
    dates = _dates()
    prices = [100.0] * len(dates)
    with pytest.raises(ValueError, match="param_candidates"):
        search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name="weekly_rsi",
            param_candidates=[],
            compute_indicator_z=lambda params: [0.0] * len(dates),
            base_extra_z={},
            base_weights=SdcaCompositeWeights(power_law=1.0),
            rails_fitter=_fitter,
            evaluator=lambda *a, **k: SdcaTrialMetrics(
                vs_flat_dca_pct=0.0, vs_lump_pct=0.0, capital_deployed_pct=0.0, max_drawdown_pct=0.0
            ),
            shape=_SHAPE,
        )


def test_period_search_rejects_mismatched_z_length() -> None:
    dates = _dates()
    prices = [100.0] * len(dates)
    with pytest.raises(ValueError, match="expected"):
        search_oscillator_periods_by_backtest(
            dates,
            prices,
            indicator_name="weekly_rsi",
            param_candidates=[{"period": 5}],
            compute_indicator_z=lambda params: [0.0] * (len(dates) - 1),
            base_extra_z={},
            base_weights=SdcaCompositeWeights(power_law=1.0),
            rails_fitter=_fitter,
            evaluator=lambda *a, **k: SdcaTrialMetrics(
                vs_flat_dca_pct=0.0, vs_lump_pct=0.0, capital_deployed_pct=0.0, max_drawdown_pct=0.0
            ),
            shape=_SHAPE,
        )


def test_cycle_overlap_period_search_picks_the_best_synthetic_period() -> None:
    """Mirrors test_period_search_picks_the_best_synthetic_period, cycle-overlap objective."""
    dates = _dates(90)
    n = len(dates)
    trough_end = dates[19]
    peak_start = dates[70]
    windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=trough_end),
            CycleWindow(name="p", kind=CycleKind.PEAK, start=peak_start, end=dates[-1]),
        )
    )
    param_z = {5: 0.5, 14: 1.5, 30: 2.5}

    def compute_indicator_z(params: dict) -> list[float]:
        amp = param_z[params["period"]]
        out = []
        for d in dates:
            if d <= trough_end:
                out.append(amp)
            elif d >= peak_start:
                out.append(-amp)
            else:
                out.append(0.0)
        return out

    result = search_oscillator_periods_by_cycle_overlap(
        dates,
        indicator_name="weekly_rsi",
        param_candidates=[{"period": 5}, {"period": 14}, {"period": 30}],
        compute_indicator_z=compute_indicator_z,
        base_power_law_z=[0.0] * n,
        base_extra_z={},
        long_windows=windows,
        medium_windows=windows,
    )
    assert isinstance(result, CycleOverlapPeriodSearchResult)
    assert result.indicator_name == "weekly_rsi"
    assert result.best.params == {"period": 30}
    assert result.num_evaluations == 3
    assert len(result.all_scores) == 3
    assert isinstance(result.best.score, CombinedCycleOverlapScore)


def test_cycle_overlap_period_search_special_cases_power_law() -> None:
    """power_law's candidate z-series must replace base_power_law_z, extras zeroed."""
    dates = _dates(60)
    n = len(dates)
    trough_end = dates[14]
    peak_start = dates[45]
    windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=trough_end),
            CycleWindow(name="p", kind=CycleKind.PEAK, start=peak_start, end=dates[-1]),
        )
    )

    def compute_indicator_z(params: dict) -> list[float]:
        amp = float(params["trend_window"]) / 100.0
        out = []
        for d in dates:
            if d <= trough_end:
                out.append(amp)
            elif d >= peak_start:
                out.append(-amp)
            else:
                out.append(0.0)
        return out

    result = search_oscillator_periods_by_cycle_overlap(
        dates,
        indicator_name="power_law",
        param_candidates=[{"trend_window": 90}, {"trend_window": 250}],
        compute_indicator_z=compute_indicator_z,
        base_power_law_z=[0.0] * n,  # would score flat if wrongly used instead of z_series
        base_extra_z={"weekly_rsi": [5.0] * n},  # would dominate if not zeroed by weights
        long_windows=windows,
        medium_windows=windows,
    )
    assert result.indicator_name == "power_law"
    assert result.best.params == {"trend_window": 250}


def test_cycle_overlap_period_search_rejects_empty_param_candidates() -> None:
    dates = _dates()
    windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[9]),
            CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[20], end=dates[29]),
        )
    )
    with pytest.raises(ValueError, match="param_candidates"):
        search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name="weekly_rsi",
            param_candidates=[],
            compute_indicator_z=lambda params: [0.0] * len(dates),
            base_power_law_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=windows,
            medium_windows=windows,
        )


def test_cycle_overlap_period_search_rejects_mismatched_z_length() -> None:
    dates = _dates()
    windows = SdcaCycleWindows(
        windows=(
            CycleWindow(name="t", kind=CycleKind.TROUGH, start=dates[0], end=dates[9]),
            CycleWindow(name="p", kind=CycleKind.PEAK, start=dates[20], end=dates[29]),
        )
    )
    with pytest.raises(ValueError, match="expected"):
        search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name="weekly_rsi",
            param_candidates=[{"period": 5}],
            compute_indicator_z=lambda params: [0.0] * (len(dates) - 1),
            base_power_law_z=[0.0] * len(dates),
            base_extra_z={},
            long_windows=windows,
            medium_windows=windows,
        )


def test_drop_extras_missing_sources_zeros_plugins_only() -> None:
    raw = SdcaCompositeWeights(power_law=1.0, m2=1.0, weekly_rsi=0.5)
    dropped = drop_extras_missing_sources(raw, ExtraIndicatorSources())
    assert dropped.m2 == pytest.approx(0.0)
    assert dropped.weekly_rsi == pytest.approx(0.5)
    assert dropped.power_law == pytest.approx(1.0)


def test_checked_in_weights_sidecar_searched_full_catalog() -> None:
    """Guards that this frozen search run didn't silently skip a name from its
    own recorded catalog. Compares against the sidecar's own ``catalog`` field
    (the catalog as of that search), not the live EXTRA_INDICATOR_NAMES --
    the production sidecar is a point-in-time artifact and monthly_rsi/
    monthly_macd have been promoted into the research catalog but not yet
    re-searched into production (RESEARCH_STATE.md: needs Chris's accept).
    """
    payload = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "digiquant/src/digiquant/strategies/sdca/btc_composite_weights.json"
        ).read_text()
    )
    assert set(payload["search_names"]) == set(payload["catalog"])
    assert set(payload["catalog"]).issubset(set(EXTRA_INDICATOR_NAMES))
    assert payload["num_evaluations"] >= 128
    kept = {k: v for k, v in payload["weights"].items() if k != "power_law" and v > 0}
    assert kept == {}
