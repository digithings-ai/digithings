#!/usr/bin/env python3
"""Calibrate the fast-crash circuit-breaker (crash_override.py) via real
Stage 4 walk-forward -- not a proxy.

Background: every curve-shape-only search tried against the validated
3-weight composite baseline (power_law=1.0, m2=0.5, dxy=0.5) tops out around
33.5% fold-1 (COVID, 2019-07-01..2021-11-20) OOS drawdown -- still above the
20-30% target -- because that composite is built from slow/macro indicators
and reacts too slowly to a fast crash. ``indicator_catalog.fast_crash_vol_z``
(short-window realized-vol z-score, sign-flipped so a vol spike reads very
negative) was tried as one more *weighted* composite indicator and rejected:
it passes solo period-search validation but the aggregate-reweight admission
gate pins it at the 0.1 floor every time, because that gate's objective
(long+medium macro-cycle-turning-point overlap) never scores drawdown and
structurally cannot reward a fast mean-reverting signal.

The approved fix instead makes ``fast_crash_vol_z`` an INDEPENDENT
OVERRIDE/CIRCUIT-BREAKER (``crash_override.apply_crash_override``) that sits
outside the weighted composite entirely, forcing risk UP (more
sell-favorable) during a fast-crash vol spike regardless of what the slow
composite says. It can only raise risk, never lower it, so it never fights
the buy side. This script calibrates its two free knobs
(``crash_override_trigger_z``, ``crash_override_risk``; ``crash_override_ramp_z``
held fixed at 1.0 for this pass) by holding weights AND curve-shape at the
validated baseline defaults (unmodified) and grid-searching ONLY the
crash_override_* params, to isolate the override's own effect cleanly from
any curve/weight re-tuning.

Both ``evaluate_sdca_trial_curve_sim`` and ``evaluate_sdca_trial_nautilus``
accept ``crash_override_*`` as keyword-only extras outside the
``SdcaTrialEvaluator`` Protocol signature (like ``composite_rolling_window``
before it) -- ``score_trial_on_folds`` calls the evaluator positionally, so
these are bound via ``functools.partial`` before the evaluator is handed to
``run_sdca_walk_forward``, the same pattern
``run_rolling_composite_window_test.py`` uses for its rolling-window knob.

Selection: prefer candidates where ALL 3 folds are feasible under a 30%
drawdown cap AND fold-1 OOS max_drawdown_pct <= 30% (ideally <=25%) AND
beats_flat_dca_oos AND sensitivity.stable AND OOS capital_deployed_pct stays
within a sane +/-150% range on every fold (no churn blowup); among those,
maximize mean OOS vs_flat_dca_pct. The winner (and closest 1-2 runners-up)
get the full run_sdca_walk_forward() treatment on BOTH evaluators for final
confirmation.

Diagnostic only, curve_simulator search + both-evaluator final check. Does
not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_crash_override_search.py
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
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

# Validated baseline: weights AND curve-shape held fixed, unmodified, for
# this whole search -- only crash_override_* varies below.
FROZEN_TRIAL: dict[str, float | bool] = {
    **SDCA_SHAPE_DEFAULTS,
    "power_law_weight": 1.0,
    "m2_weight": 0.5,
    "dxy_weight": 0.5,
}

# Same cap Chris set for the curve-shape searches this session (fold-1 OOS
# drawdown target 20-30%).
SEARCH_OBJECTIVE = SdcaOptimizeObjective(capital_deployed_floor_pct=10.0, max_drawdown_cap_pct=30.0)

TRIGGER_Z_GRID = [-1.5, -2.0, -2.5, -3.0]
OVERRIDE_RISK_GRID = [80.0, 90.0, 95.0, 100.0]
RAMP_Z = 1.0

FOLD1_INDEX = 1  # fold.fold == 1 is the COVID OOS window (2019-07-01..2021-11-20)
FOLD1_DD_TARGET_PCT = 30.0
CAPITAL_DEPLOYED_SANE_ABS_PCT = 150.0  # outside this on any OOS fold is suspect churn

TOP_N_FINAL = 3


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
    """Bind this candidate's crash_override_* kwargs onto the evaluator via
    functools.partial -- they are outside the SdcaTrialEvaluator Protocol
    signature, so score_trial_on_folds can't forward them from the trial
    dict (see curve_sim.py / nautilus_evaluator.py docstrings)."""
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
        f"{label:>50} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
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

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(
        "frozen weights+curve-shape (validated baseline, unmodified): "
        f"power_law={FROZEN_TRIAL['power_law_weight']} m2={FROZEN_TRIAL['m2_weight']} dxy={FROZEN_TRIAL['dxy_weight']} "
        f"curve=(buy_max_rate={FROZEN_TRIAL['buy_max_rate']}, buy_knee_risk={FROZEN_TRIAL['buy_knee_risk']}, "
        f"sell_knee_risk={FROZEN_TRIAL['sell_knee_risk']}, sell_max_rate={FROZEN_TRIAL['sell_max_rate']}, "
        f"buy_curvature={FROZEN_TRIAL['buy_curvature']}, sell_curvature={FROZEN_TRIAL['sell_curvature']})"
    )
    print(f"search objective: {SEARCH_OBJECTIVE.model_dump()}")
    print(f"fold-1 OOS drawdown target: <= {FOLD1_DD_TARGET_PCT:.1f}% (ideally <= 25%)\n")

    candidates = build_candidates()
    print(f"n candidates (16 crash_override_* combos + no-override baseline): {len(candidates)}\n")

    print("=== curve_simulator: full Stage 4 walk-forward per candidate ===\n")
    cs_results: list[tuple[dict, SdcaWalkForwardResult]] = []
    for c in candidates:
        evaluator = evaluator_for(c, evaluate_sdca_trial_curve_sim)
        result = run_sdca_walk_forward(
            dates,
            prices,
            [FROZEN_TRIAL],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label=f"curve_simulator/{c['label']}",
            objective=SEARCH_OBJECTIVE,
            extra_z=extra_z,
        )
        cs_results.append((c, result))
        print_wf_row(str(c["label"]), result)
        print(f"    meets_target={meets_target(result)}")
        print()

    def rank_key(item: tuple[dict, SdcaWalkForwardResult]):
        _, r = item
        all_feasible = all(s.feasible for s in r.fold_scores)
        return (meets_target(r), all_feasible, r.mean_oos_vs_flat_dca_pct)

    ranked = sorted(cs_results, key=rank_key, reverse=True)

    print("=== Ranking (curve_simulator, meets_target first, then all-feasible, then mean OOS) ===")
    for c, r in ranked:
        fold1 = next(s for s in r.fold_scores if s.fold.fold == FOLD1_INDEX)
        print(
            f"  meets_target={str(meets_target(r)):5}  mean_OOS={r.mean_oos_vs_flat_dca_pct:7.2f}%  "
            f"fold1_OOS_dd={fold1.out_of_sample.max_drawdown_pct:6.2f}%  "
            f"beats_oos={str(r.beats_flat_dca_oos):5}  sens_stable={str(r.sensitivity.stable):5}  {c['label']}"
        )
    print()

    finalists = ranked[:TOP_N_FINAL]
    print(f"=== Full Stage 4 walk-forward (both evaluators) on top {len(finalists)} finalists ===\n")
    for idx, (c, _) in enumerate(finalists):
        label = str(c["label"])
        print(f"--- finalist{idx}: {label} ---")

        evaluator_cs = evaluator_for(c, evaluate_sdca_trial_curve_sim)
        result_cs = run_sdca_walk_forward(
            dates,
            prices,
            [FROZEN_TRIAL],
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
            [FROZEN_TRIAL],
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
