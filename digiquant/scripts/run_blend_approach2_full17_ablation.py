#!/usr/bin/env python3
"""Blend Approach 2: round-8-style iterative ablation, seeded with the full 17-survivor pool.

Chris likes "the valuation index shape of the 17 indicator strat, then the
performance and behavior of the round 8 [strategy]." Approach 1 tested the
most literal reading (freeze Round 2's weights, just re-search the curve).
Approach 2 tests the other reading: keep round 8's *search method*
(``ablation.run_ablation_rounds``'s reweight -> find-dominant -> drop ->
repeat loop, exactly as ``scripts/run_iterative_ablation.py`` drives it) but
seed it with Task #93 Round 2's full 17-survivor pool
(``SURVIVING_INDICATORS``, duplicated verbatim from
``run_aggregate_reweight_full17_fixed_index.py``) instead of the smaller
12-name diagnostic default pool round 8 itself started from. Round 8's own
5-name pool is already a strict subset of these 17, so this is the
admissible-indicator ceiling, not a bigger universe -- per the standing
Phase-B gate, ``vol_regime``/``halving_cycle`` are Stage-2 REJECTED (dead
end #21), ``adx``/``stochastic`` lack OHLC high/low plumbing, and
``fast_crash_vol`` hasn't cleared Stage 1 -- none of the five are eligible
for this pool.

Every round also uses Task #93 Round 2's authoritative oscillator/window
config (``ROUND23_OSCILLATORS``/``ROUND23_EXTRA_WINDOWS``, the config that
actually produced ``baseline_relative_rescore.json``'s recorded scores --
see ``run_baseline_relative_rescore.py``), not round 8's own defaults. This
is a genuine, deliberate methodological difference from round 8's own
historical scoring, called out explicitly in the final report.

Round logs go to ``.scratch/blend/approach2_round_{n}.json``. After the
ablation loop finishes, the best-seen round's weights get a full-resolution
feasibility-aware curve search + full ``run_sdca_walk_forward_vs_baseline``
validation (mirroring ``run_ablation_best_round_full_resolution.py``'s
pattern), written to ``.scratch/blend/approach2_full_resolution.json``.

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_blend_approach2_full17_ablation.py
"""

from __future__ import annotations

import functools
import itertools
import json
import multiprocessing
import time
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from digiquant.strategies.sdca import _aggregate_reweight_parallel as worker
from digiquant.strategies.sdca.ablation import (
    AblationRoundResult,
    AblationRunResult,
    run_ablation_rounds,
)
from digiquant.strategies.sdca.baseline_evaluator import (
    WalkForwardBaselineComparison,
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import params_from_shape
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    search_wide_knee_curve_feasibility_aware,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import (
    combined_cycle_overlap_score,
    optimize_stage_a_weights_combined_multi_ratio,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
ROUNDS_DIR = DIGIQUANT_ROOT / ".scratch" / "blend"
FULL_RES_OUT_PATH = ROUNDS_DIR / "approach2_full_resolution.json"

# SURVIVING_INDICATORS duplicated verbatim from
# run_aggregate_reweight_full17_fixed_index.py -- Task #93 Round 2's full
# 17-survivor pool, the admissible-indicator ceiling for this blend attempt.
SURVIVING_INDICATORS: tuple[str, ...] = (
    "power_law",
    "m2",
    "rs_eth",
    "dxy",
    "onchain_mvrv",
    "onchain_asopr",
    "onchain_puell",
    "onchain_rhodl",
    "onchain_addr_ratio",
    "fear_greed",
    "weekly_monthly_rsi",
    "weekly_monthly_macd",
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
    "monthly_rsi",
    "monthly_macd",
)
INITIAL_POOL: tuple[str, ...] = SURVIVING_INDICATORS

# ROUND23_* duplicated verbatim from run_baseline_relative_rescore.py -- the
# authoritative oscillator/window config for the 17-survivor pool (NOT round
# 8's own defaults -- see module docstring).
ROUND23_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    rs_eth_window=60,
    rs_eth_fast_window=30,
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=12,
    macd_slow=26,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=180,
    sma_band_fast_window=45,
    monthly_rsi_length=5,
    monthly_rsi_daily_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)

ROUND23_EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

MIN_FLOOR = 0.1
MAX_WEIGHT = 1.0
COARSE_GRID: tuple[float, ...] = (MIN_FLOOR, MAX_WEIGHT)
DROPPED_GRID: tuple[float, ...] = (0.0,)
REFINE_STEP = 0.05
REFINE_HALF_WIDTH = 0.15
JOINT_REFINE_EVAL_CEILING = 2_000_000
PRIMARY_RATIO: tuple[float, float] = (3.0, 1.0)
PARALLEL_DISPATCH_THRESHOLD = 10  # pools larger than this use the worker pool
N_WORKERS = 16
CHUNK_SIZE = 512

GATE_N_RANDOM = 300
GATE_INITIAL_CASH = 10_000.0
FULL_INITIAL_CASH = 10_000.0

ROUND23_EVALUATOR = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=ROUND23_OSCILLATORS)


@dataclass(frozen=True)
class AblationInputs:
    dates: list
    prices: list
    date_s: pl.Series
    price_s: pl.Series
    power_law_z: list
    extra_z: dict
    long_windows: SdcaCycleWindows
    medium_windows: SdcaCycleWindows


def load_inputs() -> AblationInputs:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s,
        price_s,
        rails["low"],
        rails["median"],
        rails["high"],
        trend_window=ROUND23_OSCILLATORS.power_law_trend_window,
    ).to_list()

    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=ROUND23_OSCILLATORS,
        extra_windows=ROUND23_EXTRA_WINDOWS,
    )
    missing = [n for n in SURVIVING_INDICATORS if n != "power_law" and n not in extra_z]
    if missing:
        raise SystemExit(f"missing extra_z for: {missing} -- have {sorted(extra_z)}")

    return AblationInputs(
        dates=dates,
        prices=prices,
        date_s=date_s,
        price_s=price_s,
        power_law_z=power_law_z,
        extra_z=extra_z,
        long_windows=SdcaCycleWindows.btc_v1(),
        medium_windows=SdcaCycleWindows.btc_medium_term_v1(),
    )


# ---------------------------------------------------------------------------
# Coarse-scan helpers, duplicated verbatim from run_iterative_ablation.py /
# run_aggregate_reweight_full17_fixed_index.py per the self-contained-script
# convention.
# ---------------------------------------------------------------------------


def refined_window(coarse_value: float) -> tuple[float, ...]:
    lo = max(MIN_FLOOR, coarse_value - REFINE_HALF_WIDTH)
    hi = min(MAX_WEIGHT, coarse_value + REFINE_HALF_WIDTH)
    vals: set[float] = set()
    n_steps = round((hi - lo) / REFINE_STEP)
    for i in range(n_steps + 1):
        vals.add(round(lo + i * REFINE_STEP, 4))
    vals.add(round(coarse_value, 4))
    return tuple(sorted(v for v in vals if MIN_FLOOR - 1e-9 <= v <= MAX_WEIGHT + 1e-9))


def chunked(iterable, size):
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, size))
        if not batch:
            return
        yield batch


def run_parallel_scan(data: AblationInputs, extra_names, extra_grid, power_law_grid):
    all_combos = [
        (pl_val, combo)
        for pl_val in power_law_grid
        for combo in itertools.product(extra_grid, repeat=len(extra_names))
    ]
    total = len(all_combos)
    print(f"  scanning {total} combos across {N_WORKERS} workers...")
    ctx = multiprocessing.get_context("spawn")
    t0 = time.time()
    results: list[tuple[float, tuple[float, ...], float, float]] = []
    with ctx.Pool(
        processes=N_WORKERS,
        initializer=worker.init_globals,
        initargs=(
            data.dates,
            data.power_law_z,
            data.extra_z,
            data.long_windows,
            data.medium_windows,
            extra_names,
        ),
    ) as pool:
        for res in pool.imap_unordered(worker.score_chunk, chunked(all_combos, CHUNK_SIZE)):
            results.extend(res)
    dt = time.time() - t0
    print(f"  done in {dt:.1f}s ({total / max(dt, 1e-9):.0f} evals/s), {len(results)} feasible")
    return results


def best_for_ratio(results, names, lw: float, mw: float) -> SdcaCompositeWeights:
    best = None
    best_obj = float("-inf")
    for pl_val, combo, long_obj, medium_obj in results:
        obj = lw * long_obj + mw * medium_obj
        if obj > best_obj:
            best_obj = obj
            best = (pl_val, combo)
    if best is None:
        raise ValueError("no feasible combo in coarse scan results")
    pl_val, combo = best
    return SdcaCompositeWeights(power_law=pl_val, **dict(zip(names, combo, strict=True)))


def full_score(data: AblationInputs, weights: SdcaCompositeWeights, lw: float, mw: float) -> float:
    risk = risk_from_weighted_z(data.dates, data.power_law_z, data.extra_z, weights)
    return combined_cycle_overlap_score(
        data.dates, risk, data.long_windows, data.medium_windows, long_weight=lw, medium_weight=mw
    ).objective


def refine_at_max(
    data: AblationInputs, pool: tuple[str, ...], coarse_weights: SdcaCompositeWeights
):
    coarse_dict = coarse_weights.model_dump()
    at_max = [name for name in pool if coarse_dict.get(name, 0.0) >= MAX_WEIGHT - 1e-9]
    if not at_max:
        return coarse_weights

    refine_grids = {name: refined_window(coarse_dict[name]) for name in at_max}
    joint_evals = 1
    for name in at_max:
        joint_evals *= len(refine_grids[name])

    refine_extras = [n for n in at_max if n != "power_law"]
    pl_options = refine_grids.get("power_law", (coarse_dict["power_law"],))

    if joint_evals <= JOINT_REFINE_EVAL_CEILING:
        extra_grids = [refine_grids[n] for n in refine_extras]
        best_obj = float("-inf")
        best_payload = dict(coarse_dict)
        for pl_val in pl_options:
            for combo in itertools.product(*extra_grids) if extra_grids else [()]:
                payload = dict(coarse_dict)
                payload["power_law"] = pl_val
                for n, v in zip(refine_extras, combo, strict=True):
                    payload[n] = v
                weights = SdcaCompositeWeights(
                    **{k: v for k, v in payload.items() if k in pool or k == "power_law"}
                )
                score = full_score(data, weights, *PRIMARY_RATIO)
                if score > best_obj:
                    best_obj = score
                    best_payload = payload
        refined = best_payload
    else:
        current = dict(coarse_dict)
        for name in at_max:
            best_val = current[name]
            best_obj = float("-inf")
            for v in refine_grids[name]:
                trial = dict(current)
                trial[name] = v
                weights = SdcaCompositeWeights(
                    **{k: v2 for k, v2 in trial.items() if k in pool or k == "power_law"}
                )
                score = full_score(data, weights, *PRIMARY_RATIO)
                if score > best_obj:
                    best_obj = score
                    best_val = v
            current[name] = best_val
        refined = current

    return SdcaCompositeWeights(
        **{k: v for k, v in refined.items() if k in pool or k == "power_law"}
    )


def make_reweight_fn(data: AblationInputs):
    def reweight_fn(pool: tuple[str, ...]) -> SdcaCompositeWeights:
        has_power_law = "power_law" in pool
        extra_names = tuple(n for n in pool if n != "power_law")
        power_law_grid = COARSE_GRID if has_power_law else DROPPED_GRID

        if len(pool) > PARALLEL_DISPATCH_THRESHOLD:
            results = run_parallel_scan(data, extra_names, COARSE_GRID, power_law_grid)
            coarse_weights = best_for_ratio(results, extra_names, *PRIMARY_RATIO)
        else:
            ratio_results = optimize_stage_a_weights_combined_multi_ratio(
                data.dates,
                power_law_z=data.power_law_z,
                extra_z=data.extra_z,
                long_windows=data.long_windows,
                medium_windows=data.medium_windows,
                search_names=extra_names,
                grid=COARSE_GRID,
                power_law_grid=power_law_grid,
                ratios=(PRIMARY_RATIO,),
            )
            coarse_weights = ratio_results[PRIMARY_RATIO].weights

        return refine_at_max(data, pool, coarse_weights)

    return reweight_fn


def make_gate_fn(data: AblationInputs):
    def gate_fn(pool: tuple[str, ...], weights: SdcaCompositeWeights) -> tuple[float, float]:
        risk_list = risk_from_weighted_z(data.dates, data.power_law_z, data.extra_z, weights)
        risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)
        curve_result = search_wide_knee_curve_feasibility_aware(
            data.date_s,
            data.price_s,
            risk_s,
            initial_cash=GATE_INITIAL_CASH,
            n_random=GATE_N_RANDOM,
        )
        candidate_params = {
            **freeze_weight_params(weights),
            **params_from_shape(curve_result.best.shape),
        }
        result = run_sdca_walk_forward(
            data.dates,
            data.prices,
            [candidate_params],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=ROUND23_EVALUATOR,
            evaluator_label="curve_simulator",
            extra_z=data.extra_z,
            fold_weighting="duration",
        )
        return (
            result.mean_oos_vs_flat_dca_pct_unweighted,
            result.mean_oos_vs_flat_dca_pct_duration_weighted,
        )

    return gate_fn


def _round_summary(round_result: AblationRoundResult) -> dict:
    return round_result.model_dump()


def log_round(round_result: AblationRoundResult) -> None:
    ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    path = ROUNDS_DIR / f"approach2_round_{round_result.round_index}.json"
    path.write_text(json.dumps(_round_summary(round_result), indent=2, default=str))
    print(
        f"round {round_result.round_index}: pool={list(round_result.pool)} "
        f"dominant={round_result.dominant_indicator} (weight={round_result.dominant_weight:.3f}) "
        f"oos_unweighted={round_result.mean_oos_vs_flat_dca_pct_unweighted:+.2f}% "
        f"oos_duration={round_result.mean_oos_vs_flat_dca_pct_duration_weighted:+.2f}%"
    )


def print_summary(result: AblationRunResult) -> None:
    print(f"\n=== stop_reason: {result.stop_reason} ({len(result.rounds)} rounds run) ===")
    best = result.best_round
    print(
        f"best round: #{best.round_index} pool={list(best.pool)} "
        f"dominant={best.dominant_indicator} (weight={best.dominant_weight:.3f})"
    )
    print(f"  oos_unweighted={best.mean_oos_vs_flat_dca_pct_unweighted:+.2f}%")
    print(f"  oos_duration_weighted={best.mean_oos_vs_flat_dca_pct_duration_weighted:+.2f}%")
    print(f"  weights={best.weights.model_dump()}")


def print_comparison(comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print("=== blend_approach2_full_resolution ===")
    print(
        f"  candidate  mean_oos(unweighted)={c.mean_oos_vs_flat_dca_pct_unweighted:+7.2f}%  "
        f"mean_oos(duration)={c.mean_oos_vs_flat_dca_pct_duration_weighted:+7.2f}%  "
        f"beats_flat_dca_oos={c.beats_flat_dca_oos}  sensitivity_stable={c.sensitivity.stable}"
    )
    print(
        f"  baseline   mean_oos(unweighted)={b.mean_oos_vs_flat_dca_pct_unweighted:+7.2f}%  "
        f"mean_oos(duration)={b.mean_oos_vs_flat_dca_pct_duration_weighted:+7.2f}%  "
        f"beats_flat_dca_oos={b.beats_flat_dca_oos}  sensitivity_stable={b.sensitivity.stable}"
    )
    print(
        f"  delta_mean_oos_vs_flat_dca_pct={comparison.delta_mean_oos_vs_flat_dca_pct:+7.2f}%  "
        f"beats_baseline_oos={comparison.beats_baseline_oos}\n"
    )


def main() -> None:
    data = load_inputs()
    print(f"BTC-USD {data.dates[0]}..{data.dates[-1]} ({len(data.dates)} daily bars)")
    print(f"initial pool (N={len(INITIAL_POOL)}): {list(INITIAL_POOL)}\n")

    result = run_ablation_rounds(
        INITIAL_POOL,
        reweight_fn=make_reweight_fn(data),
        gate_fn=make_gate_fn(data),
        on_round=log_round,
    )
    print_summary(result)

    best = result.best_round
    print("\nrunning full-resolution feasibility-aware curve search on best round's weights...")
    risk_list = risk_from_weighted_z(data.dates, data.power_law_z, data.extra_z, best.weights)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)
    curve_result = search_wide_knee_curve_feasibility_aware(
        data.date_s, data.price_s, risk_s, initial_cash=FULL_INITIAL_CASH
    )
    candidate_params = {
        **freeze_weight_params(best.weights),
        **params_from_shape(curve_result.best.shape),
    }

    print("running full walk-forward vs. risk50-linear baseline (with sensitivity check)...")
    comparison = run_sdca_walk_forward_vs_baseline(
        data.dates,
        data.prices,
        candidate_params,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=ROUND23_EVALUATOR,
        evaluator_label="curve_simulator",
        extra_z=data.extra_z,
        fold_weighting="duration",
    )
    print_comparison(comparison)

    FULL_RES_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FULL_RES_OUT_PATH.write_text(
        json.dumps(
            {
                "best_round_index": best.round_index,
                "best_round_pool": list(best.pool),
                "stop_reason": result.stop_reason,
                "comparison": comparison.model_dump(),
            },
            indent=2,
            default=str,
        )
    )
    print(f"wrote {FULL_RES_OUT_PATH}")
    print(
        "\nDiagnostic blend attempt only -- never writes settings.json or "
        'RESEARCH_STATE.md\'s "current best validated candidate" section. Report '
        "this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
