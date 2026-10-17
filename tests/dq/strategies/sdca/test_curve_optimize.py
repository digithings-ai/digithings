"""Remaining-book curve search: frozen index, return objective, fill concentration."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from click.testing import CliRunner
from digiquant.cli import main as digiquant_main
from digiquant.strategies.sdca import curve_optimize as curve_optimize_module
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import RISK_NODES, AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    CONTINUOUS_CROSSING_EPS,
    CURVE_SEARCH_BOUNDS,
    DEAD_ZONE_WIDTH_GRID,
    DEEP_CHEAP_RISK,
    DEEP_RICH_RISK,
    PUBLISHED_BUY_KNEE,
    PUBLISHED_SELL_KNEE,
    WIDE_KNEE_SEARCH_BOUNDS,
    CurveOptimizeGates,
    FillConcentration,
    beats_baseline_concentration,
    continuous_shape_ok,
    continuous_shape_params,
    dead_zone_shape_params,
    fill_concentration,
    load_frozen_index,
    persist_curve_winner,
    published_curve_shape,
    published_indicator_weights,
    round_shape_for_preset,
    run_published_curve_search,
    sample_continuous_curve_trials,
    sample_curve_trials,
    sample_wide_knee_curve_trials,
    score_dead_zone_width,
    score_shape_on_index,
    search_continuous_curve,
    search_curve,
    search_wide_knee_curve,
    shape_from_bounds_ok,
    sweep_dead_zone_width,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategy_specs import get_param_specs

pytestmark = pytest.mark.unit


def _published_shape() -> SdcaCurveShape:
    """Today's live ``btc_optimized`` shape, for baseline-identity checks."""
    preset = load_preset("btc_optimized")
    assert preset.shape is not None
    return preset.shape


def _weak_baseline() -> SdcaCurveShape:
    """Fixed weak single-knee baseline for search-mechanics tests.

    These tests verify search selection on synthetic data, not the published
    preset's value (pinned by TestBtcOptimizedPromotion + the dead-zone
    test). They previously read the live preset via load_preset, which broke
    when the preset was promoted to the cycle-4 mid-tier candidate: fixed
    6-key trials can no longer beat it on raw return. The pre-promotion
    knees (35.5/24.1/71.9/21.0/1.3/4.0) preserve the original test premise.
    """
    return _shape(
        buy_max_rate=35.5,
        buy_knee_risk=24.1,
        sell_knee_risk=71.9,
        sell_max_rate=21.0,
        buy_curvature=1.3,
        sell_curvature=4.0,
    )


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


def _mean_risk_concentration(
    *, buy_mean_risk: float | None, sell_mean_risk: float | None
) -> FillConcentration:
    """A concentration whose only free variables are the two mean-risk figures.

    Every other field is held fixed so that a comparison against another
    ``_mean_risk_concentration`` differs *only* on the mean-risk guards, which
    is what lets the 1e-9 tie band be probed on its own.
    """
    return FillConcentration(
        buy_notional=100.0,
        sell_notional=100.0,
        buy_frac_cheap=1.0,
        sell_frac_rich=1.0,
        buy_frac_deep=0.5,
        sell_frac_deep=0.5,
        buy_mean_risk=buy_mean_risk,
        sell_mean_risk=sell_mean_risk,
        sell_notional_2025=10.0,
        sell_days_2025=2,
        min_cash=1.0,
        min_units=0.0,
    )


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
        baseline = _weak_baseline()
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
        baseline = _weak_baseline()
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
        baseline = _weak_baseline()
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

    def test_beats_baseline_tolerance_is_a_tie_band_not_a_licence(self) -> None:
        """Pin the *direction* of the 1e-9 tie band on both mean-risk guards.

        ``beats_baseline_concentration`` treats a candidate as worse only when
        it is worse by more than 1e-9. The pre-existing test above uses 18.0
        versus 9.0, which is nowhere near the epsilon, so it pins monotone
        ordering only -- the correct guard and an inverted ``- 1e-9`` give it
        the same answer. These cases straddle the boundary, which is the only
        thing that distinguishes ``+ 1e-9`` from ``- 1e-9``.
        """
        baseline = _mean_risk_concentration(buy_mean_risk=50.0, sell_mean_risk=50.0)

        # Bought at a *higher* mean risk is worse; inside the tie band it passes.
        marginally_worse_buys = _mean_risk_concentration(
            buy_mean_risk=50.0 + 5e-10, sell_mean_risk=50.0
        )
        assert beats_baseline_concentration(marginally_worse_buys, baseline) is True

        # Same defect, past the epsilon: now it loses.
        worse_buys = _mean_risk_concentration(buy_mean_risk=50.0 + 5e-9, sell_mean_risk=50.0)
        assert beats_baseline_concentration(worse_buys, baseline) is False

        # Sold at a *lower* mean risk is worse; mirror image on the sell side.
        marginally_worse_sells = _mean_risk_concentration(
            buy_mean_risk=50.0, sell_mean_risk=50.0 - 5e-10
        )
        assert beats_baseline_concentration(marginally_worse_sells, baseline) is True

        worse_sells = _mean_risk_concentration(buy_mean_risk=50.0, sell_mean_risk=50.0 - 5e-9)
        assert beats_baseline_concentration(worse_sells, baseline) is False

    def test_beats_baseline_rejects_a_candidate_missing_a_mean(self) -> None:
        baseline = _mean_risk_concentration(buy_mean_risk=50.0, sell_mean_risk=50.0)
        assert (
            beats_baseline_concentration(
                _mean_risk_concentration(buy_mean_risk=None, sell_mean_risk=50.0), baseline
            )
            is False
        )
        assert (
            beats_baseline_concentration(
                _mean_risk_concentration(buy_mean_risk=50.0, sell_mean_risk=None), baseline
            )
            is False
        )

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


class TestContinuousCurveParams:
    def test_crossing_risk_splits_into_a_tiny_symmetric_knee_gap(self) -> None:
        params = continuous_shape_params(50.0, 20.0, 20.0, 2.0, 2.0)
        assert params["buy_knee_risk"] == pytest.approx(50.0 - CONTINUOUS_CROSSING_EPS / 2)
        assert params["sell_knee_risk"] == pytest.approx(50.0 + CONTINUOUS_CROSSING_EPS / 2)
        gap = params["sell_knee_risk"] - params["buy_knee_risk"]
        assert gap == pytest.approx(CONTINUOUS_CROSSING_EPS)
        assert gap < 5.0  # far below the RISK_NODES spacing

    def test_rates_are_near_zero_but_nonzero_on_either_side_of_the_crossing(self) -> None:
        params = continuous_shape_params(50.0, 20.0, 20.0, 2.0, 2.0)
        shape = SdcaCurveShape(**params)
        just_below = shape.rate_at(50.0 - CONTINUOUS_CROSSING_EPS)
        just_above = shape.rate_at(50.0 + CONTINUOUS_CROSSING_EPS)
        assert 0.0 < just_below < 0.01
        assert -0.01 < just_above < 0.0

    def test_continuous_shape_ok_ignores_old_disjoint_knee_bounds(self) -> None:
        """A crossing near 15 puts sell_knee_risk far outside the old
        CURVE_SEARCH_BOUNDS sell range [50, 92] -- that's fine here, since a
        continuous fit's crossing point legitimately covers that whole middle
        territory (there's no artificial dead zone constraining it)."""
        params = continuous_shape_params(15.0, 20.0, 20.0, 2.0, 2.0)
        assert not shape_from_bounds_ok(params)
        assert continuous_shape_ok(params)

    def test_continuous_shape_ok_still_rejects_out_of_bounds_rate(self) -> None:
        params = continuous_shape_params(50.0, 999.0, 20.0, 2.0, 2.0)
        assert not continuous_shape_ok(params)

    def test_continuous_shape_ok_rejects_zero_sell_max_rate_via_the_rate_bounds(self) -> None:
        """Named for what it pins, not for the guard that looks like it pins.

        ``continuous_shape_ok`` ends with ``return shape.sell_max_rate > 0.0``,
        but that line is unreachable through this entry point: the bounds loop
        rejects 0.0 first, because ``CURVE_SEARCH_BOUNDS["sell_max_rate"]`` is
        ``(3.0, 40.0)``. The rejection asserted here is the rate-bounds loop.
        The trailing check stays as defence in depth for any future bounds that
        admit 0.0.
        """
        params = continuous_shape_params(50.0, 20.0, 0.0, 2.0, 2.0)
        assert not continuous_shape_ok(params)
        assert CURVE_SEARCH_BOUNDS["sell_max_rate"][0] > 0.0


class TestSampleContinuousCurveTrials:
    def test_random_only_trials_deduped_and_within_bounds(self) -> None:
        """Occasionally a high-curvature crossing lands so close to a RISK_NODES
        point that the adjacent node's interpolated rate underflows below
        SdcaCurveShape's own epsilon and gets rejected -- inherent to the
        unchanged shape validator, not a defect in the generator, so a small
        undercount vs n_random is expected rather than an exact match."""
        trials = sample_continuous_curve_trials(n_random=40, seed=7, include_grid=False)
        assert 35 <= len(trials) <= 40
        for params in trials:
            assert continuous_shape_ok(params)

    def test_at_most_one_risk_node_ever_falls_in_the_dead_zone(self) -> None:
        trials = sample_continuous_curve_trials(n_random=200, seed=3, include_grid=True)
        assert len(trials) > 0
        for params in trials:
            shape = SdcaCurveShape(**params)
            dead_nodes = [r for r in RISK_NODES if shape.buy_knee_risk <= r <= shape.sell_knee_risk]
            assert len(dead_nodes) <= 1

    def test_grid_and_random_are_independent_knobs(self) -> None:
        grid_only = sample_continuous_curve_trials(n_random=0, include_grid=True)
        random_only = sample_continuous_curve_trials(n_random=10, seed=1, include_grid=False)
        assert len(grid_only) > 0
        assert 8 <= len(random_only) <= 10

    def test_same_seed_is_deterministic(self) -> None:
        a = sample_continuous_curve_trials(n_random=25, seed=11, include_grid=False)
        b = sample_continuous_curve_trials(n_random=25, seed=11, include_grid=False)
        assert a == b


class TestSearchContinuousCurve:
    def test_search_continuous_curve_picks_a_feasible_continuous_shape(self) -> None:
        dates, prices, risk = _v_cycle()
        result = search_continuous_curve(
            dates,
            prices,
            risk,
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            n_random=60,
            seed=5,
            include_grid=False,
        )
        assert 50 <= result.num_evaluations <= 60
        gap = result.best.shape.sell_knee_risk - result.best.shape.buy_knee_risk
        assert gap == pytest.approx(CONTINUOUS_CROSSING_EPS)
        assert result.beats_flat_dca_oos is False

    def test_baseline_is_todays_published_curve(self) -> None:
        dates, prices, risk = _v_cycle()
        result = search_continuous_curve(
            dates,
            prices,
            risk,
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            n_random=20,
            seed=9,
            include_grid=False,
        )
        assert result.baseline.shape == _published_shape()


class TestSampleWideKneeCurveTrials:
    def test_random_only_trials_deduped_and_within_bounds(self) -> None:
        trials = sample_wide_knee_curve_trials(n_random=200, seed=7, include_grid=False)
        assert 150 <= len(trials) <= 200
        for params in trials:
            assert shape_from_bounds_ok(params, bounds=WIDE_KNEE_SEARCH_BOUNDS)

    def test_knees_are_independent_not_a_single_crossing(self) -> None:
        """Unlike the continuous-curve sampler, gaps here should vary widely --
        this search must be able to explore genuinely separated buy/sell
        knees, not just a near-zero crossing epsilon."""
        trials = sample_wide_knee_curve_trials(n_random=300, seed=3, include_grid=False)
        gaps = [t["sell_knee_risk"] - t["buy_knee_risk"] for t in trials]
        assert max(gaps) > 20.0
        assert min(gaps) < 20.0

    def test_grid_and_random_are_independent_knobs(self) -> None:
        grid_only = sample_wide_knee_curve_trials(n_random=0, include_grid=True)
        random_only = sample_wide_knee_curve_trials(n_random=10, seed=1, include_grid=False)
        assert len(grid_only) > 0
        assert 8 <= len(random_only) <= 10

    def test_same_seed_is_deterministic(self) -> None:
        a = sample_wide_knee_curve_trials(n_random=25, seed=11, include_grid=False)
        b = sample_wide_knee_curve_trials(n_random=25, seed=11, include_grid=False)
        assert a == b


class TestSearchWideKneeCurve:
    def test_search_wide_knee_curve_picks_a_feasible_shape(self) -> None:
        dates, prices, risk = _v_cycle()
        result = search_wide_knee_curve(
            dates,
            prices,
            risk,
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            n_random=60,
            seed=5,
            include_grid=False,
        )
        assert 50 <= result.num_evaluations <= 60
        assert result.best.shape.buy_knee_risk < result.best.shape.sell_knee_risk
        assert result.beats_flat_dca_oos is False

    def test_baseline_is_todays_published_curve(self) -> None:
        dates, prices, risk = _v_cycle()
        result = search_wide_knee_curve(
            dates,
            prices,
            risk,
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            n_random=20,
            seed=9,
            include_grid=False,
        )
        assert result.baseline.shape == _published_shape()


class TestDeadZoneShapeParams:
    def test_zero_width_collapses_to_a_tiny_symmetric_gap(self) -> None:
        params = dead_zone_shape_params(50.0, 0.0, 15.0, 15.0, 1.5, 1.5)
        assert params["sell_knee_risk"] - params["buy_knee_risk"] == pytest.approx(2e-6)
        assert params["buy_knee_risk"] == pytest.approx(50.0, abs=1e-5)

    def test_width_widens_a_symmetric_gap_around_crossing(self) -> None:
        params = dead_zone_shape_params(50.0, 20.0, 15.0, 15.0, 1.5, 1.5)
        assert params["buy_knee_risk"] == pytest.approx(40.0)
        assert params["sell_knee_risk"] == pytest.approx(60.0)

    def test_large_width_near_an_edge_clips_to_valid_knee_bounds(self) -> None:
        params = dead_zone_shape_params(
            5.0, 50.0, 15.0, 15.0, 1.5, 1.5, knee_floor=0.5, knee_ceiling=99.5
        )
        assert params["buy_knee_risk"] == pytest.approx(0.5)
        assert params["buy_knee_risk"] < params["sell_knee_risk"]
        # every width, including this clipped edge case, must yield a valid shape
        SdcaCurveShape(**params)

    def test_every_grid_width_yields_a_valid_shape_from_a_mid_crossing(self) -> None:
        for width in DEAD_ZONE_WIDTH_GRID:
            params = dead_zone_shape_params(50.0, width, 15.0, 15.0, 1.5, 1.5)
            SdcaCurveShape(**params)


class TestScoreDeadZoneWidth:
    def test_trade_days_match_the_raw_backtest_report(self) -> None:
        dates, prices, risk = _v_cycle()
        shape = _shape(buy_knee_risk=45.0, sell_knee_risk=55.0)
        report, _ = run_backtest(dates, prices, risk, AccumDistCurve(shape.to_nodes()), 1000.0)
        scored = score_dead_zone_width(dates, prices, risk, shape, 10.0, 1000.0)
        assert scored.trade_days == report.buy_days + report.sell_days
        assert scored.buy_days == report.buy_days
        assert scored.sell_days == report.sell_days
        assert scored.width == 10.0

    def test_long_only_shape_is_flagged_infeasible(self) -> None:
        dates, prices, risk = _v_cycle()
        shape = _shape(sell_max_rate=0.0)
        scored = score_dead_zone_width(dates, prices, risk, shape, 45.0, 1000.0)
        assert not scored.feasible
        assert "long_only" in scored.reject_reasons


class TestSweepDeadZoneWidth:
    def _winner(self) -> SdcaCurveShape:
        return SdcaCurveShape(
            buy_max_rate=15.0,
            buy_knee_risk=49.75,
            sell_knee_risk=50.25,
            sell_max_rate=15.0,
            buy_curvature=1.5,
            sell_curvature=1.5,
        )

    def test_recovers_the_winners_crossing_as_the_midpoint(self) -> None:
        dates, prices, risk = _v_cycle()
        result = sweep_dead_zone_width(
            dates,
            prices,
            risk,
            self._winner(),
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            widths=(0.5, 10.0, 50.0),
        )
        assert result.crossing_risk == pytest.approx(50.0)
        assert [t.width for t in result.trials] == [0.5, 10.0, 50.0]

    def test_continuous_baseline_is_the_winner_shape_unmodified(self) -> None:
        dates, prices, risk = _v_cycle()
        winner = self._winner()
        result = sweep_dead_zone_width(
            dates,
            prices,
            risk,
            winner,
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            widths=(5.0,),
        )
        assert result.continuous_baseline.shape == winner
        assert result.continuous_baseline.width == 0.0

    def test_wider_dead_zone_trades_less_on_this_v_cycle(self) -> None:
        dates, prices, risk = _v_cycle()
        result = sweep_dead_zone_width(
            dates,
            prices,
            risk,
            self._winner(),
            initial_cash=1000.0,
            frozen_weights=published_indicator_weights(),
            widths=(0.5, 50.0),
        )
        narrow, wide = result.trials
        assert wide.trade_days <= narrow.trade_days

    def test_frozen_weights_round_trip_into_the_result(self) -> None:
        dates, prices, risk = _v_cycle()
        weights = published_indicator_weights()
        result = sweep_dead_zone_width(
            dates,
            prices,
            risk,
            self._winner(),
            initial_cash=1000.0,
            frozen_weights=weights,
            widths=(1.0,),
        )
        assert result.frozen_weights == weights.model_dump()


def _write_btc_cache(cache_dir: Path, *, n_days: int = 800, start: date = date(2016, 1, 4)) -> date:
    """Write a deterministic ``BTC-USD.csv`` into ``cache_dir``; return its last date.

    The sawtooth gives the power-law fit real variation, so the frozen risk
    index is not a constant and the date arithmetic below is not degenerate.
    800 days from 2016-01-04 leaves a 2018-01-01 trade-start window that is
    comfortably longer than any signal delay used below.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = ["timestamp,open,high,low,close,volume,symbol"]
    for i in range(n_days):
        d = start + timedelta(days=i)
        price = 400.0 + 120.0 * ((i % 90) / 90.0) + 0.05 * i
        rows.append(f"{d},{price},{price * 1.01},{price * 0.99},{price},1,BTC-USD")
    (cache_dir / "BTC-USD.csv").write_text("\n".join(rows) + "\n")
    return start + timedelta(days=n_days - 1)


class TestLoadFrozenIndex:
    """G1: the operator entry to the leaf-4 search, rewritten by this PR.

    Nothing under ``tests/dq/strategies/sdca/`` referenced ``load_frozen_index``
    before this class. Flipping ``apply_calendar_delay``'s sign from
    ``- timedelta`` to ``+ timedelta`` therefore survived the whole suite. That
    is the highest-value gap in the review: a sign error here would shift every
    curve search's index *forward* into look-ahead, and the whole point of the
    delay is that it does not.
    """

    def test_signal_delay_trims_the_future_end_not_the_past_end(self, tmp_path: Path) -> None:
        last_bar = _write_btc_cache(tmp_path)
        dates, _prices, _risk, _weights = load_frozen_index(
            tmp_path, signal_delay_days=3, trade_start="2018-01-01"
        )
        # Exactly three days short of the last cached bar. With the sign
        # flipped, the cutoff lands past the end of the data, the filter keeps
        # everything, and this assertion reads max_date instead.
        assert dates[-1] == last_bar - timedelta(days=3)
        assert dates[-1] < last_bar

    @pytest.mark.parametrize(
        ("delay", "expected_trim"),
        [(0, 0), (1, 1), (3, 3), (10, 10)],
    )
    def test_a_larger_delay_trims_strictly_more(
        self, tmp_path: Path, delay: int, expected_trim: int
    ) -> None:
        last_bar = _write_btc_cache(tmp_path)
        dates, _prices, _risk, _weights = load_frozen_index(
            tmp_path, signal_delay_days=delay, trade_start="2018-01-01"
        )
        assert dates[-1] == last_bar - timedelta(days=expected_trim)

    def test_signal_delay_zero_keeps_the_whole_index(self, tmp_path: Path) -> None:
        last_bar = _write_btc_cache(tmp_path)
        dates, _prices, _risk, _weights = load_frozen_index(
            tmp_path, signal_delay_days=0, trade_start="2018-01-01"
        )
        assert dates[-1] == last_bar

    def test_trade_start_never_reintroduces_delayed_rows(self, tmp_path: Path) -> None:
        """``trade_start`` filters forward; the delay filters backward. Order matters."""
        last_bar = _write_btc_cache(tmp_path)
        dates, _prices, _risk, _weights = load_frozen_index(
            tmp_path, signal_delay_days=7, trade_start="2018-01-01"
        )
        assert dates[0] == date(2018, 1, 1)
        assert dates[-1] == last_bar - timedelta(days=7)

    def test_missing_cache_raises_before_anything_else(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="no cached BTC-USD"):
            load_frozen_index(tmp_path, signal_delay_days=3)

    def test_run_published_curve_search_reaches_the_search_through_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The operator command must feed the frozen index into the search.

        Pins the wiring itself: the sentinel dates/prices/risk and the resolved
        weights have to arrive at ``search_curve``, and the delay and trade-start
        the caller passed have to reach ``load_frozen_index``.
        """
        captured: dict[str, object] = {}
        sentinel_dates = pl.Series("date", [date(2019, 1, 1), date(2019, 2, 1)])
        sentinel_prices = pl.Series("price", [100.0, 110.0])
        sentinel_risk = pl.Series("risk", [20.0, 80.0])
        sentinel_weights = published_indicator_weights()

        def fake_load_frozen_index(
            cache_dir: Path,
            *,
            signal_delay_days: int = 3,
            trade_start: str = "2018-01-01",
        ) -> tuple[pl.Series, pl.Series, pl.Series, object]:
            captured["load_kwargs"] = {
                "cache_dir": cache_dir,
                "signal_delay_days": signal_delay_days,
                "trade_start": trade_start,
            }
            return sentinel_dates, sentinel_prices, sentinel_risk, sentinel_weights

        def fake_search_curve(
            dates: pl.Series,
            prices: pl.Series,
            risk: pl.Series,
            trials: list[dict[str, object]],
            **kwargs: object,
        ) -> None:
            captured["search_args"] = (dates, prices, risk, trials)
            captured["search_kwargs"] = kwargs
            return None

        monkeypatch.setattr(curve_optimize_module, "load_frozen_index", fake_load_frozen_index)
        monkeypatch.setattr(curve_optimize_module, "sample_curve_trials", lambda **kw: [{"a": 1.0}])
        monkeypatch.setattr(curve_optimize_module, "search_curve", fake_search_curve)

        run_published_curve_search(
            tmp_path,
            signal_delay_days=5,
            trade_start="2019-06-01",
            n_random=7,
            seed=11,
            initial_cash=2500.0,
        )

        assert captured["load_kwargs"] == {
            "cache_dir": tmp_path,
            "signal_delay_days": 5,
            "trade_start": "2019-06-01",
        }
        args = captured["search_args"]
        assert args is not None
        got_dates, got_prices, got_risk, got_trials = args
        assert got_dates is sentinel_dates
        assert got_prices is sentinel_prices
        assert got_risk is sentinel_risk
        assert got_trials == [{"a": 1.0}]
        search_kwargs = captured["search_kwargs"]
        assert search_kwargs is not None
        assert search_kwargs["initial_cash"] == 2500.0
        assert search_kwargs["frozen_weights"] is sentinel_weights
        assert search_kwargs["baseline"] == published_curve_shape()
