#!/usr/bin/env python3
"""Stage 4 walk-forward OOS validation of composite_rolling_window candidates
found by ``run_composite_rolling_window_sweep.py``.

Context: that sweep found the existing (unused) ``rolling_window`` knob on
``compute_composite_risk`` -- exposed end-to-end as ``composite_rolling_window``
on ``build_risk_index`` / ``evaluate_sdca_trial_curve_sim`` -- looks like it
un-saturates allocation on the frozen validated-baseline weights + published
curve. rolling_window=1095 in particular showed allocation actually dropping
mid-cycle (2022 mean 15.6%, 2025 mean 61.7%) instead of pinning near 97-99%,
while beating the baseline's in-sample return several-fold. rolling_window=730
posted the single best in-sample number (+1248%) but with allocation whipsawing
between ~0% and 100% inside single years -- a pattern that reads more like
in-sample overfit noise than genuine valuation-tracking.

Every other full-history-metric optimization tried in this project (curve
reshuffles, regime-switch variants) has looked great in-sample and failed
walk-forward OOS. Same gate applies here before any of this is credible:
frozen weights + frozen curve + frozen composite_rolling_window, run through
the identical 3-fold walk-forward / curve_simulator evaluator that produced
the documented +84.90% OOS baseline number.

Diagnostic only. Not touching RESEARCH_STATE.md/settings.json/presets.json --
report back for Chris's explicit accept/reject per the standing gate.

Usage:
    uv run python -m scripts.run_composite_rolling_window_walk_forward
"""

from __future__ import annotations

import functools
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

FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Two candidates from the sweep: 1095d looked most like genuine mid-cycle
# valuation-tracking; 730d posted the best in-sample number but with
# whipsaw-looking allocation, included as a "does the return survive OOS
# too" check against the more plausible candidate.
CANDIDATE_WINDOWS = [1095, 730]


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
    print(f"frozen weights + curve (unchanged from validated baseline): {FROZEN_WEIGHT_PARAMS}\n")

    baseline_trial = {**SDCA_SHAPE_DEFAULTS, **published_curve_shape().model_dump(), **FROZEN_WEIGHT_PARAMS}

    print("=== composite_rolling_window=None (validated baseline, for comparison) ===")
    result_baseline = run_sdca_walk_forward(
        dates,
        prices,
        [baseline_trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/published_baseline",
        extra_z=extra_z,
    )
    print_wf_row("rolling_window=None", result_baseline)
    print()

    for window in CANDIDATE_WINDOWS:
        bound_evaluator = functools.partial(evaluate_sdca_trial_curve_sim, composite_rolling_window=window)
        print(f"=== composite_rolling_window={window} ===")
        result = run_sdca_walk_forward(
            dates,
            prices,
            [baseline_trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=bound_evaluator,
            evaluator_label=f"curve_simulator/rolling_window_{window}",
            extra_z=extra_z,
        )
        print_wf_row(f"rolling_window={window}", result)
        print()

    print(
        "Diagnostic only (curve_simulator evaluator). Not touching RESEARCH_STATE.md/settings.json -- "
        "report full table to Chris for explicit accept/reject. A candidate that beats_flat_dca_oos=True "
        "with sensitivity stable=True here still needs the nautilus evaluator run before ship consideration."
    )


if __name__ == "__main__":
    run()
