#!/usr/bin/env python3
"""Stage 4 walk-forward on the top candidates from
run_drawdown_constrained_curve_search.py -- shapes that clear an explicit
full-history max-drawdown ceiling (20/25/30%), instead of just maximizing
the unconstrained risk_adjusted_return ratio.

Chris's target (2026-09-13): equity drawdown "in or around 30%, 20% at
most," achieved by actively de-risking (selling) on the way up and not
staying over-exposed into a crash, while still catching every long-term
bottom.

Full-history in-sample clearing a ceiling does not guarantee any single
fold does -- in particular fold 1's OOS window (2019-07-01..2021-11-20,
the COVID crash) has been the hard case for every curve tested this session.
This script runs the real Stage 4 gate (both evaluators) on three
candidates spanning the return/drawdown frontier from that search, checking
per-fold OOS drawdown specifically, not just the headline OOS return.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full table to Chris for explicit accept first.

Usage:
    uv run python scripts/run_drawdown_constrained_candidates_walk_forward.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Top candidates from run_drawdown_constrained_curve_search.py, one per
# drawdown ceiling bucket (20/25/30%), each the best full-history
# total_return_pct within its bucket.
CANDIDATES = {
    "ceiling30_dd27.6": {
        "buy_max_rate": 38.0,
        "buy_knee_risk": 39.1,
        "sell_knee_risk": 53.5,
        "sell_max_rate": 68.2,
        "buy_curvature": 1.84,
        "sell_curvature": 1.12,
    },
    "ceiling25_dd24.3": {
        "buy_max_rate": 25.0,
        "buy_knee_risk": 45.0,
        "sell_knee_risk": 55.0,
        "sell_max_rate": 90.0,
        "buy_curvature": 4.00,
        "sell_curvature": 1.50,
    },
    "ceiling20_dd19.6": {
        "buy_max_rate": 15.0,
        "buy_knee_risk": 45.0,
        "sell_knee_risk": 55.0,
        "sell_max_rate": 90.0,
        "buy_curvature": 4.00,
        "sell_curvature": 1.50,
    },
}


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>30} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    for fs in result.fold_scores:
        oos = fs.out_of_sample
        print(
            f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:6.2f}%"
        )
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:.2f}%  vs_lump={h.vs_lump_pct:.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.2f}%  max_drawdown={h.max_drawdown_pct:.2f}%"
        )
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}\n")

    summary = []
    for name, shape_params in CANDIDATES.items():
        trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **FROZEN_WEIGHT_PARAMS}
        print(f"=== {name}: {shape_params} ===")

        result_cs = run_sdca_walk_forward(
            dates, prices, [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_curve_sim,
            evaluator_label=f"curve_simulator/{name}",
            extra_z=extra_z,
        )
        print_wf_row(f"curve_simulator {name}", result_cs)

        result_nt = run_sdca_walk_forward(
            dates, prices, [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_nautilus,
            evaluator_label=f"nautilus/{name}",
            extra_z=extra_z,
        )
        print_wf_row(f"nautilus {name}", result_nt)
        print()

        summary.append((name, result_cs, result_nt))

    print("=== Summary (mean_OOS / holdout vs-flat-DCA %, worst-fold OOS drawdown, feasibility, sensitivity) ===")
    for name, result_cs, result_nt in summary:
        worst_dd_cs = max(fs.out_of_sample.max_drawdown_pct for fs in result_cs.fold_scores)
        all_feasible_cs = all(fs.feasible for fs in result_cs.fold_scores)
        cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
        cs_holdout_vs_lump = result_cs.holdout_metrics.vs_lump_pct if result_cs.holdout_metrics else float("nan")
        print(
            f"{name:>20} curve_sim | OOS {result_cs.mean_oos_vs_flat_dca_pct:7.2f} | holdout {cs_holdout:7.2f} "
            f"(vs_lump {cs_holdout_vs_lump:7.2f}) | worst_fold_OOS_dd {worst_dd_cs:6.2f}% "
            f"| all_folds_feasible={all_feasible_cs} | sensitivity_stable={result_cs.sensitivity.stable}"
        )
        worst_dd_nt = max(fs.out_of_sample.max_drawdown_pct for fs in result_nt.fold_scores)
        all_feasible_nt = all(fs.feasible for fs in result_nt.fold_scores)
        nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
        nt_holdout_vs_lump = result_nt.holdout_metrics.vs_lump_pct if result_nt.holdout_metrics else float("nan")
        print(
            f"{name:>20} nautilus  | OOS {result_nt.mean_oos_vs_flat_dca_pct:7.2f} | holdout {nt_holdout:7.2f} "
            f"(vs_lump {nt_holdout_vs_lump:7.2f}) | worst_fold_OOS_dd {worst_dd_nt:6.2f}% "
            f"| all_folds_feasible={all_feasible_nt} | sensitivity_stable={result_nt.sensitivity.stable}"
        )

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
