#!/usr/bin/env python3
"""Curve search selected DIRECTLY on Stage-4 walk-forward OOS performance,
not full-history in-sample -- to fix the overfitting found in
run_drawdown_constrained_curve_search.py.

That script filtered the wide-knee trial pool by a HARD full-history
max_drawdown_pct ceiling (20/25/30%) and surfaced spectacular-looking
candidates (e.g. +3458% return / 27.6% dd / beats lump-sum). All three top
candidates FAILED real Stage 4 walk-forward
(run_drawdown_constrained_candidates_walk_forward.py): fold 1 (COVID,
2019-07-01..2021-11-20) stayed infeasible with OOS drawdown 38-43% and
capital_deployed collapsing to -350% to -509% (severe buy/sell churn from
extreme sell_max_rate 68-90), sensitivity was unstable on all three, and the
tightest-drawdown candidate even failed beats_flat_dca_oos outright. Every
fold's IS vs_flat_dca was deeply negative (-53% to -83%) despite spectacular
full-history numbers -- proof these shapes only "work" when averaged over
the full 11-year history and do not generalize to any single fold's shorter
IS window.

This script scores each candidate shape via walk_forward.score_trial_on_folds()
directly (rails refit per fold, real IS/OOS evaluation) with a tightened
SdcaOptimizeObjective(max_drawdown_cap_pct=30.0) instead of the full-history
score_shape_on_index(). This is ~5-8x more expensive per trial than the
full-history score (no shortlist pre-filter, since the full-history metric
was shown above to be anti-correlated with OOS generalization -- prefiltering
on it would just reproduce the same overfit picks), so the trial pool here is
a random subsample of the wide-knee bounds, not the full grid+3000-random
pool.

Selection: prefer trials where ALL folds are feasible under the 30% cap;
among those, maximize mean OOS vs_flat_dca_pct; if none are all-feasible,
fall back to maximizing the feasible-fold count, then minimizing worst-fold
OOS drawdown. The best 1-3 candidates get the full run_sdca_walk_forward()
treatment (both evaluators, sensitivity, holdout) for final reporting.

Diagnostic only, curve_simulator search + both-evaluator final check. Does
not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_oos_native_drawdown_curve_search.py [--pilot]
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_SEARCH_BOUNDS,
    sample_wide_knee_curve_trials,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    make_walk_forward_folds,
    params_are_valid,
    score_trial_on_folds,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Chris's target: OOS drawdown <=30% (ideally <=20-25%), all folds feasible.
SEARCH_OBJECTIVE = SdcaOptimizeObjective(capital_deployed_floor_pct=10.0, max_drawdown_cap_pct=30.0)

N_TRIALS_MAIN = 2500
N_TRIALS_PILOT = 20
TOP_N_FINAL = 3


def build_trials(n: int, *, seed: int = 7) -> list[dict[str, float]]:
    """Random-only subsample of the wide-knee bounds (no grid: keeps the pool
    small enough for per-trial walk-forward scoring)."""
    pool = sample_wide_knee_curve_trials(n_random=n * 2, seed=seed, include_grid=False)
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]


def score_candidate(shape_params, dates, prices, folds, extra_z):
    trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **FROZEN_WEIGHT_PARAMS}
    if not params_are_valid(trial):
        return None
    scores = score_trial_on_folds(
        trial, dates, prices, folds,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        objective=SEARCH_OBJECTIVE,
        extra_z=extra_z,
    )
    all_feasible = all(s.feasible for s in scores)
    feasible_count = sum(s.feasible for s in scores)
    worst_oos_dd = max(s.out_of_sample.max_drawdown_pct for s in scores)
    mean_oos_vs_flat_dca = sum(s.out_of_sample.vs_flat_dca_pct for s in scores) / len(scores)
    return {
        "trial": trial,
        "scores": scores,
        "all_feasible": all_feasible,
        "feasible_count": feasible_count,
        "worst_oos_dd": worst_oos_dd,
        "mean_oos_vs_flat_dca": mean_oos_vs_flat_dca,
    }


def rank_key(result):
    # all_feasible first, then (among all-feasible) highest mean OOS return;
    # otherwise most feasible folds, then lowest worst-fold drawdown.
    return (
        result["all_feasible"],
        result["feasible_count"],
        result["mean_oos_vs_flat_dca"] if result["all_feasible"] else -result["worst_oos_dd"],
    )


def print_fold_table(label, scores):
    for s in scores:
        oos = s.out_of_sample
        print(
            f"    fold {s.fold.fold}: IS={s.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={s.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:6.2f}%"
        )


def print_wf_row(label, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>30} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    print_fold_table(label, result.fold_scores)
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:.2f}%  vs_lump={h.vs_lump_pct:.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.2f}%  max_drawdown={h.max_drawdown_pct:.2f}%"
        )
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR, *, pilot: bool = False) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}")
    print(f"search objective: {SEARCH_OBJECTIVE.model_dump()}")
    for f in folds:
        print(f"  fold {f.fold}: IS {f.is_start}..{f.is_end}  OOS {f.oos_start}..{f.oos_end}")
    print()

    n_trials = N_TRIALS_PILOT if pilot else N_TRIALS_MAIN
    trials = build_trials(n_trials)
    print(f"n candidate shapes (wide-knee bounds, random-only, walk-forward-native scoring): {len(trials)}\n")

    t0 = time.monotonic()
    results = []
    for i, shape_params in enumerate(trials):
        r = score_candidate(shape_params, dates, prices, folds, extra_z)
        if r is not None:
            results.append(r)
        if pilot or (i + 1) % 100 == 0:
            elapsed = time.monotonic() - t0
            print(f"  ... {i + 1}/{len(trials)} scored ({elapsed:.1f}s elapsed, {elapsed / (i + 1):.3f}s/trial)")
    elapsed = time.monotonic() - t0
    print(f"\nscored {len(results)} valid candidates in {elapsed:.1f}s ({elapsed / max(1, len(trials)):.3f}s/trial)\n")

    if pilot:
        print("Pilot run only -- exiting before ranking/full validation.")
        return

    all_feasible_results = [r for r in results if r["all_feasible"]]
    print(f"all-3-folds-feasible under {SEARCH_OBJECTIVE.max_drawdown_cap_pct:.0f}% cap: {len(all_feasible_results)} / {len(results)}\n")

    results.sort(key=rank_key, reverse=True)

    print("=== Top 10 candidates by walk-forward-native ranking ===")
    for r in results[:10]:
        sh = r["trial"]
        print(
            f"  all_feasible={str(r['all_feasible']):>5}  feasible_folds={r['feasible_count']}/3  "
            f"worst_OOS_dd={r['worst_oos_dd']:6.2f}%  mean_OOS_vs_flat_dca={r['mean_oos_vs_flat_dca']:7.2f}%  "
            f"knees=({sh['buy_knee_risk']:.1f}/{sh['sell_knee_risk']:.1f})  "
            f"rates=({sh['buy_max_rate']:.1f}/{sh['sell_max_rate']:.1f})  "
            f"curv=({sh['buy_curvature']:.2f}/{sh['sell_curvature']:.2f})"
        )
    print()

    finalists = results[:TOP_N_FINAL]
    print(f"=== Full Stage 4 walk-forward (both evaluators) on top {len(finalists)} finalists ===\n")
    for idx, r in enumerate(finalists):
        shape_params = {k: r["trial"][k] for k in ("buy_max_rate", "buy_knee_risk", "sell_knee_risk", "sell_max_rate", "buy_curvature", "sell_curvature")}
        label = f"finalist{idx}"
        print(f"--- {label}: {shape_params} ---")

        result_cs = run_sdca_walk_forward(
            dates, prices, [r["trial"]],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_curve_sim,
            evaluator_label=f"curve_simulator/{label}",
            objective=SEARCH_OBJECTIVE,
            extra_z=extra_z,
        )
        print_wf_row(f"curve_simulator {label}", result_cs)

        result_nt = run_sdca_walk_forward(
            dates, prices, [r["trial"]],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluate_sdca_trial_nautilus,
            evaluator_label=f"nautilus/{label}",
            objective=SEARCH_OBJECTIVE,
            extra_z=extra_z,
        )
        print_wf_row(f"nautilus {label}", result_nt)
        print()

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run(pilot="--pilot" in sys.argv)
