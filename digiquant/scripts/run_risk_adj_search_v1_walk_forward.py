#!/usr/bin/env python3
"""Stage 4 walk-forward for risk_adj_search_v1 -- the trial Chris asked to
revisit ("lowest drawdown, highest total returns... cycling between
overbought and oversold more frequently").

risk_adj_search_v1.json (.scratch/tearsheets/, gitignored, generated
2026-09-04) was an ad-hoc single-shot full-history run with no recorded CLI
invocation and no full curve shape (only buy_knee_risk/sell_knee_risk are
stored). Its knees exactly match the widened CURVE_SEARCH_BOUNDS/
DEFAULT_COARSE_GRID introduced by commit 2661badd9 ("widen curve search +
switch optimizer objective to risk-adjusted return"), and that commit's
own reported before/after numbers (-30.9% -> +247.6% vs lump, 70.5% ->
31.2% max drawdown) match the trial almost exactly. Re-running
sample_curve_trials()/search_curve() (same functions run_published_curve_
search() calls) frozen at power_law=1.0/m2=0.5/dxy=0.5 reproduced it near
-identically (knees identical; headline figures within ~2%, consistent with
a few days of cache drift since Sep 4) and recovered the full shape the
trial JSON never stored: buy_max_rate=35.0, sell_max_rate=25.0,
buy_curvature=1.5, sell_curvature=1.0.

Its own embedded notes already say beats_flat_dca_oos=false -- that search
never ran walk-forward, only a full-history in-sample fit. This script runs
the actual Stage 4 gate on the exact reproduced weights+shape before it can
be treated as a candidate baseline, per the standing playbook rule (do not
touch settings.json/RESEARCH_STATE.md until beats_flat_dca_oos=True with a
stable sensitivity check).

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full IS/OOS table + sensitivity check to Chris for explicit accept
first.

Usage:
    uv run python scripts/run_risk_adj_search_v1_walk_forward.py
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

# Same weights as the currently "validated" baseline -- risk_adj_search_v1
# only changed the curve, not the composite.
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Reproduced via scripts run against curve_optimize.sample_curve_trials()/
# search_curve() frozen on the same weights (see module docstring). Knees
# match risk_adj_search_v1.json's curve_knees exactly; the other four
# params are the ones that JSON never recorded.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 35.0,
    "buy_knee_risk": 45.0,
    "sell_knee_risk": 50.0,
    "sell_max_rate": 25.0,
    "buy_curvature": 1.5,
    "sell_curvature": 1.0,
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
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    trial = {**SDCA_SHAPE_DEFAULTS, **FROZEN_SHAPE_PARAMS, **FROZEN_WEIGHT_PARAMS}

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}")
    print(f"reproduced risk_adj_search_v1 curve shape: {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/risk_adj_search_v1",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print("=== nautilus evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_nt = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/risk_adj_search_v1",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline (1.0/0.5/0.5, old curve)':>65} | OOS  84.90 / 84.78 "
        f"| 2/3 folds infeasible | sensitivity unstable +/-16.27pp"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'risk_adj_search_v1 (45/50 narrow dead-zone), curve_sim':>65} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f} | sensitivity stable={result_cs.sensitivity.stable}"
    )
    print(
        f"{'risk_adj_search_v1 (45/50 narrow dead-zone), nautilus':>65} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f} | sensitivity stable={result_nt.sensitivity.stable}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
