#!/usr/bin/env python3
"""Stage 4 walk-forward on risk_adj_search_v1 with a WIDER dead zone.

risk_adj_search_v1's reproduced shape (buy_knee_risk=45, sell_knee_risk=50 --
a 5-point dead zone) passes Stage 4 nominally (beats_flat_dca_oos=True) but
fails on closer inspection: sensitivity is unstable (+/-9.04pp) and fold 1
goes infeasible with OOS capital_deployed_pct collapsing to -390%, i.e. the
narrow dead zone causes pathological churn in at least one regime (see
run_risk_adj_search_v1_walk_forward.py).

Chris's direction (selecting between "re-run the curve search with a floor
that widens the dead-zone slightly to kill the fold-1 churn pathology while
keeping most of the frequent-cycling behavior" vs treating this as a dead
end): widen the dead zone.

run_risk_adj_search_v1_dead_zone_sweep.py already produced an in-sample
risk_adjusted_return-vs-width frontier holding risk_adj_search_v1's crossing
point (47.5) and rates/curvatures (buy_max_rate=35, sell_max_rate=25,
buy_curvature=1.5, sell_curvature=1.0) fixed. Widths 5.0/7.5/10.0 sit on the
same trade-day plateau (2741, i.e. almost the same cycling frequency as the
original); 15.0/20.0 drop to a lower-frequency plateau (1987). That sweep is
in-sample only and does not test fold-level OOS feasibility -- this script
runs the actual Stage 4 gate (both evaluators) on each width, via
dead_zone_shape_params() to derive the exact knees, specifically checking
whether fold 1 becomes feasible and sensitivity becomes stable, not just
whether beats_flat_dca_oos stays True.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full table to Chris for explicit accept first.

Usage:
    uv run python scripts/run_risk_adj_search_v1_wider_dead_zone_walk_forward.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import dead_zone_shape_params
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

# risk_adj_search_v1's reproduced rates/curvatures and crossing point (the
# midpoint of its two knees, 45/50 -> 47.5). Only the dead-zone width varies.
CROSSING_RISK = 47.5
BUY_MAX_RATE = 35.0
SELL_MAX_RATE = 25.0
BUY_CURVATURE = 1.5
SELL_CURVATURE = 1.0

# Candidates from run_risk_adj_search_v1_dead_zone_sweep.py's in-sample
# frontier: 7.5/10.0 stay on the original's trade-day plateau (2741, nearly
# the same cycling frequency); 15.0/20.0 drop to the next plateau (1987) as a
# clearly-wider fallback if the small widenings don't fix fold 1.
CANDIDATE_WIDTHS = (25.0, 30.0, 40.0, 50.0)


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>28} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
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
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}")
    print(
        f"fixed crossing_risk={CROSSING_RISK} buy_max_rate={BUY_MAX_RATE} sell_max_rate={SELL_MAX_RATE} "
        f"buy_curvature={BUY_CURVATURE} sell_curvature={SELL_CURVATURE}\n"
    )

    summary_rows = []
    for width in CANDIDATE_WIDTHS:
        shape_params = dead_zone_shape_params(
            CROSSING_RISK, width, BUY_MAX_RATE, SELL_MAX_RATE, BUY_CURVATURE, SELL_CURVATURE
        )
        trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **FROZEN_WEIGHT_PARAMS}

        print(f"=== width={width} (knees {shape_params['buy_knee_risk']:.2f}/{shape_params['sell_knee_risk']:.2f}) ===")

        result_cs = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_curve_sim,
            evaluator_label=f"curve_simulator/width={width}",
            extra_z=extra_z,
        )
        print_wf_row(f"curve_simulator w={width}", result_cs)

        result_nt = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_nautilus,
            evaluator_label=f"nautilus/width={width}",
            extra_z=extra_z,
        )
        print_wf_row(f"nautilus w={width}", result_nt)
        print()

        summary_rows.append((width, result_cs, result_nt))

    print("=== Summary (mean_OOS / holdout vs-flat-DCA %, all folds feasible?, sensitivity stable?) ===")
    print(
        f"{'width=5.0 (original, narrow)':>32} | cs OOS  32.79 holdout  19.01 fold1_feasible=False stable=False"
    )
    for width, result_cs, result_nt in summary_rows:
        cs_all_feasible = all(fs.feasible for fs in result_cs.fold_scores)
        nt_all_feasible = all(fs.feasible for fs in result_nt.fold_scores)
        cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
        nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
        print(
            f"{f'width={width} curve_sim':>32} | OOS {result_cs.mean_oos_vs_flat_dca_pct:7.2f} "
            f"| holdout {cs_holdout:7.2f} | all_folds_feasible={cs_all_feasible} "
            f"| sensitivity_stable={result_cs.sensitivity.stable}"
        )
        print(
            f"{f'width={width} nautilus':>32} | OOS {result_nt.mean_oos_vs_flat_dca_pct:7.2f} "
            f"| holdout {nt_holdout:7.2f} | all_folds_feasible={nt_all_feasible} "
            f"| sensitivity_stable={result_nt.sensitivity.stable}"
        )

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
