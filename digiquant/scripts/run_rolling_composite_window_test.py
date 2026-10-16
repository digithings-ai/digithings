#!/usr/bin/env python3
"""Test Chris's hypothesis (2026-09-07): BTC's realized volatility has compressed
over time, so z-scoring indicators against the *whole* history under-registers
recent extremes ("compressive behavior... risk of not catching certain
extensions, tops and bottoms"). Proposed fix: a rolling (progressive-at-start,
then fixed-window) z-score instead of whole-history.

This is RESEARCH_STATE.md's backlog item 1 ("Fresh Stage-A weight search on
the dead-zone-fixed rolling composite... scored against the corrected true
baseline, not the live 5-weight config") -- an earlier run (commit
b38c89440) tested the *composite*-level rolling re-normalization
(``compute_composite_risk``'s ``rolling_window`` / ``composite_rolling_window``)
at 3-5yr windows, but only against the broken live 5-weight index (result:
-46% to -51% OOS). This script runs it against the actual validated
3-weight baseline (power_law=1.0, m2=0.5, dxy=0.5) instead.

``causal_rolling_z`` (and therefore this composite-level knob) already ramps
up progressively via ``min_samples`` before reaching the full window --
exactly the "progressively, then move forward" mechanic Chris described --
so no new normalization code was needed, just a proper run of the existing
knob at 2/3/4/5yr against the right index, held fixed at the current
validated curve shape (index-then-curve protocol: settle the index before
touching the curve). See ``run_rolling_composite_stage_a_and_curve.py`` for
the follow-up weight/curve re-derivation under the winning window.

Diagnostic only. No production writes.

Usage:
    uv run python scripts/run_rolling_composite_window_test.py
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Validated 3-weight baseline (RESEARCH_STATE.md "current best validated
# candidate", 2026-09-03) + published btc_optimized curve shape, held fixed.
# Only the composite normalization window varies across runs below.
TRIAL = {
    **SDCA_SHAPE_DEFAULTS,
    "buy_max_rate": 35.5,
    "buy_knee_risk": 24.1,
    "sell_knee_risk": 71.9,
    "sell_max_rate": 21.0,
    "buy_curvature": 1.3,
    "sell_curvature": 4.0,
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

WINDOWS = {
    "whole-history (current)": None,
    "2yr (730d)": 730,
    "3yr (1095d)": 1095,
    "4yr (1460d)": 1460,
    "5yr (1825d)": 1825,
}


def run(data_dir: Path = DEFAULT_DATA_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(data_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(data_dir))
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    print(
        f"{'window':>26} | {'mean_IS':>9} | {'mean_OOS':>9} | {'IS-OOS gap':>10} "
        f"| {'holdout':>9} | {'beats_flat_oos':>14}"
    )
    for label, window in WINDOWS.items():
        evaluator = partial(
            evaluate_sdca_trial_curve_sim,
            composite_rolling_window=window,
            composite_rolling_min_samples=20 if window is not None else None,
        )
        result = run_sdca_walk_forward(
            dates,
            prices,
            [TRIAL],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label=f"curve_simulator/rolling={window}",
            extra_z=extra_z,
        )
        holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
        print(
            f"{label:>26} | {result.mean_is_vs_flat_dca_pct:9.2f} | "
            f"{result.mean_oos_vs_flat_dca_pct:9.2f} | {result.is_oos_gap_pct:10.2f} | "
            f"{holdout:9.2f} | {str(result.beats_flat_dca_oos):>14}"
        )
        for fs in result.fold_scores:
            print(
                f"    fold {fs.fold.fold}: IS[{fs.fold.is_start}..{fs.fold.is_end}]="
                f"{fs.in_sample.vs_flat_dca_pct:8.2f}%  OOS[{fs.fold.oos_start}..{fs.fold.oos_end}]="
                f"{fs.out_of_sample.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}"
            )


if __name__ == "__main__":
    run()
