"""Stage A weight search scored by backtest, not cycle-window overlap."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
)
from digiquant.strategies.sdca.optimize import drop_extras_missing_sources
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics
from digiquant.strategies.sdca.weight_search import (
    optimize_stage_a_by_backtest,
    search_names_with_data,
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
        valuation_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        assert isinstance(model, _ConstRails)
        rsi_w = m2_w = 0.0
        for ind in extra_indicators or []:
            if getattr(ind, "name", "") == "weekly_rsi":
                rsi_w = float(ind.weight)
            elif getattr(ind, "name", "") == "m2":
                m2_w = float(ind.weight)
        vs_flat = 10.0 + 5.0 * rsi_w - 8.0 * m2_w + 0.1 * valuation_weight
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
        valuation_grid=(1.0,),
    )
    assert result.weights.weekly_rsi == pytest.approx(1.0)
    assert result.weights.m2 == pytest.approx(0.0)
    assert result.weights.sma_band == pytest.approx(0.0)
    assert result.weights.valuation == pytest.approx(1.0)
    assert result.num_evaluations > 0
    assert result.mean_is_vs_flat_dca_pct > result.mean_oos_vs_flat_dca_pct - 50.0


def test_backtest_search_skips_enabled_extra_without_z() -> None:
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
        return SdcaTrialMetrics(
            vs_flat_dca_pct=float(valuation_weight),
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
        valuation_grid=(1.0,),
    )
    assert "dxy" not in result.weights.enabled_extras()
    assert result.weights.dxy == pytest.approx(0.0)


def test_drop_extras_missing_sources_zeros_plugins_only() -> None:
    raw = SdcaCompositeWeights(valuation=1.0, m2=1.0, weekly_rsi=0.5)
    dropped = drop_extras_missing_sources(raw, ExtraIndicatorSources())
    assert dropped.m2 == pytest.approx(0.0)
    assert dropped.weekly_rsi == pytest.approx(0.5)
    assert dropped.valuation == pytest.approx(1.0)
