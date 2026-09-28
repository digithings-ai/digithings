#!/usr/bin/env python3
"""Task 8 (2026-09-25-sdca-index-smoothing-tiered-curve-plan): periodic
self-optimization cycle driver.

Alternates between indicator-pool ablation and tiered-curve search, gates
each candidate against flat DCA *and* the currently-published live config
(`published_indicator_weights()` + `published_curve_shape()` read from the
actual current `settings.json` -- never the stale validated-candidate
section), and logs findings. State persists in
`.scratch/periodic_cycle_state.json` (untracked) so successive invocations
alternate cycle types and remember the ablation pool + best-seen candidate.

GATE (RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes `settings.json` or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. A gate-clearing candidate is
reported on stdout for Chris's explicit accept; only his accept promotes.

Ablation cycles explore weights while holding the curve at the live shape;
curve cycles explore the tiered shape while holding weights at live (or
best-seen, once one exists). Data plumbing (`reweight.load_inputs()`) is
identical to Task 7's driver, so the frozen index matches Task 7 exactly.
The ablation round callbacks are reused unchanged from
`run_iterative_ablation` (cross-script import -- same convention Task 7's
driver uses for `run_aggregate_reweight_full17_fixed_index`).

Usage:
    uv run python scripts/run_periodic_self_optimization_cycle.py
"""

from __future__ import annotations

import functools
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl

# Reused, unchanged, from the existing drivers -- not copied.
# Cross-script import works because ``uv run python scripts/<this file>.py``
# puts ``scripts/`` (this file's own directory) at sys.path[0], and all
# three files live there.
import run_aggregate_reweight_full17_fixed_index as reweight
import run_iterative_ablation as ablation_driver

from digiquant.strategies.sdca.ablation import run_ablation_rounds
from digiquant.strategies.sdca.baseline_evaluator import (
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.curve_optimize import (
    _MID_TIER_KEYS,
    WIDE_KNEE_TIERED_COARSE_GRID,
    WIDE_KNEE_TIERED_SEARCH_BOUNDS,
    published_curve_shape,
    published_indicator_weights,
)
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    search_wide_knee_curve_feasibility_aware,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.periodic_cycle_state import (
    CycleState,
    load_cycle_state,
    save_cycle_state,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
STATE_PATH = DIGIQUANT_ROOT / ".scratch" / "periodic_cycle_state.json"
RESEARCH_STATE_PATH = (
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "RESEARCH_STATE.md"
)

FULL_INITIAL_CASH = 10_000.0

# Same plain-default oscillator spec Task 7's gate uses (matches
# load_inputs()'s implicit default; deliberately not a bespoke Stage 1 set).
GATE_OSCILLATORS = SdcaOscillatorSpec()


def params_for(weights: SdcaCompositeWeights, shape) -> dict:
    """Trial params: frozen weight params + curve-shape fields (Task 7's exact construction).

    Unset (None) mid-tier fields are dropped, not passed through:
    ``SdcaWalkForwardResult.best_params`` is a strict
    ``dict[str, bool | float | int | str]`` that rejects None. Set mid-tier
    fields pass through intact, and the walk-forward ``shape_from_params``
    path now reads them (cycle-1 finding F1), so a tiered-curve winner gates
    on its actual searched shape -- a single-knee live shape still gates
    identically with or without its None mid-tier keys present.
    """
    trial: dict[str, float | int | str] = dict(freeze_weight_params(weights))
    for key, value in shape.model_dump().items():
        if value is not None:
            trial[key] = value
    return trial


def fold_passes(fs) -> bool:
    """One fold clears the parity bar iff feasible with a real OOS edge over flat DCA."""
    return bool(fs.feasible and fs.out_of_sample.vs_flat_dca_pct > 0)


def main() -> None:
    state = load_cycle_state(STATE_PATH)
    cycle_type = state.next_cycle_type
    print(f"periodic self-optimization cycle {state.cycle_count + 1} (type={cycle_type})")
    print(
        f"  ablation pool remaining (N={len(state.ablation_pool_remaining)}): {list(state.ablation_pool_remaining)}"
    )

    # -- Step 2: live-config baseline (actual current settings.json) --
    live_weights = published_indicator_weights()
    live_shape = published_curve_shape()
    live_params = params_for(live_weights, live_shape)
    print(f"  live weights: {live_weights.model_dump()}")
    print(f"  live curve shape: {live_shape.model_dump()}")

    # -- Data (identical frozen index to Task 7) --
    dates, power_law_z, extra_z, long_windows, medium_windows = reweight.load_inputs()
    _dates2, prices = load_sdca_ohlcv(
        symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None
    )
    assert _dates2 == dates, "load_sdca_ohlcv returned different dates on the second call"
    print(f"  BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")

    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=GATE_OSCILLATORS)

    candidate_weights: SdcaCompositeWeights
    cycle_notes: dict = {"cycle_type": cycle_type}

    if cycle_type == "ablation":
        # -- Step 3 (ablation half): exactly one bounded ablation round --
        data = SimpleNamespace(
            dates=dates,
            prices=prices,
            date_s=pl.Series("date", dates, dtype=pl.Date),
            price_s=pl.Series("price", prices, dtype=pl.Float64),
            power_law_z=power_law_z,
            extra_z=extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
        )
        ablation_result = run_ablation_rounds(
            tuple(state.ablation_pool_remaining),
            reweight_fn=ablation_driver.make_reweight_fn(data),
            gate_fn=ablation_driver.make_gate_fn(data),
            max_rounds=1,
        )
        best_round = ablation_result.best_round
        candidate_weights = best_round.weights
        # Ablation explores weights; the curve is held at the live shape.
        candidate_shape = live_shape
        remaining = tuple(n for n in best_round.pool if n != best_round.dominant_indicator)
        print(
            f"  ablation round: pool={list(best_round.pool)} "
            f"dominant={best_round.dominant_indicator} (weight={best_round.dominant_weight:.3f}) "
            f"oos_duration={best_round.mean_oos_vs_flat_dca_pct_duration_weighted:+.2f}% "
            f"stop={ablation_result.stop_reason}"
        )
        cycle_notes["ablation"] = {
            "pool_before": list(best_round.pool),
            "dominant_indicator": best_round.dominant_indicator,
            "dominant_weight": best_round.dominant_weight,
            "pool_after": list(remaining),
            "stop_reason": ablation_result.stop_reason,
        }
    else:
        # -- Step 4 (curve half): tiered feasibility-aware search --
        # Weights held at best-seen (if one cleared the gate before) else live.
        if state.best_seen is not None:
            candidate_weights = SdcaCompositeWeights(**state.best_seen["weights"])
            print("  curve cycle weights: best_seen (prior gate-clearing candidate)")
        else:
            candidate_weights = live_weights
            print("  curve cycle weights: live config (no best_seen yet)")
        risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, candidate_weights)
        risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)
        curve_result = search_wide_knee_curve_feasibility_aware(
            pl.Series("date", dates, dtype=pl.Date),
            pl.Series("price", prices, dtype=pl.Float64),
            risk_s,
            initial_cash=FULL_INITIAL_CASH,
            bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
            grid=WIDE_KNEE_TIERED_COARSE_GRID,
            extra_keys=_MID_TIER_KEYS,
        )
        candidate_shape = curve_result.best.shape
        print(
            f"  curve search: num_evaluations={curve_result.num_evaluations} "
            f"feasibility_adjusted_score={curve_result.best.feasibility_adjusted_score:.4f} "
            f"shape={candidate_shape.model_dump()}"
        )
        cycle_notes["curve_search"] = {
            "num_evaluations": curve_result.num_evaluations,
            "feasibility_adjusted_score": curve_result.best.feasibility_adjusted_score,
            "notes": curve_result.notes,
        }
        remaining = tuple(state.ablation_pool_remaining)

    candidate_params = params_for(candidate_weights, candidate_shape)

    # -- Step 5: gate vs flat DCA (+ risk50-linear) and vs the live config --
    comparison = run_sdca_walk_forward_vs_baseline(
        dates,
        prices,
        candidate_params,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    candidate_result = comparison.candidate
    live_result = run_sdca_walk_forward(
        dates,
        prices,
        [live_params],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    cand_oos = candidate_result.mean_oos_vs_flat_dca_pct_duration_weighted
    live_oos = live_result.mean_oos_vs_flat_dca_pct_duration_weighted
    beats_live = bool(cand_oos > live_oos)

    per_fold = [
        {
            "fold": fs.fold.fold,
            "oos_vs_flat_dca_pct": fs.out_of_sample.vs_flat_dca_pct,
            "max_drawdown_pct": fs.out_of_sample.max_drawdown_pct,
            "feasible": fs.feasible,
            "passes": fold_passes(fs),
        }
        for fs in candidate_result.fold_scores
    ]
    all_folds_pass = bool(per_fold) and all(f["passes"] for f in per_fold)
    print("  per-fold vs flat DCA:")
    for f in per_fold:
        print(
            f"    fold {f['fold']}: oos_vs_flat_dca={f['oos_vs_flat_dca_pct']:+.2f}% "
            f"max_dd={f['max_drawdown_pct']:.2f}% feasible={f['feasible']} passes={f['passes']}"
        )
    print(
        f"  candidate duration-weighted OOS={cand_oos:+.2f}% "
        f"beats_flat_dca_oos={candidate_result.beats_flat_dca_oos} "
        f"sensitivity_stable={candidate_result.sensitivity.stable} "
        f"(max_abs_delta={candidate_result.sensitivity.max_abs_delta_oos_pct:.2f})"
    )
    print(
        f"  live config duration-weighted OOS={live_oos:+.2f}% "
        f"beats_live_oos={beats_live} "
        f"beats_risk50_linear={comparison.beats_baseline_oos} "
        f"(delta={comparison.delta_mean_oos_vs_flat_dca_pct:+.2f}%)"
    )

    full_gate = bool(
        candidate_result.beats_flat_dca_oos
        and all_folds_pass
        and candidate_result.sensitivity.stable
        and beats_live
    )

    # -- Step 6: persist state (flip type, bump count, maybe new best_seen) --
    new_count = state.cycle_count + 1
    next_type = "curve" if cycle_type == "ablation" else "ablation"
    best_seen = state.best_seen
    if full_gate:
        prev_oos = (
            float(state.best_seen["duration_weighted_oos_pct"])
            if state.best_seen is not None
            else float("-inf")
        )
        if cand_oos > prev_oos:
            best_seen = {
                "cycle": new_count,
                "cycle_type": cycle_type,
                "weights": candidate_weights.model_dump(),
                "curve_shape": candidate_shape.model_dump(),
                "duration_weighted_oos_pct": cand_oos,
                "beats_flat_dca_oos": True,
            }
            print("  best_seen updated.")
    save_cycle_state(
        STATE_PATH,
        CycleState(
            cycle_count=new_count,
            next_cycle_type=next_type,
            ablation_pool_remaining=remaining,
            best_seen=best_seen,
        ),
    )

    # -- Step 7: full result detail (untracked) --
    out = {
        "cycle": new_count,
        "cycle_type": cycle_type,
        "candidate_weights": candidate_weights.model_dump(),
        "candidate_curve_shape": candidate_shape.model_dump(),
        "live_weights": live_weights.model_dump(),
        "live_curve_shape": live_shape.model_dump(),
        "cycle_notes": cycle_notes,
        "walk_forward_vs_baseline": comparison.model_dump(),
        "live_walk_forward": live_result.model_dump(),
        "per_fold": per_fold,
        "all_folds_pass": all_folds_pass,
        "beats_live_oos": beats_live,
        "full_parity_gate": full_gate,
    }
    result_path = DIGIQUANT_ROOT / ".scratch" / f"periodic_cycle_{new_count}.json"
    result_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"  wrote {result_path}")

    # -- Step 8: append one dated line to Immediate backlog (never lines 13-21) --
    today = datetime.now(timezone.utc).date().isoformat()
    entry = (
        f"- **{today} — periodic cycle {new_count} ({cycle_type})**: "
        f"candidate duration-weighted OOS={cand_oos:+.2f}% vs live {live_oos:+.2f}% "
        f"(beats_live_oos={beats_live}), beats_flat_dca_oos={candidate_result.beats_flat_dca_oos}, "
        f"per-fold pass={[f['fold'] for f in per_fold if f['passes']]}/{[f['fold'] for f in per_fold]}, "
        f"sensitivity_stable={candidate_result.sensitivity.stable}, "
        f"full_parity_gate={full_gate} "
        f"(detail: `.scratch/periodic_cycle_{new_count}.json`).\n"
    )
    text = RESEARCH_STATE_PATH.read_text()
    marker = "## North-star ceiling"
    if "Periodic self-optimization cycle log" not in text:
        log_block = (
            "11. **Periodic self-optimization cycle log** (Task 8 driver, "
            "`scripts/run_periodic_self_optimization_cycle.py` — alternating "
            "ablation / tiered-curve cycles gated vs flat DCA and the live "
            "`settings.json` config; diagnostic only, never writes "
            "`settings.json` or the validated-candidate section):\n" + entry
        )
        text = text.replace(marker, log_block + "\n" + marker, 1)
    else:
        # Append after the last existing dated cycle line in this block.
        insert_at = text.index(marker)
        text = text[:insert_at].rstrip("\n") + "\n" + entry + "\n" + text[insert_at:]
    RESEARCH_STATE_PATH.write_text(text)
    print("  appended cycle line to RESEARCH_STATE.md Immediate backlog.")

    # -- Step 9: one-line gate summary (the standing loop relays this) --
    if full_gate:
        print("CANDIDATE CLEARS FULL PARITY GATE — needs Chris's explicit accept")
    else:
        failures = []
        if not candidate_result.beats_flat_dca_oos:
            failures.append("aggregate beats_flat_dca_oos=False")
        failed_folds = [f["fold"] for f in per_fold if not f["passes"]]
        if failed_folds:
            failures.append(f"folds failing parity bar={failed_folds}")
        if not candidate_result.sensitivity.stable:
            failures.append(
                "sensitivity unstable "
                f"(max_abs_delta={candidate_result.sensitivity.max_abs_delta_oos_pct:.2f})"
            )
        if not beats_live:
            failures.append(f"loses to live config ({cand_oos:+.2f}% vs {live_oos:+.2f}%)")
        print(f"gate not cleared: {'; '.join(failures) if failures else 'unknown'}")


if __name__ == "__main__":
    main()
