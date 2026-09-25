#!/usr/bin/env python3
"""Task 7 (2026-09-25-sdca-index-smoothing-tiered-curve-plan): joint 17-
indicator reweight + tiered, feasibility-aware curve search, gated by a
single walk-forward OOS run on the overall winner.

Why this script is structured as "reweight search -> small candidate set ->
curve search per candidate -> pick the best (weights, curve) pair -> one
walk-forward gate" rather than "curve search nested inside the reweight
search's per-combination loop":

``run_aggregate_reweight_full17_fixed_index.main()`` does NOT loop over
individual weight candidates one at a time. Its coarse pass
(``run_parallel_scan``) is an exhaustive multiprocessing scan over up to
2**17 = 131,072 combinations (16-name search pool x 2-point coarse grid,
since N=17 > 12 triggers the 2-point ``COARSE_GRID``), scored via a cheap
cycle-overlap objective with no backtest and no price data touched at all.
Its refine pass can re-score up to 2,000,000 more combinations the same
cheap way. Calling an expensive curve search (which runs a real backtest
simulation per trial) inside either of those loops is not feasible -- it
would multiply an already-large combinatorial search by thousands of
backtest evaluations each.

Instead, this script reuses ``run_aggregate_reweight_full17_fixed_index``'s
``load_inputs``/``run_parallel_scan``/``best_for_ratio``/``full_score``/
``refined_window``/``chunked`` UNCHANGED (imported, not copied) to reproduce
its exact coarse pass, refine pass, and ratio-sensitivity pass -- which
naturally produce a SMALL set of final weight candidates, not thousands:

1. The refined primary-ratio (3:1) winner (that script's main output).
2. The three ratio-sensitivity coarse winners, one each for ratios
   (2.0, 1.0), (3.0, 1.0), (5.0, 1.0) -- picked from the already-computed
   coarse-pass ``results`` via ``best_for_ratio``, no new evaluation needed,
   but note they come from the COARSE grid only, not the refined one.

That is up to 4 distinct ``SdcaCompositeWeights`` candidates (fewer once
duplicates -- e.g. the 3:1 coarse winner colliding with some other ratio's
coarse winner -- are deduplicated). For EACH surviving candidate, this
script freezes its composite-risk index via ``risk_from_weighted_z`` and
runs Task 6's ``search_wide_knee_curve_feasibility_aware`` (tiered search
space: ``bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS``,
``grid=WIDE_KNEE_TIERED_COARSE_GRID``, ``extra_keys=_MID_TIER_KEYS``)
against that candidate's frozen index. The overall (weights, curve) winner
is the candidate whose curve search achieved the best
``feasibility_adjusted_score`` -- making the reported result jointly optimal
over the small candidate set the reweight search actually produces, without
requiring a computationally infeasible curve-search-inside-131,072-combo-scan.

The single overall winner is then run once through ``run_sdca_walk_forward``
(``fold_weighting="duration"``, real backtest simulation) as the OOS gate.

GATE (RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes ``settings.json`` or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_full17_tiered_reweight.py
"""

from __future__ import annotations

import functools
import itertools
import json
from pathlib import Path

import polars as pl

# Reused, unchanged, from the existing full-17 reweight driver -- not copied.
# Cross-script import works because ``uv run python scripts/<this file>.py``
# puts ``scripts/`` (this file's own directory) at sys.path[0], and both
# files live there.
import run_aggregate_reweight_full17_fixed_index as reweight

from digiquant.strategies.sdca.curve_optimize import (
    _MID_TIER_KEYS,
    WIDE_KNEE_TIERED_COARSE_GRID,
    WIDE_KNEE_TIERED_SEARCH_BOUNDS,
)
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    FeasibilityAwareCurveSearchResult,
    search_wide_knee_curve_feasibility_aware,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "full17_tiered_reweight.json"

FULL_INITIAL_CASH = 10_000.0

# Plain defaults, matching load_inputs()'s implicit use of SdcaOscillatorSpec()
# (it calls load_sdca_extra_z(...) with no oscillators= kwarg at all) --
# deliberately NOT run_full_recalibration_feasible_curve.py's bespoke
# STAGE1_OSCILLATORS (that script's own "Stage 1 winners" from a different,
# sequential fixed_index/Round 2/Stage 2b/3b script lineage, verified to
# diverge substantially from these plain defaults -- e.g. rsi_length=5 vs
# the default 14). Using STAGE1_OSCILLATORS here would recompute fold-local
# indicators under a totally different window set than the frozen index this
# script's curve search ran against, silently introducing a train/gate
# mismatch.
GATE_OSCILLATORS = SdcaOscillatorSpec()


def dedup_weight_candidates(
    candidates: list[tuple[str, SdcaCompositeWeights]],
) -> list[tuple[str, SdcaCompositeWeights]]:
    """Drop candidates whose weights are identical to an earlier one (keeps
    the first label seen), so an expensive curve search never reruns on a
    byte-identical frozen index."""
    seen: set[tuple[float, ...]] = set()
    out: list[tuple[str, SdcaCompositeWeights]] = []
    for label, weights in candidates:
        key = tuple(weights.model_dump().values())
        if key in seen:
            continue
        seen.add(key)
        out.append((label, weights))
    return out


def run_reweight_search(
    dates, power_law_z, extra_z, long_windows, medium_windows
) -> list[tuple[str, SdcaCompositeWeights]]:
    """Reproduce run_aggregate_reweight_full17_fixed_index.main()'s coarse
    pass, refine pass, and ratio-sensitivity pass -- unchanged reweight-
    search functions, same control flow -- returning the resulting small
    candidate set instead of only printing/writing it as main() does."""
    print(f"surviving indicators (N={len(reweight.SURVIVING_INDICATORS)}): {list(reweight.SURVIVING_INDICATORS)}")
    print(f"extra_windows override (real Stage 1 periods): {reweight.EXTRA_WINDOWS}")
    print(
        f"coarse grid resolution: N={len(reweight.SURVIVING_INDICATORS)} > 12 -> "
        "2-point (0.1, 1.0) exhaustive"
    )

    print("\n=== Coarse pass: 2-point floor/max grid, exhaustive product, all ratios reused ===")
    results, names = reweight.run_parallel_scan(
        dates,
        power_law_z,
        extra_z,
        long_windows,
        medium_windows,
        reweight.EXTRA_SEARCH_NAMES,
        reweight.COARSE_GRID,
    )

    coarse_weights, coarse_primary_obj = reweight.best_for_ratio(results, names, *reweight.PRIMARY_RATIO)
    coarse_weights_dict = coarse_weights.model_dump()
    print(f"coarse winner (ratio {reweight.PRIMARY_RATIO[0]:g}:{reweight.PRIMARY_RATIO[1]:g}): {coarse_weights_dict}")
    print(f"coarse primary objective: {coarse_primary_obj:.3f}")

    at_max = [
        name
        for name in reweight.SURVIVING_INDICATORS
        if coarse_weights_dict.get(name, 0.0) >= reweight.MAX_WEIGHT - 1e-9
    ]
    print(f"\nindicators at coarse max (real signal, candidates for refine): {at_max}")

    refine_grids = {name: reweight.refined_window(coarse_weights_dict[name]) for name in at_max}
    joint_evals = 1
    for name in at_max:
        joint_evals *= len(refine_grids[name])
    print(f"joint refine product would be {joint_evals} evals")

    refined_weights_dict = dict(coarse_weights_dict)
    if not at_max:
        print("no indicator sat at max on the coarse pass -- skipping refine.")
    elif joint_evals <= 2_000_000:
        print(f"\n=== Refined pass: JOINT exhaustive product over {at_max} ({joint_evals} evals) ===")
        refine_names_extras = [n for n in at_max if n != "power_law"]
        pl_options = refine_grids.get("power_law", (coarse_weights_dict["power_law"],))
        extra_grids = [refine_grids[n] for n in refine_names_extras]
        best_obj = float("-inf")
        best_payload = dict(coarse_weights_dict)
        for pl_val in pl_options:
            for combo in itertools.product(*extra_grids) if extra_grids else [()]:
                payload = dict(coarse_weights_dict)
                payload["power_law"] = pl_val
                for n, v in zip(refine_names_extras, combo, strict=True):
                    payload[n] = v
                extras_kwargs = {k: v for k, v in payload.items() if k != "power_law"}
                weights = SdcaCompositeWeights(power_law=float(pl_val), **extras_kwargs)
                score = reweight.full_score(
                    dates, power_law_z, extra_z, long_windows, medium_windows, weights, *reweight.PRIMARY_RATIO
                )
                if score.objective > best_obj:
                    best_obj = score.objective
                    best_payload = payload
        refined_weights_dict = best_payload
        print(f"refined winner: {refined_weights_dict}")
        print(f"refined objective: {best_obj:.3f}")
    else:
        print(f"\n=== Refined pass: ONE-AT-A-TIME over {at_max} (joint {joint_evals} > 2,000,000) ===")
        current = dict(coarse_weights_dict)
        for name in at_max:
            best_val = current[name]
            best_obj = float("-inf")
            for v in refine_grids[name]:
                trial = dict(current)
                trial[name] = v
                pl_val = trial.pop("power_law")
                weights = SdcaCompositeWeights(power_law=float(pl_val), **trial)
                score = reweight.full_score(
                    dates, power_law_z, extra_z, long_windows, medium_windows, weights, *reweight.PRIMARY_RATIO
                )
                if score.objective > best_obj:
                    best_obj = score.objective
                    best_val = v
            current[name] = best_val
            print(f"  refined {name}: {best_val} (objective {best_obj:.3f})")
        refined_weights_dict = current

    print(f"\nfinal refined weights: {refined_weights_dict}")

    print("\n=== Ratio sensitivity (2:1, 3:1, 5:1), reusing coarse-pass precomputed scores ===")
    candidates: list[tuple[str, SdcaCompositeWeights]] = [
        ("refined_primary_3_1", SdcaCompositeWeights(**refined_weights_dict))
    ]
    for lw, mw in reweight.RATIOS:
        weights, obj = reweight.best_for_ratio(results, names, lw, mw)
        key = f"{lw:g}:{mw:g}"
        print(f"  {key}: objective={obj:.3f} weights={weights.model_dump()}")
        candidates.append((f"coarse_ratio_{key}", weights))

    deduped = dedup_weight_candidates(candidates)
    print(
        f"\n{len(candidates)} candidate(s) produced, {len(deduped)} distinct after dedup: "
        f"{[label for label, _ in deduped]}"
    )
    return deduped


def curve_search_over_candidates(
    dates, prices, power_law_z, extra_z, candidates: list[tuple[str, SdcaCompositeWeights]]
) -> tuple[str, SdcaCompositeWeights, FeasibilityAwareCurveSearchResult]:
    """Run Task 6's tiered feasibility-aware curve search against each
    candidate's frozen index; return the overall (weights, curve) winner
    ranked by feasibility_adjusted_score."""
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    print(
        "\n=== Tiered feasibility-aware curve search per candidate weighting "
        f"({len(candidates)} candidate(s)) ==="
    )
    best_label: str | None = None
    best_weights: SdcaCompositeWeights | None = None
    best_curve: FeasibilityAwareCurveSearchResult | None = None
    for label, weights in candidates:
        risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
        risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)
        curve_result = search_wide_knee_curve_feasibility_aware(
            date_s,
            price_s,
            risk_s,
            initial_cash=FULL_INITIAL_CASH,
            bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
            grid=WIDE_KNEE_TIERED_COARSE_GRID,
            extra_keys=_MID_TIER_KEYS,
        )
        print(
            f"  [{label}] num_evaluations={curve_result.num_evaluations}  "
            f"feasibility_adjusted_score={curve_result.best.feasibility_adjusted_score:.4f}  "
            f"risk_adjusted_return={curve_result.best.risk_adjusted_return:.4f}  "
            f"capital_deployed_pct={curve_result.best.capital_deployed_pct:.1f}%  "
            f"max_drawdown_pct={curve_result.best.base.max_drawdown_pct:.2f}%"
        )
        if best_curve is None or curve_result.best.feasibility_adjusted_score > best_curve.best.feasibility_adjusted_score:
            best_label, best_weights, best_curve = label, weights, curve_result

    assert best_label is not None and best_weights is not None and best_curve is not None
    print(
        f"\noverall (weights, curve) winner: {best_label}  "
        f"feasibility_adjusted_score={best_curve.best.feasibility_adjusted_score:.4f}"
    )
    print(f"  winning weights: {best_weights.model_dump()}")
    print(f"  winning curve shape: {best_curve.best.shape.model_dump()}")
    return best_label, best_weights, best_curve


def run_walk_forward_gate(
    dates, prices, extra_z, winning_weights: SdcaCompositeWeights, winning_curve_shape
) -> SdcaWalkForwardResult:
    trial: dict[str, float | int | str] = dict(freeze_weight_params(winning_weights))
    trial.update(winning_curve_shape.model_dump())
    # oscillators=GATE_OSCILLATORS is explicit for clarity -- it's the same
    # SdcaOscillatorSpec() plain default that evaluate_sdca_trial_curve_sim's
    # own oscillators: SdcaOscillatorSpec | None = None already resolves to,
    # and matches load_inputs()'s implicit default (see module docstring).
    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=GATE_OSCILLATORS)
    return run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )


def print_walk_forward_table(result: SdcaWalkForwardResult) -> None:
    print(f"\n=== Walk-forward OOS validation gate ({result.evaluator_label}) ===")
    print(f"{len(result.folds)} folds, holdout tail {result.holdout[0]}..{result.holdout[1]}\n")
    for fs in result.fold_scores:
        f = fs.fold
        is_m, oos_m = fs.in_sample, fs.out_of_sample
        print(
            f"  fold {f.fold}: IS {f.is_start}..{f.is_end}  OOS {f.oos_start}..{f.oos_end}\n"
            f"    IS  vs_flat_dca={is_m.vs_flat_dca_pct:+8.2f}%  vs_lump={is_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={is_m.capital_deployed_pct:5.1f}%  max_dd={is_m.max_drawdown_pct:5.1f}%\n"
            f"    OOS vs_flat_dca={oos_m.vs_flat_dca_pct:+8.2f}%  vs_lump={oos_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={oos_m.capital_deployed_pct:5.1f}%  max_dd={oos_m.max_drawdown_pct:5.1f}%  "
            f"oos_minus_is={oos_m.vs_flat_dca_pct - is_m.vs_flat_dca_pct:+6.2f}  feasible={fs.feasible}"
        )
    print(
        f"\n  mean IS vs_flat_dca={result.mean_is_vs_flat_dca_pct:+.2f}%  "
        f"mean OOS vs_flat_dca (primary, {result.fold_weighting})={result.mean_oos_vs_flat_dca_pct:+.2f}%  "
        f"IS-OOS gap (is_oos_gap_pct = mean_is - mean_oos)={result.is_oos_gap_pct:+.2f}"
    )
    print(
        f"  mean OOS vs_flat_dca unweighted={result.mean_oos_vs_flat_dca_pct_unweighted:+.2f}%  "
        f"mean OOS vs_flat_dca duration_weighted={result.mean_oos_vs_flat_dca_pct_duration_weighted:+.2f}%"
    )
    print(f"  beats_flat_dca_oos={result.beats_flat_dca_oos}")
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"  holdout: vs_flat_dca={h.vs_flat_dca_pct:+.2f}%  vs_lump={h.vs_lump_pct:+.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.1f}%  max_dd={h.max_drawdown_pct:.1f}%"
        )
    s = result.sensitivity
    print(
        f"\n  sensitivity (+/-{s.frac:g} on every numeric param, {s.neighbor_count} valid neighbors):\n"
        f"    max_abs_delta_oos_pct={s.max_abs_delta_oos_pct:.2f}  "
        f"spike_threshold_pct={s.spike_threshold_pct:g}  stable={s.stable}"
    )
    print(f"\n  num_evaluations={result.num_evaluations}  objective={result.objective.model_dump()}")


def main() -> None:
    dates, power_law_z, extra_z, long_windows, medium_windows = reweight.load_inputs()
    # load_inputs() doesn't return raw prices -- call load_sdca_ohlcv() a
    # second time ourselves (same call load_inputs() makes internally,
    # cheap) since both the curve search and the walk-forward gate need it.
    _dates2, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    assert _dates2 == dates, "load_sdca_ohlcv returned different dates on the second call"
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    candidates = run_reweight_search(dates, power_law_z, extra_z, long_windows, medium_windows)
    winning_label, winning_weights, winning_curve = curve_search_over_candidates(
        dates, prices, power_law_z, extra_z, candidates
    )

    result = run_walk_forward_gate(dates, prices, extra_z, winning_weights, winning_curve.best.shape)
    print_walk_forward_table(result)

    out = {
        "surviving_indicators": list(reweight.SURVIVING_INDICATORS),
        "extra_windows_override": reweight.EXTRA_WINDOWS,
        "candidate_labels": [label for label, _ in candidates],
        "winning_candidate_label": winning_label,
        "winning_weights": winning_weights.model_dump(),
        "winning_curve_shape": winning_curve.best.shape.model_dump(),
        "curve_search_notes": winning_curve.notes,
        "walk_forward_result": result.model_dump(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")

    qualifies = result.beats_flat_dca_oos and result.sensitivity.stable
    infeasible_folds = [fs.fold.fold for fs in result.fold_scores if not fs.feasible]
    print(
        f"\nOVERALL: winning_candidate={winning_label}  beats_flat_dca_oos={result.beats_flat_dca_oos}  "
        f"sensitivity_stable={result.sensitivity.stable}  qualifies_as_new_baseline_candidate={qualifies}"
    )
    if infeasible_folds:
        print(
            f"  NOTE: fold(s) {infeasible_folds} are infeasible under the objective's "
            "capital-deployed floor / drawdown cap (SdcaOptimizeObjective) -- "
            "mean_oos_vs_flat_dca_pct and beats_flat_dca_oos are plain (or duration-weighted) "
            "averages over ALL folds regardless of feasibility, so a positive beats_flat_dca_oos "
            "here does not by itself mean every fold cleared the feasibility rails -- check the "
            "per-fold feasible= flags above."
        )
    print(
        "\nDiagnostic walk-forward gate only -- this script NEVER writes settings.json or "
        "RESEARCH_STATE.md's \"current best validated candidate\" section, regardless of this "
        "result. Report this table to Chris for explicit accept/reject; qualifying for the gate "
        "(beats_flat_dca_oos=True AND sensitivity stable=True) is necessary but not sufficient -- "
        "only his explicit accept promotes a candidate."
    )


if __name__ == "__main__":
    main()
