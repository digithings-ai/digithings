#!/usr/bin/env python3
"""Follow-up to ``run_rolling_composite_window_test.py``: that script showed
2yr-5yr rolling composite normalization uniformly beats whole-history on
holdout (36.35% vs 3.25%) at a lower but far more consistent searched-OOS
(~64.5% vs 84.9%), using the *existing* validated weights/curve unchanged.

RESEARCH_STATE.md backlog item 1 goes further: re-derive Stage A weights
under the rolling composite too (previously only tested against the broken
live 5-weight index), then refit the curve -- "index then curve, repeat".
This script does both, restricted to the validated 3-weight family
(power_law/m2/dxy) since that IS "the corrected true baseline." Window
fixed at 1095d (3yr): the prior script showed window length doesn't matter
in 2yr-5yr, so there's no reason to search it further.

Four parts:
  A. Stage A weight re-derivation (``optimize_stage_a_by_backtest``) at
     rolling=1095d, curve held at the published shape (don't touch the
     curve while the index is still being resolved).
  B. Full walk-forward validation of the new weights + published curve
     (rolling=1095d) -- isolates the weight-search delta.
  C. Curve refit: build a frozen, full-history rolling-normalized index at
     the new weights, run the standard curve search
     (``sample_curve_trials`` / ``search_curve``) instead of carrying over
     the whole-history-fit 24.1/71.9 curve.
  D. Full walk-forward validation of the final candidate (new weights + new
     curve, rolling=1095d) -- the number that actually matters.

Result (2026-09-07 run): Part A's IS-only ranking picked a weight mix
dominated by one outlier fold (mean_IS=216%, one fold at +390%) that does
NOT clearly improve OOS/holdout over just keeping the old weights (67.55%
OOS / 30.75% holdout vs 64.51% / 36.35% -- roughly a wash, holdout actually
a bit worse). Part C's curve refit is worse than a wash: it looks great on
the frozen, non-walk-forward index (risk_adjusted_return 118 vs baseline
51) but catastrophically overfits -- Part D's walk-forward validation comes
back at -26.14% mean OOS with every fold infeasible. The standard curve
search (``search_curve``) fits against the *entire* 2018-2026 sample at
once, so it "sees" late-sample risk extremes that early walk-forward IS
windows (e.g. fold 0's 2014-2017) never do -- a stark demonstration of why
the protocol requires walk-forward validation before any accept, not just
an in-sample risk_adjusted_return.

Conclusion: of everything tried across this script and
``run_rolling_composite_window_test.py``, the single best-validated
candidate remains the rolling window *alone* (1095d, same weights/curve
as today) -- re-deriving weights and refitting the curve did not improve
on it and the curve refit specifically produced a badly overfit result.

Diagnostic only. No production writes.

Usage:
    uv run python scripts/run_rolling_composite_stage_a_and_curve.py
"""

from __future__ import annotations

from datetime import date
from functools import partial
from pathlib import Path

import polars as pl

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import (
    apply_calendar_delay,
    published_curve_shape,
    sample_curve_trials,
    search_curve,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import build_extra_indicators
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    drop_extras_missing_sources,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.weight_search import optimize_stage_a_by_backtest

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = DIGIQUANT_ROOT / "data" / "price-history"
ROLLING_WINDOW = 1095
ROLLING_MIN_SAMPLES = 20


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>50} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    for fs in result.fold_scores:
        print(
            f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={fs.out_of_sample.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}"
        )


def build_frozen_rolling_index(
    weights,
    *,
    rolling_window: int,
    rolling_min_samples: int,
    cache_dir: Path,
    trade_start: str = "2018-01-01",
):
    """Mirrors ``curve_optimize.load_frozen_index`` but with composite-level rolling z on."""
    ohlcv = load_cached("BTC-USD", cache_dir)
    ohlcv = apply_calendar_delay(ohlcv, 3)
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    d = ohlcv[ts_col]
    if d.dtype != pl.Date:
        d = d.cast(pl.Date)
    sources = load_sdca_extra_sources(cache_dir)
    resolved = drop_extras_missing_sources(weights, sources)
    extras = build_extra_indicators(d, ohlcv["close"], resolved, sources)
    index = build_risk_index(
        d,
        ohlcv["close"],
        BtcPowerLawRiskModel(load_coefficients()),
        extra_indicators=extras or None,
        power_law_weight=resolved.power_law,
        composite_rolling_window=rolling_window,
        composite_rolling_min_samples=rolling_min_samples,
    )
    cutoff = date.fromisoformat(trade_start)
    window = index.filter(pl.col("date") >= cutoff)
    return window["date"], window["price"], window["risk"], resolved


def run(data_dir: Path = DEFAULT_DATA_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(data_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(data_dir))
    published_shape = published_curve_shape()
    rolling_evaluator = partial(
        evaluate_sdca_trial_curve_sim,
        composite_rolling_window=ROLLING_WINDOW,
        composite_rolling_min_samples=ROLLING_MIN_SAMPLES,
    )

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"published curve shape (held fixed for Parts A/B): {published_shape}\n")

    print("=== Part A: Stage A weight re-derivation (rolling=1095d, curve=published) ===")
    stage_a = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=rolling_evaluator,
        shape=published_shape,
        search_names=("m2", "dxy"),
        grid=(0.0, 0.25, 0.5, 0.75, 1.0),
        power_law_grid=(0.0, 0.5, 1.0),
    )
    print("validated baseline weights (whole-history-derived): power_law=1.0, m2=0.5, dxy=0.5")
    print(f"new winning weights (rolling-derived):               {stage_a.weights.model_dump()}")
    print(
        f"mean_IS={stage_a.mean_is_vs_flat_dca_pct:.2f}  "
        f"mean_OOS={stage_a.mean_oos_vs_flat_dca_pct:.2f} (OOS not used to rank)"
    )
    print(f"evaluated {stage_a.num_evaluations} weight combinations\n")

    print("=== Part B: walk-forward validation of new weights + published curve (rolling=1095d) ===")
    trial_b = {
        **SDCA_SHAPE_DEFAULTS,
        "buy_max_rate": published_shape.buy_max_rate,
        "buy_knee_risk": published_shape.buy_knee_risk,
        "sell_knee_risk": published_shape.sell_knee_risk,
        "sell_max_rate": published_shape.sell_max_rate,
        "buy_curvature": published_shape.buy_curvature,
        "sell_curvature": published_shape.sell_curvature,
        "power_law_weight": stage_a.weights.power_law,
        "m2_weight": stage_a.weights.m2,
        "dxy_weight": stage_a.weights.dxy,
    }
    result_b = run_sdca_walk_forward(
        dates,
        prices,
        [trial_b],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=rolling_evaluator,
        evaluator_label="curve_simulator/rolling=1095/new_weights",
        extra_z=extra_z,
    )
    print_wf_row("new weights + published curve", result_b)
    print()

    print("=== Part C: curve refit on frozen rolling-normalized index (new weights) ===")
    c_dates, c_prices, c_risk, resolved_weights = build_frozen_rolling_index(
        stage_a.weights,
        rolling_window=ROLLING_WINDOW,
        rolling_min_samples=ROLLING_MIN_SAMPLES,
        cache_dir=data_dir,
    )
    years = sorted({d.year for d in c_dates})
    print("max risk per year on the new frozen rolling index:")
    c_df = pl.DataFrame({"date": c_dates, "risk": c_risk})
    for y in years:
        m = c_df.filter(pl.col("date").dt.year() == y)["risk"].max()
        print(f"  {y}: {m:.1f}")

    trials = sample_curve_trials(n_random=4000, seed=42)
    curve_result = search_curve(
        c_dates,
        c_prices,
        c_risk,
        trials,
        initial_cash=1000.0,
        baseline=published_shape,
        frozen_weights=resolved_weights,
        evaluator="curve_simulator",
    )
    winner_shape = curve_result.best.shape
    print(f"\nevaluated {curve_result.num_evaluations} trials ({curve_result.num_feasible} feasible)")
    print(f"winning shape: {winner_shape}")
    print(f"reject_reasons (winner): {curve_result.best.reject_reasons}")
    print(
        f"risk_adjusted_return: {curve_result.best.risk_adjusted_return:.4f} "
        f"vs baseline(published curve on this index): {curve_result.baseline.risk_adjusted_return:.4f}"
    )
    print(
        f"total_return_pct: {curve_result.best.total_return_pct:.2f}%  "
        f"max_drawdown_pct: {curve_result.best.max_drawdown_pct:.2f}%"
    )
    print(f"vs_flat_dca_pct: {curve_result.best.vs_flat_dca_pct:.2f}%\n")

    print("=== Part D: walk-forward validation of final candidate (new weights + new curve, rolling=1095d) ===")
    trial_d = {
        **SDCA_SHAPE_DEFAULTS,
        "buy_max_rate": winner_shape.buy_max_rate,
        "buy_knee_risk": winner_shape.buy_knee_risk,
        "sell_knee_risk": winner_shape.sell_knee_risk,
        "sell_max_rate": winner_shape.sell_max_rate,
        "buy_curvature": winner_shape.buy_curvature,
        "sell_curvature": winner_shape.sell_curvature,
        "power_law_weight": stage_a.weights.power_law,
        "m2_weight": stage_a.weights.m2,
        "dxy_weight": stage_a.weights.dxy,
    }
    result_d = run_sdca_walk_forward(
        dates,
        prices,
        [trial_d],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=rolling_evaluator,
        evaluator_label="curve_simulator/rolling=1095/final_candidate",
        extra_z=extra_z,
    )
    print_wf_row("new weights + new curve (final)", result_d)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(f"{'whole-history, current weights+curve':>50} | OOS  84.90 | holdout   3.25  (from window-test script)")
    print(f"{'rolling=1095d, current weights+curve':>50} | OOS  64.51 | holdout  36.35  (from window-test script)")
    b_holdout = result_b.holdout_metrics.vs_flat_dca_pct if result_b.holdout_metrics else float("nan")
    d_holdout = result_d.holdout_metrics.vs_flat_dca_pct if result_d.holdout_metrics else float("nan")
    print(
        f"{'rolling=1095d, new weights + published curve':>50} | "
        f"OOS {result_b.mean_oos_vs_flat_dca_pct:6.2f} | holdout {b_holdout:6.2f}"
    )
    print(
        f"{'rolling=1095d, new weights + new curve (final)':>50} | "
        f"OOS {result_d.mean_oos_vs_flat_dca_pct:6.2f} | holdout {d_holdout:6.2f}"
    )


if __name__ == "__main__":
    run()
