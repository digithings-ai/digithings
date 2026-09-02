"""Remaining-book curve search: frozen index, return objective, fill concentration."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from click.testing import CliRunner
from digiquant.cli import main as digiquant_main
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    CURVE_SEARCH_BOUNDS,
    DEEP_CHEAP_RISK,
    DEEP_RICH_RISK,
    PUBLISHED_BUY_KNEE,
    PUBLISHED_SELL_KNEE,
    CurveOptimizeGates,
    FillConcentration,
    beats_baseline_concentration,
    fill_concentration,
    persist_curve_winner,
    published_indicator_weights,
    round_shape_for_preset,
    sample_curve_trials,
    score_shape_on_index,
    search_curve,
    shape_from_bounds_ok,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategy_specs import get_param_specs

pytestmark = pytest.mark.unit


def _published_shape() -> SdcaCurveShape:
    preset = load_preset("btc_optimized")
    assert preset.shape is not None
    return preset.shape


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
    """Price dips then rips; risk is cheap at the trough and rich at the peak."""
    prices: list[float] = []
    risks: list[float] = []
    # Cheap window: price 50 → 40, risk 5 → 12 (bottom).
    for i in range(n_cheap):
        t = i / max(n_cheap - 1, 1)
        prices.append(50.0 - 10.0 * t)
        risks.append(5.0 + 7.0 * t)
    # Dead zone: price 40 → 80, risk 40 → 60.
    for i in range(n_mid):
        t = i / max(n_mid - 1, 1)
        prices.append(40.0 + 40.0 * t)
        risks.append(40.0 + 20.0 * t)
    # Rich window: price 80 → 120, risk 80 → 95 (top, includes 2025-like extension).
    for i in range(n_rich):
        t = i / max(n_rich - 1, 1)
        prices.append(80.0 + 40.0 * t)
        risks.append(80.0 + 15.0 * t)
    shifted = [date(2022, 1, 1) + timedelta(days=i) for i in range(n_cheap + n_mid)]
    shifted.extend(date(2025, 6, 1) + timedelta(days=i) for i in range(n_rich))
    return pl.Series("date", shifted, dtype=pl.Date), pl.Series(prices), pl.Series(risks)


class TestRemainingBookRateShape:
    def test_rate_rises_as_risk_goes_to_zero(self) -> None:
        shape = _shape(buy_max_rate=8.0, buy_knee_risk=25.0, buy_curvature=1.0)
        assert shape.rate_at(0.0) > shape.rate_at(10.0) > shape.rate_at(20.0) > 0.0
        assert shape.rate_at(25.0) == pytest.approx(0.0)

    def test_sell_rate_magnitude_rises_as_risk_goes_to_100(self) -> None:
        shape = _shape(sell_max_rate=8.0, sell_knee_risk=70.0, sell_curvature=2.0)
        assert shape.rate_at(100.0) < shape.rate_at(90.0) < shape.rate_at(80.0) < 0.0
        assert shape.rate_at(70.0) == pytest.approx(0.0)

    def test_higher_curvature_back_loads_toward_the_extreme(self) -> None:
        linear = _shape(buy_curvature=1.0).rate_at(12.0)
        curved = _shape(buy_curvature=3.0).rate_at(12.0)
        assert curved < linear
        assert _shape(buy_curvature=3.0).rate_at(0.0) == pytest.approx(
            _shape(buy_curvature=1.0).rate_at(0.0)
        )

    def test_five_percent_of_remaining_cash_compounds(self) -> None:
        dates = pl.date_range(date(2024, 1, 1), date(2024, 1, 3), eager=True)
        _, frame = run_backtest(
            dates,
            pl.Series([100.0, 100.0, 100.0]),
            pl.Series([0.0, 0.0, 0.0]),
            AccumDistCurve(_shape(buy_max_rate=5.0, buy_curvature=1.0).to_nodes()),
            1000.0,
        )
        cash = frame["cash"].to_list()
        assert cash[0] == pytest.approx(950.0)
        assert cash[1] == pytest.approx(902.5)
        assert cash[2] == pytest.approx(857.375)
        assert all(c > 0.0 for c in cash)


class TestFillConcentration:
    def test_all_buys_below_published_knee_when_knee_at_or_inside_25(self) -> None:
        dates, prices, risk = _v_cycle()
        score = score_shape_on_index(dates, prices, risk, _shape(buy_knee_risk=25.0), 1000.0)
        conc = score.concentration
        assert conc.buy_notional > 0.0
        assert conc.buy_frac_cheap == pytest.approx(1.0)
        assert conc.min_cash >= 0.0
        assert conc.min_units >= 0.0

    def test_curved_high_rate_clusters_buys_cheaper_than_linear_drip(self) -> None:
        dates, prices, risk = _v_cycle(n_cheap=60, n_mid=20, n_rich=40)
        drip = score_shape_on_index(dates, prices, risk, _shape(), 1000.0)
        clustered = score_shape_on_index(
            dates,
            prices,
            risk,
            _shape(
                buy_max_rate=20.0,
                buy_knee_risk=12.0,
                buy_curvature=3.0,
                sell_max_rate=20.0,
                sell_knee_risk=85.0,
                sell_curvature=3.0,
            ),
            1000.0,
        )
        assert drip.concentration.buy_mean_risk is not None
        assert clustered.concentration.buy_mean_risk is not None
        assert clustered.concentration.buy_mean_risk < drip.concentration.buy_mean_risk
        assert clustered.concentration.buy_frac_deep >= drip.concentration.buy_frac_deep
        assert clustered.concentration.sell_mean_risk is not None
        assert drip.concentration.sell_mean_risk is not None
        assert clustered.concentration.sell_mean_risk >= drip.concentration.sell_mean_risk

    def test_long_only_is_rejected(self) -> None:
        dates, prices, risk = _v_cycle()
        long_only = _shape(sell_max_rate=0.0, sell_knee_risk=100.0)
        score = score_shape_on_index(dates, prices, risk, long_only, 1000.0)
        assert score.feasible is False
        assert "long_only" in score.reject_reasons

    def test_2025_sell_gate(self) -> None:
        dates, prices, risk = _v_cycle()
        ok = score_shape_on_index(dates, prices, risk, _shape(sell_knee_risk=70.0), 1000.0)
        assert ok.concentration.sell_days_2025 >= 1
        assert ok.feasible is True
        assert "no_2025_sells" not in ok.reject_reasons


class TestSearchSpace:
    def test_bounds_are_wider_than_published_3_pct_25_70(self) -> None:
        assert CURVE_SEARCH_BOUNDS["buy_max_rate"][1] >= 30.0
        assert CURVE_SEARCH_BOUNDS["sell_max_rate"][1] >= 30.0
        assert CURVE_SEARCH_BOUNDS["buy_knee_risk"][0] <= 10.0
        assert CURVE_SEARCH_BOUNDS["buy_knee_risk"][1] <= PUBLISHED_BUY_KNEE
        assert CURVE_SEARCH_BOUNDS["sell_knee_risk"][0] >= PUBLISHED_SELL_KNEE
        assert CURVE_SEARCH_BOUNDS["buy_curvature"][1] >= 4.0
        assert CURVE_SEARCH_BOUNDS["sell_curvature"][1] >= 4.0

    def test_strategy_specs_match_widened_curve_bounds(self) -> None:
        specs = get_param_specs("sdca")
        lo_buy, hi_buy, _, _, _ = specs["buy_max_rate"]
        lo_sell, hi_sell, _, _, _ = specs["sell_max_rate"]
        assert hi_buy >= 30.0
        assert hi_sell >= 30.0
        lo_bk, hi_bk, _, _, _ = specs["buy_knee_risk"]
        lo_sk, hi_sk, _, _, _ = specs["sell_knee_risk"]
        assert hi_bk < lo_sk
        assert hi_bk <= PUBLISHED_BUY_KNEE
        assert lo_sk >= PUBLISHED_SELL_KNEE

    def test_sample_trials_stay_in_bounds_and_keep_dead_zone(self) -> None:
        trials = sample_curve_trials(
            n_random=40, seed=7, include_grid=False, include_published=False
        )
        assert len(trials) == 40
        for params in trials:
            assert shape_from_bounds_ok(params)
            shape = SdcaCurveShape(
                buy_max_rate=float(params["buy_max_rate"]),
                buy_knee_risk=float(params["buy_knee_risk"]),
                sell_knee_risk=float(params["sell_knee_risk"]),
                sell_max_rate=float(params["sell_max_rate"]),
                buy_curvature=float(params["buy_curvature"]),
                sell_curvature=float(params["sell_curvature"]),
            )
            assert shape.buy_knee_risk < shape.sell_knee_risk
            assert shape.sell_max_rate > 0.0


class TestSearchAndPersist:
    def test_search_picks_higher_return_among_concentrated(self) -> None:
        dates, prices, risk = _v_cycle()
        baseline = _published_shape()
        clustered = _shape(
            buy_max_rate=18.0,
            buy_knee_risk=12.0,
            buy_curvature=2.5,
            sell_max_rate=18.0,
            sell_knee_risk=82.0,
            sell_curvature=3.0,
        )
        result = search_curve(
            dates,
            prices,
            risk,
            trials=[
                {
                    "buy_max_rate": baseline.buy_max_rate,
                    "buy_knee_risk": baseline.buy_knee_risk,
                    "sell_knee_risk": baseline.sell_knee_risk,
                    "sell_max_rate": baseline.sell_max_rate,
                    "buy_curvature": baseline.buy_curvature,
                    "sell_curvature": baseline.sell_curvature,
                },
                {
                    "buy_max_rate": clustered.buy_max_rate,
                    "buy_knee_risk": clustered.buy_knee_risk,
                    "sell_knee_risk": clustered.sell_knee_risk,
                    "sell_max_rate": clustered.sell_max_rate,
                    "buy_curvature": clustered.buy_curvature,
                    "sell_curvature": clustered.sell_curvature,
                },
            ],
            initial_cash=1000.0,
            baseline=baseline,
            frozen_weights=published_indicator_weights(),
        )
        assert result.num_evaluations == 2
        assert result.beats_flat_dca_oos is False
        assert result.best.total_return_pct >= result.baseline.total_return_pct
        assert result.best.concentration.buy_mean_risk is not None
        assert result.baseline.concentration.buy_mean_risk is not None
        assert (
            result.best.concentration.buy_mean_risk <= result.baseline.concentration.buy_mean_risk
        )

    def test_higher_return_drip_does_not_win_over_concentrated(self) -> None:
        """A long risk≈20 plateau lets a 25-knee linear dump cash before the bottom."""
        n_plateau, n_bottom, n_mid, n_rich = 50, 20, 15, 30
        prices: list[float] = []
        risks: list[float] = []
        for i in range(n_plateau):
            prices.append(80.0 - 0.1 * i)
            risks.append(20.0)
        for i in range(n_bottom):
            t = i / max(n_bottom - 1, 1)
            prices.append(75.0 - 25.0 * t)
            risks.append(18.0 - 13.0 * t)
        for i in range(n_mid):
            t = i / max(n_mid - 1, 1)
            prices.append(50.0 + 30.0 * t)
            risks.append(40.0 + 20.0 * t)
        for i in range(n_rich):
            t = i / max(n_rich - 1, 1)
            prices.append(80.0 + 40.0 * t)
            risks.append(80.0 + 15.0 * t)
        dates_list = [
            date(2022, 1, 1) + timedelta(days=i) for i in range(n_plateau + n_bottom + n_mid)
        ]
        dates_list.extend(date(2025, 6, 1) + timedelta(days=i) for i in range(n_rich))
        dates = pl.Series("date", dates_list, dtype=pl.Date)
        prices_s = pl.Series(prices)
        risk_s = pl.Series(risks)
        baseline = _published_shape()
        drip = _shape(
            buy_max_rate=35.0,
            buy_knee_risk=25.0,
            buy_curvature=1.0,
            sell_max_rate=25.0,
            sell_knee_risk=70.0,
            sell_curvature=2.0,
        )
        clustered = _shape(
            buy_max_rate=20.0,
            buy_knee_risk=12.0,
            buy_curvature=3.0,
            sell_max_rate=20.0,
            sell_knee_risk=85.0,
            sell_curvature=3.0,
        )
        result = search_curve(
            dates,
            prices_s,
            risk_s,
            trials=[
                {
                    "buy_max_rate": drip.buy_max_rate,
                    "buy_knee_risk": drip.buy_knee_risk,
                    "sell_knee_risk": drip.sell_knee_risk,
                    "sell_max_rate": drip.sell_max_rate,
                    "buy_curvature": drip.buy_curvature,
                    "sell_curvature": drip.sell_curvature,
                },
                {
                    "buy_max_rate": clustered.buy_max_rate,
                    "buy_knee_risk": clustered.buy_knee_risk,
                    "sell_knee_risk": clustered.sell_knee_risk,
                    "sell_max_rate": clustered.sell_max_rate,
                    "buy_curvature": clustered.buy_curvature,
                    "sell_curvature": clustered.sell_curvature,
                },
            ],
            initial_cash=1000.0,
            baseline=baseline,
            frozen_weights=published_indicator_weights(),
        )
        drip_score = score_shape_on_index(dates, prices_s, risk_s, drip, 1000.0)
        clustered_score = score_shape_on_index(dates, prices_s, risk_s, clustered, 1000.0)
        assert clustered_score.concentration.buy_mean_risk is not None
        assert drip_score.concentration.buy_mean_risk is not None
        assert clustered_score.concentration.buy_mean_risk < drip_score.concentration.buy_mean_risk
        assert result.best.shape.buy_knee_risk == pytest.approx(12.0)
        assert result.unconstrained_return_pct >= result.best.total_return_pct - 1e-9

    def test_persist_requires_return_and_concentration(self, tmp_path: Path) -> None:
        dates, prices, risk = _v_cycle()
        baseline = _published_shape()
        result = search_curve(
            dates,
            prices,
            risk,
            trials=[
                {
                    "buy_max_rate": baseline.buy_max_rate,
                    "buy_knee_risk": baseline.buy_knee_risk,
                    "sell_knee_risk": baseline.sell_knee_risk,
                    "sell_max_rate": baseline.sell_max_rate,
                    "buy_curvature": baseline.buy_curvature,
                    "sell_curvature": baseline.sell_curvature,
                }
            ],
            initial_cash=1000.0,
            baseline=baseline,
            frozen_weights=published_indicator_weights(),
        )
        # Same as baseline → not a persist (needs a strict beat on return).
        presets = tmp_path / "presets.json"
        presets.write_text(json.dumps({"btc_optimized": {"shape": {}, "long_only": False}}))
        sidecar = tmp_path / "curve.json"
        wrote = persist_curve_winner(
            result,
            presets_path=presets,
            sidecar_path=sidecar,
            persist=True,
        )
        assert wrote is False
        assert sidecar.exists()

    def test_published_weights_are_frozen_from_settings(self) -> None:
        weights = published_indicator_weights()
        assert weights.valuation == pytest.approx(1.0)
        assert weights.m2 == pytest.approx(0.5)
        assert weights.dxy == pytest.approx(0.5)
        assert weights.rs_eth == pytest.approx(0.0)
        assert weights.sma_band == pytest.approx(0.0)
        # Richer published composite (#3304): cycle-scaled oscillators, not 90-day z.
        assert weights.weekly_rsi == pytest.approx(0.25)
        assert weights.weekly_macd == pytest.approx(0.5)

    def test_cli_help_lists_command(self) -> None:
        result = CliRunner().invoke(digiquant_main, ["sdca-optimize-curve", "--help"])
        assert result.exit_code == 0
        assert "--persist-preset" in result.output
        assert "--sidecar" in result.output
        assert "frozen" in result.output.lower() or "curve" in result.output.lower()


class TestConcentrationHelper:
    def test_empty_trades_are_zero(self) -> None:
        frame = pl.DataFrame(
            {
                "date": [date(2024, 1, 1)],
                "risk": [50.0],
                "daily_trade_usd": [0.0],
                "cash": [1000.0],
                "asset_units": [0.0],
            }
        )
        conc = fill_concentration(frame)
        assert conc.buy_notional == pytest.approx(0.0)
        assert conc.sell_notional == pytest.approx(0.0)
        assert conc.buy_frac_cheap == pytest.approx(0.0)
        assert conc.sell_frac_rich == pytest.approx(0.0)

    def test_beats_baseline_concentration_uses_mean_risk(self) -> None:
        worse = FillConcentration(
            buy_notional=100.0,
            sell_notional=100.0,
            buy_frac_cheap=1.0,
            sell_frac_rich=1.0,
            buy_frac_deep=0.2,
            sell_frac_deep=0.2,
            buy_mean_risk=18.0,
            sell_mean_risk=75.0,
            sell_notional_2025=10.0,
            sell_days_2025=2,
            min_cash=1.0,
            min_units=0.0,
        )
        better = worse.model_copy(
            update={
                "buy_mean_risk": 9.0,
                "sell_mean_risk": 90.0,
                "buy_frac_deep": 0.8,
                "sell_frac_deep": 0.7,
            }
        )
        assert beats_baseline_concentration(better, worse) is True
        assert beats_baseline_concentration(worse, better) is False
        assert DEEP_CHEAP_RISK < PUBLISHED_BUY_KNEE
        assert DEEP_RICH_RISK > PUBLISHED_SELL_KNEE

    def test_gates_type_defaults(self) -> None:
        gates = CurveOptimizeGates()
        assert gates.require_2025_sells is True
        assert gates.require_sells is True
        assert gates.min_sell_max_rate > 0.0

    def test_round_shape_for_preset_is_one_decimal(self) -> None:
        rounded = round_shape_for_preset(
            _shape(
                buy_max_rate=35.4864,
                buy_knee_risk=24.0981,
                sell_knee_risk=71.8844,
                sell_max_rate=20.9816,
                buy_curvature=1.2769,
                sell_curvature=4.0424,
            )
        )
        assert rounded.buy_max_rate == pytest.approx(35.5)
        assert rounded.buy_knee_risk == pytest.approx(24.1)
        assert rounded.sell_knee_risk == pytest.approx(71.9)
        assert rounded.sell_max_rate == pytest.approx(21.0)
        assert rounded.buy_curvature == pytest.approx(1.3)
        assert rounded.sell_curvature == pytest.approx(4.0)
