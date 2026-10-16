#!/usr/bin/env python3
"""Stage 4 walk-forward for the power-law-dominant reweight with the
CONSTRAINED Stage 3 curve refit
(``run_power_law_dominant_curve_search_constrained.py``).

Context: the unconstrained fresh curve
(``run_power_law_dominant_curve_search.py``, tested in
``run_power_law_dominant_curve_walk_forward.py``) passed the walk-forward
gate cleanly (beats_oos=True, sensitivity stable +/-0.80pp) but its
full-history tearsheet revealed a real problem -- its buy_knee_risk (20.18,
picked freely by the generic risk_adjusted_return objective) delayed
re-entry at the actual 2022-11 long-term bottom: allocation sat at ~47-56%
for months while the SAME weights under the OLD published curve
(buy_knee_risk=24.1) already sat at 85-90%, missing much of the price
recovery from ~$16,885 to ~$27,000+ before catching up. This directly
violates Chris's explicit, non-negotiable requirement that every long-term
bottom must be caught.

``run_power_law_dominant_curve_search_constrained.py`` re-ran Stage 3 with
buy_knee_risk's search floor raised to 24.0 (the already-validated,
bottom-catching value) -- everything else free. Winner: buy_max_rate=25.0,
buy_knee_risk=24.0, sell_knee_risk=55.0, sell_max_rate=30.0,
buy_curvature=1.5, sell_curvature=1.5 (persist_ok=True). Its full-history
tearsheet (``pld_constrained_curve_full_history.json``) shows a real middle
ground: 0.0-0.2% allocation at both 2021 tops (vs. old curve's 33-94%,
i.e. dramatically more selling, per Chris's "sell more" feedback) while
recovering to 60-76% through the 2022-2023 bottom window (vs. old curve's
85-92%, vs. the unconstrained curve's 47-56% -- much closer to the
validated bottom-catching baseline).

This script checks whether that middle-ground shape holds up OOS.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full IS/OOS table + sensitivity check to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    uv run python scripts/run_power_law_dominant_curve_constrained_walk_forward.py
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
    "m2_weight": 0.15,
    "dxy_weight": 0.15,
}

# Constrained Stage 3 winner (run_power_law_dominant_curve_search_constrained.py),
# buy_knee_risk floor raised to 24.0 to preserve bottom-catching speed.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 25.0,
    "buy_knee_risk": 24.0,
    "sell_knee_risk": 55.0,
    "sell_max_rate": 30.0,
    "buy_curvature": 1.5,
    "sell_curvature": 1.5,
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
    print(f"constrained Stage 3 curve shape: {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/power_law_dominant_curve_constrained",
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
        evaluator_label="nautilus/power_law_dominant_curve_constrained",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline (1.0/0.5/0.5, old curve)':>65} | OOS  84.90 / 84.78 "
        f"| 2/3 folds infeasible | sensitivity unstable +/-16.27pp"
    )
    print(
        f"{'power_law_dominant, OLD curve (isolation test)':>65} | OOS  75.26 / 75.01 "
        f"| fold1 infeasible (COVID) | sensitivity unstable +/-21.44pp"
    )
    print(
        f"{'power_law_dominant, unconstrained fresh curve':>65} | OOS  44.10 / 43.93 "
        f"| fold1 infeasible (COVID) | sensitivity STABLE +/-0.80pp | but undershoots 2022 bottom"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'power_law_dominant, CONSTRAINED curve (curve_sim)':>65} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f}"
    )
    print(
        f"{'power_law_dominant, CONSTRAINED curve (nautilus)':>65} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
