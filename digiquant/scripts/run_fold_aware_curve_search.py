#!/usr/bin/env python3
"""Fold-aware curve search: minimax risk-adjusted-return across walk-forward
IS windows, instead of Stage 3's usual full-history risk_adjusted_return.

Motivation (RESEARCH_STATE.md, dead-zone lead closed 2026-09-16): every
candidate tried in this project -- different weight mixes, different
indicator windows, different curve refits -- converges to the same ~50-53%
fold-1 OOS drawdown once Stage 3's curve search is allowed to pick its own
shape freely against the full-history objective. That's flagged as "the
actual binding constraint" and a fold-aware/robust curve-search objective as
the well-motivated, not-yet-tried next step.

This script re-searches the curve shape on the VALIDATED baseline index
(power_law=1.0, m2=0.5, dxy=0.5 -- the only feasible candidate so far), but
scores each trial by min(risk_adjusted_return) across the 3 walk-forward
folds' IN-SAMPLE windows (never OOS -- OOS must stay untouched by search),
instead of by full-history risk_adjusted_return. If a curve exists that's
robust across all three expanding IS windows, it should generalize better to
each fold's held-out OOS than the full-history-optimized shape does.

Winner is then run through the full Stage 4 walk-forward OOS gate.

Diagnostic only. Does not touch RESEARCH_STATE.md or settings.json.

Usage:
    uv run python scripts/run_fold_aware_curve_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    CurveOptimizeGates,
    WIDE_KNEE_COARSE_GRID,
    WIDE_KNEE_SEARCH_BOUNDS,
    load_frozen_index,
    published_curve_shape,
    sample_wide_knee_curve_trials,
    score_shape_on_index,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.walk_forward import make_walk_forward_folds

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

INITIAL_CASH = 1000.0
N_RANDOM = 800  # keep runtime bounded: 4x evaluations per trial (full + 3 fold-IS)


def build_shape(params: dict) -> SdcaCurveShape | None:
    try:
        return SdcaCurveShape(
            buy_max_rate=float(params["buy_max_rate"]),
            buy_knee_risk=float(params["buy_knee_risk"]),
            sell_knee_risk=float(params["sell_knee_risk"]),
            sell_max_rate=float(params["sell_max_rate"]),
            buy_curvature=float(params["buy_curvature"]),
            sell_curvature=float(params["sell_curvature"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=BASELINE_WEIGHTS)
    print(f"Frozen baseline index (validated power_law/m2/dxy mix): {weights.model_dump()}")
    print(f"{dates[0]}..{dates[-1]} ({len(dates)} bars)\n")

    folds, holdout = make_walk_forward_folds(dates.to_list())
    print("Walk-forward IS windows used for the robust curve-search objective (OOS untouched):")
    for f in folds:
        print(f"  fold {f.fold}: IS {f.is_start}..{f.is_end}  (OOS {f.oos_start}..{f.oos_end})")
    print(f"  holdout: {holdout[0]}..{holdout[1]}\n")

    fold_slices = []
    for f in folds:
        mask = (dates >= f.is_start) & (dates <= f.is_end)
        fold_slices.append((dates.filter(mask), prices.filter(mask), risk.filter(mask)))

    gates = CurveOptimizeGates()
    # Fold-IS windows (2018-2019, 2018-2021, 2018-2023) never reach 2025, so the
    # default require_2025_sells gate would reject every trial regardless of
    # shape quality -- disable it only for fold-IS scoring, keep it for the
    # full-history score below (which does reach 2025 in the real data).
    fold_gates = CurveOptimizeGates(require_2025_sells=False)
    trials = sample_wide_knee_curve_trials(
        n_random=N_RANDOM, seed=42, include_grid=True,
        bounds=WIDE_KNEE_SEARCH_BOUNDS, grid=WIDE_KNEE_COARSE_GRID,
    )
    print(f"Evaluating {len(trials)} curve trials x (full-history + {len(folds)} fold-IS windows)...\n")

    full_baseline = score_shape_on_index(dates, prices, risk, published_curve_shape(), INITIAL_CASH, gates=gates)

    best_robust = None
    best_robust_score = float("-inf")
    best_fullhist = None
    best_fullhist_score = float("-inf")
    n_all_feasible = 0

    for params in trials:
        shape = build_shape(params)
        if shape is None:
            continue
        full_score = score_shape_on_index(dates, prices, risk, shape, INITIAL_CASH, gates=gates)
        if full_score.feasible and full_score.risk_adjusted_return > best_fullhist_score:
            best_fullhist_score = full_score.risk_adjusted_return
            best_fullhist = (shape, full_score)

        fold_scores = [
            score_shape_on_index(fd, fp, fr, shape, INITIAL_CASH, gates=fold_gates)
            for fd, fp, fr in fold_slices
        ]
        if all(fs.feasible for fs in fold_scores):
            n_all_feasible += 1
            robust = min(fs.risk_adjusted_return for fs in fold_scores)
            if robust > best_robust_score:
                best_robust_score = robust
                best_robust = (shape, fold_scores, full_score)

    print(f"Trials feasible on ALL 3 fold-IS windows: {n_all_feasible}/{len(trials)}\n")

    print("=== Full-history-optimized winner (Stage 3 as usual) ===")
    if best_fullhist:
        shape, score = best_fullhist
        print(f"  shape: {shape.model_dump()}")
        print(f"  full-history risk_adjusted_return={score.risk_adjusted_return:.4f} "
              f"(return={score.total_return_pct:.2f}%, drawdown={score.max_drawdown_pct:.2f}%)")
    else:
        print("  none feasible")
    print()

    print("=== Fold-robust winner (minimax across 3 IS windows) ===")
    if best_robust:
        shape, fold_scores, full_score = best_robust
        print(f"  shape: {shape.model_dump()}")
        print(f"  full-history risk_adjusted_return={full_score.risk_adjusted_return:.4f} "
              f"(return={full_score.total_return_pct:.2f}%, drawdown={full_score.max_drawdown_pct:.2f}%)")
        for f, fs in zip(folds, fold_scores, strict=True):
            print(f"    fold {f.fold} IS: risk_adjusted_return={fs.risk_adjusted_return:.4f} "
                  f"(return={fs.total_return_pct:.2f}%, drawdown={fs.max_drawdown_pct:.2f}%)")
        print(f"  min fold IS risk_adjusted_return={best_robust_score:.4f}")
    else:
        print("  no trial feasible on all 3 fold-IS windows -- fold-aware search failed to find a candidate")
        return
    print()

    print(f"Published-curve full-history baseline: risk_adjusted_return={full_baseline.risk_adjusted_return:.4f} "
          f"(return={full_baseline.total_return_pct:.2f}%, drawdown={full_baseline.max_drawdown_pct:.2f}%)\n")

    # Stage 4: run the fold-robust winning shape through the real walk-forward OOS gate.
    shape = best_robust[0]
    trial = {
        **SDCA_SHAPE_DEFAULTS,
        "buy_max_rate": shape.buy_max_rate,
        "buy_knee_risk": shape.buy_knee_risk,
        "sell_knee_risk": shape.sell_knee_risk,
        "sell_max_rate": shape.sell_max_rate,
        "buy_curvature": shape.buy_curvature,
        "sell_curvature": shape.sell_curvature,
        "power_law_weight": weights.power_law,
        "m2_weight": weights.m2,
        "dxy_weight": weights.dxy,
    }

    wf_dates, wf_prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    wf_extra_z = load_sdca_extra_z(wf_dates, wf_prices, data_path=None, data_dir=str(cache_dir))

    print("=== Stage 4: fold-robust curve, frozen baseline weights (curve_simulator) ===")
    result_cs = run_sdca_walk_forward(
        wf_dates, wf_prices, [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/fold_aware_curve",
        extra_z=wf_extra_z,
    )
    holdout_cs = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    print(f"  IS={result_cs.mean_is_vs_flat_dca_pct:.2f}  OOS={result_cs.mean_oos_vs_flat_dca_pct:.2f}  "
          f"gap={result_cs.is_oos_gap_pct:.2f}  holdout={holdout_cs:.2f}  beats_oos={result_cs.beats_flat_dca_oos}")
    for fs in result_cs.fold_scores:
        oos = fs.out_of_sample
        print(f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:.2f}%  OOS={oos.vs_flat_dca_pct:.2f}%  "
              f"feasible={fs.feasible}  OOS_drawdown={oos.max_drawdown_pct:.2f}%  "
              f"OOS_capital_deployed={oos.capital_deployed_pct:.2f}%")
    print(f"  sensitivity: stable={result_cs.sensitivity.stable}  "
          f"max_abs_delta_oos={result_cs.sensitivity.max_abs_delta_oos_pct:.2f}pp")
    print()

    print("=== Stage 4: fold-robust curve, frozen baseline weights (nautilus) ===")
    result_nt = run_sdca_walk_forward(
        wf_dates, wf_prices, [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/fold_aware_curve",
        extra_z=wf_extra_z,
    )
    holdout_nt = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(f"  IS={result_nt.mean_is_vs_flat_dca_pct:.2f}  OOS={result_nt.mean_oos_vs_flat_dca_pct:.2f}  "
          f"gap={result_nt.is_oos_gap_pct:.2f}  holdout={holdout_nt:.2f}  beats_oos={result_nt.beats_flat_dca_oos}")
    for fs in result_nt.fold_scores:
        oos = fs.out_of_sample
        print(f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:.2f}%  OOS={oos.vs_flat_dca_pct:.2f}%  "
              f"feasible={fs.feasible}  OOS_drawdown={oos.max_drawdown_pct:.2f}%  "
              f"OOS_capital_deployed={oos.capital_deployed_pct:.2f}%")
    print(f"  sensitivity: stable={result_nt.sensitivity.stable}  "
          f"max_abs_delta_oos={result_nt.sensitivity.max_abs_delta_oos_pct:.2f}pp")
    print()

    print("=== Compare vs RESEARCH_STATE.md current validated baseline (full-history-optimized curve) ===")
    print("  baseline: OOS 84.90 (curve_simulator) / 84.78 (nautilus), fold-1 OOS drawdown ~50-53%, infeasible")
    print(f"  fold-robust curve: OOS {result_cs.mean_oos_vs_flat_dca_pct:.2f} (curve_simulator) / "
          f"{result_nt.mean_oos_vs_flat_dca_pct:.2f} (nautilus)")
    print("\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- report back for "
          "Chris's explicit accept/reject, per the standing gate.")


if __name__ == "__main__":
    run()
