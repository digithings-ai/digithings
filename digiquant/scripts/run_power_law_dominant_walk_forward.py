#!/usr/bin/env python3
"""OOS walk-forward gate for the power-law-dominant reweight of the validated
3-indicator baseline (power_law/m2/dxy).

Chris's feedback (2026-09-13): the strategy doesn't sell enough at tops and
stays overexposed through the decline, so it fails to re-enter aggressively
at the 2022 long-term bottom. Long-term bottoms are a hard requirement;
medium-term bottoms are optional; allocation should swing across nearly the
full 0-100% range between every major bottom and top.

Diagnosis (``.scratch/tearsheets/validated_baseline_2026.json``, the accepted
baseline with power_law=1.0/m2=0.5/dxy=0.5): at 2022-11-21 (the actual cycle
low, BTC ~$15,787), power_law's own composite-risk reading is 8.8 (strongly
"cheap"/buy), but m2 reads 72.5 ("expensive") -- not because m2 is buggy or
miscalibrated (its z-score is genuinely correct: US M2 YoY growth really was
decelerating into a historic tightening cycle at that time, confirmed at
every rolling-window length from 90 to 1460 days) but because a simple
linear weighted average lets that macro-liquidity read dilute power_law's
extreme, price-based valuation signal at the exact moment it matters most.
At 0.5 weight, m2 (and dxy) pull the composite to 32.3 -- just above the
published curve's buy_knee_risk=24.1 -- so no strong re-entry signal ever
fires at the true bottom. The same dilution works in reverse at tops: at the
2021-11 ATH, power_law and m2 already agree (-2.04 / -2.14 z, both "sell"),
so downweighting m2 costs little there.

This isolates the fix to weights alone: same published ``btc_optimized``
curve shape, only power_law/m2/dxy weights changed (1.0/0.5/0.5 ->
1.0/0.15/0.15). Single-history sanity check
(``m2dxy_downweight_test.json``, --preset btc_optimized) already showed the
qualitative fix working: allocation now swings 33-99% at the 2021 top
(vs. 93-99% before) and recovers to 85% at the 2022 bottom (vs. 71.7%
before), vs_flat_dca_pct 185.5% -> 959.9%, vs_lump_pct -31.0% -> +192.9%.
This script checks whether that holds out-of-sample.

Deliberately reuses the OLD curve shape against a CHANGED index -- this
violates AGENTS.md's "index-then-curve" rule for a final candidate, but is
intentional here as an isolation test (same pattern as
``run_onchain_risk_floor_diagnostic.py``): confirm the weight change alone
is responsible for the improvement before spending a fresh Stage 3 curve
search on it. See ``run_power_law_dominant_curve_search.py`` for the
proper re-fit.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full IS/OOS table + sensitivity check to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    uv run python scripts/run_power_law_dominant_walk_forward.py
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

# Power-law-dominant reweight: same 3 indicators as the validated baseline,
# m2/dxy pulled down from 0.5 to 0.15 so they still contribute (well above
# Phase B's 0.1 floor) without diluting power_law's extreme readings.
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.15,
    "dxy_weight": 0.15,
}

# Published btc_optimized curve shape (presets.json), unchanged -- isolation
# test for the weight change alone.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 35.5,
    "buy_knee_risk": 24.1,
    "sell_knee_risk": 71.9,
    "sell_max_rate": 21.0,
    "buy_curvature": 1.3,
    "sell_curvature": 4.0,
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
    print(f"frozen curve shape (published btc_optimized, unchanged): {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/power_law_dominant",
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
        evaluator_label="nautilus/power_law_dominant",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline (1.0/0.5/0.5)':>50} | OOS  84.90 (curve_simulator) / 84.78 (nautilus) "
        f"| holdout n/a here (power_law/m2/dxy only, see RESEARCH_STATE.md)"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'power_law_dominant (1.0/0.15/0.15, curve_sim)':>50} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f}"
    )
    print(
        f"{'power_law_dominant (1.0/0.15/0.15, nautilus)':>50} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
