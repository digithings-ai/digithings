"""Causal rolling-fold evaluation lookahead tripwire (#4804 Task 5).

Task-4's v4 gate is VOID: ``score_trial_on_folds`` builds the rails model on
each fold's IS window only, but ``RollingZRiskModel.rails`` joins requested
dates onto construction history — OOS dates miss the join, so every OOS rail
is null and nothing deploys. The fix (option ii) builds the rolling model on
the concatenated history ``is_start..oos_end`` per fold: trailing inputs
include OOS prices <= t (causally clean), and window/z are fixed constants,
so zero OOS parameter estimation occurs.

Tripwire contract: rolling rails at date t computed on the full calendar
EQUAL rails at t computed on the calendar truncated at t (same params), for
several t across a synthetic regime break. Any future-peeking operator fails
this; a trailing operator passes by construction.
"""

from __future__ import annotations

import importlib.util
import math
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    composite_weights_from_params,
    extra_indicators_for_window,
)
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    make_walk_forward_folds,
    score_trial_on_folds,
    shape_from_params,
    window_slice,
)

pytestmark = pytest.mark.unit

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "run_gold_curve_search.py"
)
WINDOW = 90
Z = 1.0


def _regime_break_series(n: int = 400, break_at: int = 250) -> tuple[list[date], list[float]]:
    """Deterministic oscillating climb with a 2x level break at ``break_at``."""
    start = date(2015, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n)]
    prices = []
    for i in range(n):
        level = 100.0 if i < break_at else 200.0
        drift = 1.0003**i
        wave = 1.0 + 0.15 * math.sin(2.0 * math.pi * i / 120.0)
        prices.append(level * drift * wave)
    return dates, prices


def _rolling_model(dates: list[date], prices: list[float]) -> RollingZRiskModel:
    return RollingZRiskModel(
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("price", prices, dtype=pl.Float64),
        window=WINDOW,
        z=Z,
    )


def _rails_row(model: RollingZRiskModel, day: date) -> tuple[float | None, ...]:
    frame = model.rails(pl.Series("date", [day], dtype=pl.Date))
    return (frame["low"][0], frame["median"][0], frame["high"][0])


def test_rolling_rails_full_calendar_equal_truncated_at_t() -> None:
    """The op itself is causal: full-history rails at t ignore inputs after t."""
    dates, prices = _regime_break_series()
    full = _rolling_model(dates, prices)
    for t_idx in (5, 50, 150, 249, 250, 251, 300, 399):
        day = dates[t_idx]
        trunc = _rolling_model(dates[: t_idx + 1], prices[: t_idx + 1])
        for got, want in zip(_rails_row(full, day), _rails_row(trunc, day), strict=True):
            if want is None:
                assert got is None
            else:
                assert got is not None
                assert got == pytest.approx(want)


def test_engine_is_path_starves_rolling_oos() -> None:
    """Pins the Task-4 void mechanism: IS-only fit + OOS rails join = all null."""
    dates, prices = _regime_break_series()
    folds, _holdout = make_walk_forward_folds(dates)
    params = {
        "buy_max_rate": 35.0,
        "buy_knee_risk": 45.0,
        "sell_knee_risk": 65.0,
        "sell_max_rate": 10.0,
        "buy_curvature": 1.0,
        "sell_curvature": 2.0,
        "valuation_weight": 1.0,
    }
    scores = score_trial_on_folds(
        params,
        dates,
        prices,
        folds,
        lambda d, p: _rolling_model(d, p),
        evaluate_sdca_trial_curve_sim,
        SdcaOptimizeObjective(),
    )
    assert len(scores) == len(folds)
    for score in scores:
        assert score.out_of_sample.capital_deployed_peak_pct == 0.0
    # Mechanism, not just symptom: the IS-only model has no OOS history, so
    # the rails join misses every OOS date (folds 0/1 do have cheap days
    # through a history-covering model — the next test deploys ~100% there).
    fold0 = folds[0]
    is_only = _rolling_model(*window_slice(dates, prices, fold0.is_start, fold0.is_end))
    oos_dates, _ = window_slice(dates, prices, fold0.oos_start, fold0.oos_end)
    rails = is_only.rails(pl.Series("date", oos_dates, dtype=pl.Date))
    assert rails["low"].null_count() == len(oos_dates)
    assert rails["median"].null_count() == len(oos_dates)
    assert rails["high"].null_count() == len(oos_dates)


def _load_gate_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("run_gold_curve_search", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_causal_fold_wiring_trades_and_matches_truncated() -> None:
    """The shipped wiring (option ii): concatenated-history model per fold.

    RED before the wiring (no such helper on the script); GREEN after. Not
    vacuous: on this same synthetic calendar the engine IS-only path deploys
    0% (test above), so a helper that delegated to it could not pass the
    non-null/deployment asserts below.
    """
    script = _load_gate_script()
    # Break lands in the holdout tail (past fold-2 OOS end at i=320), so every
    # gate fold oscillates through cheap/rich and must trade; the mid-calendar
    # break variant above already covers break-crossing causality.
    dates, prices = _regime_break_series(break_at=330)
    folds, _holdout = make_walk_forward_folds(dates)
    weights = SdcaCompositeWeights(valuation=1.0)
    shape = shape_from_params(
        {
            "buy_max_rate": 35.0,
            "buy_knee_risk": 45.0,
            "sell_knee_risk": 65.0,
            "sell_max_rate": 10.0,
            "buy_curvature": 1.0,
            "sell_curvature": 2.0,
        }
    )
    for fold in folds:
        model = script.causal_rolling_model_for_fold(dates, prices, fold, window=WINDOW, z=Z)
        assert isinstance(model, RollingZRiskModel)
        # Causality through the helper's own model: OOS rails equal truncated rails.
        oos_dates, oos_prices = window_slice(dates, prices, fold.oos_start, fold.oos_end)
        nulls = 0
        for day in oos_dates[::37]:
            t_idx = dates.index(day)
            trunc = _rolling_model(dates[: t_idx + 1], prices[: t_idx + 1])
            for got, want in zip(_rails_row(model, day), _rails_row(trunc, day), strict=True):
                if want is None:
                    nulls += 1
                    assert got is None
                else:
                    assert got is not None
                    assert got == pytest.approx(want)
        assert nulls == 0, "concatenated history must cover every OOS date"
        # The helper's model scores OOS without starvation.
        extras = extra_indicators_for_window(oos_dates, dates, {}, weights)
        metrics = evaluate_sdca_trial_curve_sim(
            oos_dates, oos_prices, model, shape, weights.valuation, extras
        )
        assert math.isfinite(metrics.vs_flat_dca_pct)
        assert metrics.capital_deployed_peak_pct > 0.0
    # Full gate entry point exists with the causal-rolling contract.
    assert callable(getattr(script, "run_causal_rolling_gate", None))
    gate = script.run_causal_rolling_gate(
        dates,
        prices,
        {
            "buy_max_rate": 35.0,
            "buy_knee_risk": 45.0,
            "sell_knee_risk": 65.0,
            "sell_max_rate": 10.0,
            "buy_curvature": 1.0,
            "sell_curvature": 2.0,
            "valuation_weight": 1.0,
        },
        window=WINDOW,
        z=Z,
        extra_z={},
        weights=composite_weights_from_params({"valuation_weight": 1.0}),
    )
    assert len(gate["per_fold"]) == len(folds)
    assert all(f["oos_capital_deployed_peak_pct"] > 0.0 for f in gate["per_fold"])
