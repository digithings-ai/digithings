#!/usr/bin/env python3
"""Stage 4 of the Phase B indicator-addition playbook: OOS walk-forward gate
for the power-law-dominant reweight WITH its freshly-fit Stage 3 curve
(``run_power_law_dominant_curve_search.py``), properly following the
"index-then-curve" rule this time.

Context: ``run_power_law_dominant_walk_forward.py`` isolation-tested the
weight change alone (power_law=1.0/m2=0.5/dxy=0.5 -> 1.0/0.15/0.15) against
the OLD published curve shape and found a mixed OOS result -- headline pass
(OOS 75.26%) but unstable sensitivity (+/-21.44pp) and a persistent fold-1
infeasibility (53.06% drawdown) that turned out (see that script's
docstring / the accompanying investigation) to be driven specifically by
the March 2020 COVID flash-crash, not a cyclical-topping failure -- an
irreducible risk for this indicator set that no curve shape can fix (no
valuation signal read BTC as "expensive" beforehand).

``run_power_law_dominant_curve_search.py`` then ran a proper fresh Stage 3
search on this reweighted index and found a shape that clears the
codebase's own gate (``persist_ok=True``, beats baseline on
risk_adjusted_return: 116.69 vs. 81.47) with much more aggressive selling
(sell_max_rate 66.9 vs. the old shape's 21.0) and a lower sell_knee_risk
(65.58 vs. 71.9) -- directly the "sell more at tops" behavior Chris asked
for -- at the cost of some upside (in-sample total_return_pct 3237% vs.
5009%, but max_drawdown cut nearly in half: 27.74% vs. 61.49%).

This script re-runs Stage 4 with weights + this new curve shape together,
to see whether the drawdown improvement holds OOS and whether it fixes
fold 0/fold 2 (fold 1 is not expected to improve, per the COVID diagnosis
above).

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full IS/OOS table + sensitivity check to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    uv run python scripts/run_power_law_dominant_curve_walk_forward.py
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

# Power-law-dominant reweight (unchanged from run_power_law_dominant_walk_forward.py).
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.15,
    "dxy_weight": 0.15,
}

# Fresh Stage 3 winner (run_power_law_dominant_curve_search.py), fit against
# THIS reweighted index -- not the old published shape.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 39.6206,
    "buy_knee_risk": 20.1806,
    "sell_knee_risk": 65.5787,
    "sell_max_rate": 66.8997,
    "buy_curvature": 1.5735,
    "sell_curvature": 1.0002,
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
    print(f"fresh Stage 3 curve shape (run_power_law_dominant_curve_search.py winner): {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/power_law_dominant_curve",
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
        evaluator_label="nautilus/power_law_dominant_curve",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline (1.0/0.5/0.5, old curve)':>60} | OOS  84.90 (curve_simulator) / 84.78 (nautilus)"
    )
    print(
        f"{'power_law_dominant, OLD curve (isolation test)':>60} | OOS  75.26 (curve_simulator) / 75.01 (nautilus) "
        f"| sensitivity unstable +/-21.44pp | fold1 infeasible (COVID-driven, irreducible)"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'power_law_dominant, FRESH curve (curve_sim)':>60} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f}"
    )
    print(
        f"{'power_law_dominant, FRESH curve (nautilus)':>60} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
