#!/usr/bin/env python3
"""Stage 4 walk-forward OOS validation of the top allocation-responsiveness
curve candidates found by ``run_allocation_responsiveness_search.py``.

Context: Chris flagged (2026-09-18) that the validated baseline's published
curve pins allocation near 97-99% from 2024 on and barely moves -- close to
buy-and-hold, not a real dynamic strategy. The responsiveness search scored
3,635 wide-knee curve candidates (same power_law=1.0/m2=0.5/dxy=0.5 frozen
index as the validated baseline) jointly on risk_adjusted_return and a new
allocation-responsiveness metric (mean |Δallocation%| per day, restricted to
bars within 25% of trailing-1y high -- i.e. does it trim/rebuy mid-bull).
The top 3 survivors (>=60% of baseline's risk_adjusted_return) all roughly
triple the responsiveness score. This script is the required next gate per
RESEARCH_STATE.md's standard trial protocol: same 3-fold walk-forward split
and same curve_simulator evaluator that produced the documented +84.90% OOS
baseline number, run on each fixed candidate (weights + curve both frozen,
nothing re-searched here).

Diagnostic only. Not touching RESEARCH_STATE.md/settings.json/presets.json --
report back for Chris's explicit accept/reject per the standing gate.

Usage:
    uv run python -m scripts.run_allocation_responsiveness_walk_forward
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import published_curve_shape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Weights unchanged from the validated baseline -- only the curve shape
# differs between candidates and against the published baseline curve.
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Top 3 by allocation_responsiveness among candidates clearing >=60% of the
# baseline's risk_adjusted_return, from run_allocation_responsiveness_search.py.
CANDIDATES = {
    "resp_top1 (rar=22.69 resp=0.472)": {
        "buy_max_rate": 34.0,
        "buy_knee_risk": 37.3,
        "sell_knee_risk": 76.1,
        "sell_max_rate": 57.0,
        "buy_curvature": 4.52,
        "sell_curvature": 1.23,
    },
    "resp_top2 (rar=20.34 resp=0.470)": {
        "buy_max_rate": 18.5,
        "buy_knee_risk": 43.8,
        "sell_knee_risk": 74.4,
        "sell_max_rate": 63.4,
        "buy_curvature": 4.98,
        "sell_curvature": 1.57,
    },
    "resp_top3 (rar=18.73 resp=0.468)": {
        "buy_max_rate": 15.0,
        "buy_knee_risk": 30.0,
        "sell_knee_risk": 70.0,
        "sell_max_rate": 70.0,
        "buy_curvature": 2.50,
        "sell_curvature": 2.50,
    },
}


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>40} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
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
    print(
        f"    sensitivity: stable={result.sensitivity.stable}  "
        f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp"
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights (unchanged from validated baseline): {FROZEN_WEIGHT_PARAMS}\n")

    print("=== published btc_optimized curve (validated baseline, for comparison) ===")
    baseline_trial = {**SDCA_SHAPE_DEFAULTS, **published_curve_shape().model_dump(), **FROZEN_WEIGHT_PARAMS}
    result_baseline = run_sdca_walk_forward(
        dates,
        prices,
        [baseline_trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/published_baseline",
        extra_z=extra_z,
    )
    print_wf_row("published_baseline", result_baseline)
    print()

    for name, shape_params in CANDIDATES.items():
        trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **FROZEN_WEIGHT_PARAMS}
        print(f"=== {name} ===")
        print(f"    curve: {shape_params}")
        result = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_curve_sim,
            evaluator_label=f"curve_simulator/{name}",
            extra_z=extra_z,
        )
        print_wf_row(name, result)
        print()

    print(
        "Diagnostic only (curve_simulator evaluator). Not touching RESEARCH_STATE.md/settings.json -- "
        "report full table to Chris for explicit accept/reject. A candidate that beats_flat_dca_oos=True "
        "with sensitivity stable=True here still needs the nautilus evaluator run before ship consideration."
    )


if __name__ == "__main__":
    run()
