#!/usr/bin/env python3
"""Combine the fast-crash circuit-breaker with a re-tuned curve shape.

Context (see run_crash_override_search.py): the circuit-breaker
(``crash_override.apply_crash_override``), calibrated with the curve shape
frozen at SDCA_SHAPE_DEFAULTS (``sell_max_rate=10.0``,
``sell_knee_risk=80.0``), could not push fold-1 (COVID) OOS drawdown below
~49.2% against a 30% target. Root cause: that curve's sell-rate ceiling caps
deleveraging *speed* once risk saturates, regardless of *when* the override
fires -- the override changes timing, not deleveraging capacity. Chris
approved trying the override combined with a re-tuned curve (higher
``sell_max_rate``, lower ``sell_knee_risk``) as the next step.

Stage 1: ``search_wide_knee_curve`` (existing, curve_optimize.py) against the
frozen validated-baseline index (power_law=1.0, m2=0.5, dxy=0.5, no
override) to find the best risk_adjusted_return curve shape with a much
wider sell-rate ceiling than the published default (WIDE_KNEE_SEARCH_BOUNDS
allows sell_max_rate up to 95 and sell_knee_risk down to 52) -- in-sample,
full history, no override. This is "index then curve": the index itself is
unchanged from the validated baseline, only the curve shape is re-fit.

Stage 2: swap that winning shape's params in for SDCA_SHAPE_DEFAULTS's curve
keys in FROZEN_TRIAL, then re-run the exact same 17-candidate
crash_override_* grid (16 combos + no-override baseline) from
run_crash_override_search.py via real Stage-4 walk-forward on all 3 folds,
under both curve shapes (published-default curve AND the re-tuned curve) so
the two are directly comparable side by side.

Stage 3: rank by meets_target(), confirm top 3 (across both curve shapes)
via both evaluators (curve_simulator + nautilus).

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_retuned_curve_override_search.py
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    load_frozen_index,
    params_from_shape,
    search_wide_knee_curve,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.walk_forward import SdcaOptimizeObjective

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Validated baseline weights -- unchanged from run_crash_override_search.py.
BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)

SEARCH_OBJECTIVE = SdcaOptimizeObjective(capital_deployed_floor_pct=10.0, max_drawdown_cap_pct=30.0)

TRIGGER_Z_GRID = [-1.5, -2.0, -2.5, -3.0]
OVERRIDE_RISK_GRID = [80.0, 90.0, 95.0, 100.0]
RAMP_Z = 1.0

FOLD1_INDEX = 1  # fold.fold == 1 is the COVID OOS window (2019-07-01..2021-11-20)
FOLD1_DD_TARGET_PCT = 30.0
CAPITAL_DEPLOYED_SANE_ABS_PCT = 150.0

TOP_N_FINAL = 3


def find_retuned_curve_shape(cache_dir: Path) -> dict[str, float]:
    """Stage 1: best risk_adjusted_return wide-knee curve on the frozen baseline index."""
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=BASELINE_WEIGHTS)
    result = search_wide_knee_curve(
        dates, prices, risk, initial_cash=1000.0, frozen_weights=weights
    )
    print(
        f"Stage 1 wide-knee curve search: {result.num_evaluations} evaluations, "
        f"{result.num_feasible} feasible"
    )
    b = result.best
    print(
        f"  winner: total_return={b.total_return_pct:.1f}%  max_drawdown={b.max_drawdown_pct:.2f}%  "
        f"risk_adjusted_return={b.risk_adjusted_return:.2f}  feasible={b.feasible}"
    )
    print(f"  shape: {b.shape}")
    print(
        f"  baseline (published curve) risk_adjusted_return={result.baseline.risk_adjusted_return:.2f}  "
        f"beats_baseline_return={result.beats_baseline_return}\n"
    )
    return params_from_shape(b.shape)


def build_candidates() -> list[dict[str, float | bool | str]]:
    """16 crash_override combinations plus a no-override baseline row."""
    candidates: list[dict[str, float | bool | str]] = [
        {"label": "baseline (crash_override_enabled=False)", "crash_override_enabled": False}
    ]
    for trigger_z in TRIGGER_Z_GRID:
        for override_risk in OVERRIDE_RISK_GRID:
            candidates.append(
                {
                    "label": f"trigger_z={trigger_z:.1f} risk={override_risk:.0f} ramp_z={RAMP_Z:.1f}",
                    "crash_override_enabled": True,
                    "crash_override_trigger_z": trigger_z,
                    "crash_override_ramp_z": RAMP_Z,
                    "crash_override_risk": override_risk,
                }
            )
    return candidates


def evaluator_for(candidate: dict, base_evaluator):
    kwargs = {k: v for k, v in candidate.items() if k != "label"}
    return partial(base_evaluator, **kwargs)


def print_fold_table(scores) -> None:
    for s in scores:
        oos = s.out_of_sample
        churn_flag = " <-- SUSPECT CHURN" if abs(oos.capital_deployed_pct) > CAPITAL_DEPLOYED_SANE_ABS_PCT else ""
        print(
            f"    fold {s.fold.fold}: IS={s.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={s.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:7.2f}%{churn_flag}"
        )


def print_wf_row(label: str, result: SdcaWalkForwardResult) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>60} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    print_fold_table(result.fold_scores)
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


def meets_target(result: SdcaWalkForwardResult) -> bool:
    fold1 = next(s for s in result.fold_scores if s.fold.fold == FOLD1_INDEX)
    all_feasible = all(s.feasible for s in result.fold_scores)
    capital_sane = all(
        abs(s.out_of_sample.capital_deployed_pct) <= CAPITAL_DEPLOYED_SANE_ABS_PCT for s in result.fold_scores
    )
    return (
        all_feasible
        and fold1.out_of_sample.max_drawdown_pct <= FOLD1_DD_TARGET_PCT
        and result.beats_flat_dca_oos
        and result.sensitivity.stable
        and capital_sane
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    retuned_shape_params = find_retuned_curve_shape(cache_dir)

    curve_variants: dict[str, dict[str, float]] = {
        "published_curve": {k: SDCA_SHAPE_DEFAULTS[k] for k in retuned_shape_params},
        "retuned_curve": retuned_shape_params,
    }
    for name, params in curve_variants.items():
        print(f"{name}: {params}")
    print()

    candidates = build_candidates()
    print(f"n crash_override candidates per curve variant: {len(candidates)}\n")

    print("=== curve_simulator: full Stage 4 walk-forward per (curve variant, override candidate) ===\n")
    cs_results: list[tuple[str, dict, dict, SdcaWalkForwardResult]] = []
    for curve_name, curve_params in curve_variants.items():
        for c in candidates:
            trial = {
                **SDCA_SHAPE_DEFAULTS,
                **curve_params,
                "power_law_weight": BASELINE_WEIGHTS.power_law,
                "m2_weight": BASELINE_WEIGHTS.m2,
                "dxy_weight": BASELINE_WEIGHTS.dxy,
            }
            evaluator = evaluator_for(c, evaluate_sdca_trial_curve_sim)
            label = f"{curve_name} | {c['label']}"
            result = run_sdca_walk_forward(
                dates,
                prices,
                [trial],
                rails_fitter=btc_power_law_rails_fitter,
                evaluator=evaluator,
                evaluator_label=f"curve_simulator/{label}",
                objective=SEARCH_OBJECTIVE,
                extra_z=extra_z,
            )
            cs_results.append((curve_name, curve_params, c, result))
            print_wf_row(label, result)
            print(f"    meets_target={meets_target(result)}")
            print()

    def rank_key(item: tuple[str, dict, dict, SdcaWalkForwardResult]):
        _, _, _, r = item
        all_feasible = all(s.feasible for s in r.fold_scores)
        return (meets_target(r), all_feasible, r.mean_oos_vs_flat_dca_pct)

    ranked = sorted(cs_results, key=rank_key, reverse=True)

    print("=== Ranking (curve_simulator, meets_target first, then all-feasible, then mean OOS) ===")
    for curve_name, _, c, r in ranked:
        fold1 = next(s for s in r.fold_scores if s.fold.fold == FOLD1_INDEX)
        print(
            f"  meets_target={str(meets_target(r)):5}  mean_OOS={r.mean_oos_vs_flat_dca_pct:7.2f}%  "
            f"fold1_OOS_dd={fold1.out_of_sample.max_drawdown_pct:6.2f}%  "
            f"beats_oos={str(r.beats_flat_dca_oos):5}  sens_stable={str(r.sensitivity.stable):5}  "
            f"{curve_name} | {c['label']}"
        )
    print()

    finalists = ranked[:TOP_N_FINAL]
    print(f"=== Full Stage 4 walk-forward (both evaluators) on top {len(finalists)} finalists ===\n")
    for idx, (curve_name, curve_params, c, _) in enumerate(finalists):
        label = f"{curve_name} | {c['label']}"
        print(f"--- finalist{idx}: {label} ---")
        trial = {
            **SDCA_SHAPE_DEFAULTS,
            **curve_params,
            "power_law_weight": BASELINE_WEIGHTS.power_law,
            "m2_weight": BASELINE_WEIGHTS.m2,
            "dxy_weight": BASELINE_WEIGHTS.dxy,
        }

        evaluator_cs = evaluator_for(c, evaluate_sdca_trial_curve_sim)
        result_cs = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator_cs,
            evaluator_label=f"curve_simulator/finalist{idx}",
            objective=SEARCH_OBJECTIVE,
            extra_z=extra_z,
        )
        print_wf_row(f"curve_simulator finalist{idx}", result_cs)
        print(f"    meets_target={meets_target(result_cs)}")

        evaluator_nt = evaluator_for(c, evaluate_sdca_trial_nautilus)
        result_nt = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator_nt,
            evaluator_label=f"nautilus/finalist{idx}",
            objective=SEARCH_OBJECTIVE,
            extra_z=extra_z,
        )
        print_wf_row(f"nautilus finalist{idx}", result_nt)
        print(f"    meets_target={meets_target(result_nt)}")
        print()

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
