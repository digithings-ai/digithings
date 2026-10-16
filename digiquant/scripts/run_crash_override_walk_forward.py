#!/usr/bin/env python3
"""Does the ALREADY-BUILT crash circuit-breaker fix fold 1's drawdown?

Context: 14+ leads on this project (weight reweighting, indicator
diversification, curve-search objectives, Stage-3 index leakage) have all
converged to the same ~50-58% fold-1 (COVID crash, 2019-07-01..2021-11-20)
walk-forward OOS drawdown, always above the 50% ``max_drawdown_cap_pct``
gate. While investigating why the fold-causal-index experiment
(``run_fold_causal_curve_search.py``) still failed, found that
``curve_sim.py``'s ``evaluate_sdca_trial_curve_sim`` and
``nautilus_evaluator.py``'s ``evaluate_sdca_trial_nautilus`` both already
wire in ``crash_override.apply_crash_override`` -- an independent
circuit-breaker that force-pushes risk toward a sell-favorable override
whenever ``fast_crash_vol_z`` (a short-window realized-vol spike detector)
fires, regardless of what the slow macro composite (power_law/m2/dxy) says.

It defaults to ``crash_override_enabled=False`` in BOTH evaluators, and
every walk-forward script across this whole project (including every one
run this session) has passed the evaluator functions directly to
``run_sdca_walk_forward`` without wrapping them in
``functools.partial(..., crash_override_enabled=True)``. The mechanism has
therefore never been exercised in any of the 14+ prior dead ends.

This script re-runs the validated baseline (power_law=1.0/m2=0.5/dxy=0.5,
default curve shape) through walk-forward with the crash override turned ON
at its coded defaults (trigger_z=-2.0, ramp_z=1.0, override_risk=95.0) and
compares fold 1's OOS drawdown/feasibility against it OFF.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_crash_override_walk_forward.py
"""

from __future__ import annotations

import functools
from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import SdcaCompositeWeights
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

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)


def print_result(label: str, result) -> None:
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
    print(
        f"    sensitivity: stable={result.sensitivity.stable}  "
        f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp\n"
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    wf_dates, wf_prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(wf_dates, wf_prices, data_path=None, data_dir=str(cache_dir))
    trial = {
        **SDCA_SHAPE_DEFAULTS,
        "power_law_weight": FROZEN_WEIGHTS.power_law,
        "m2_weight": FROZEN_WEIGHTS.m2,
        "dxy_weight": FROZEN_WEIGHTS.dxy,
    }
    print(f"baseline trial (validated shape defaults + power_law/m2/dxy = 1.0/0.5/0.5): {trial}\n")

    evaluators = {
        "curve_simulator/override_OFF": evaluate_sdca_trial_curve_sim,
        "curve_simulator/override_ON": functools.partial(evaluate_sdca_trial_curve_sim, crash_override_enabled=True),
        "nautilus/override_OFF": evaluate_sdca_trial_nautilus,
        "nautilus/override_ON": functools.partial(evaluate_sdca_trial_nautilus, crash_override_enabled=True),
    }
    for label, evaluator in evaluators.items():
        result = run_sdca_walk_forward(
            wf_dates,
            wf_prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label=f"{label}/crash_override_check",
            extra_z=extra_z,
        )
        print_result(label, result)

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
