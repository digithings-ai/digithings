#!/usr/bin/env python3
"""Aggregate reweight (Stage 4-equivalent) over the full 17-indicator survivor list.

N=17 dimensions (power_law + 16 extras) -> per the task's dimensionality
rule (N>12), a 2-point coarse floor/max grid (0.1, 1.0), exhaustive product:
2 * 2**16 = 131072 evaluations. Serial cost measured at ~15ms/eval (~32min),
so the exhaustive product is computed with fork-based multiprocessing
(``_parallel_reweight_worker.py``) -- every per-combo evaluation is
byte-for-byte the same ``SdcaCompositeWeights`` construction +
``risk_from_weighted_z`` + ``cycle_overlap_score`` calls
``stage_a.optimize_stage_a_weights_combined``/``_multi_ratio`` make; only the
outer loop is parallelized. Each combo's long/medium objective scalars are
kept (not the full risk series), so the same one pass answers both the 3:1
coarse-winner question and the 2:1/3:1/5:1 sensitivity sweep by
recombining those scalars per ratio -- no re-search, matching
``optimize_stage_a_weights_combined_multi_ratio``'s "reuse precomputed
scores" design.

A refined pass follows: any indicator whose coarse (3:1) winner sat at the
1.0 ceiling (not just floor-pinned) gets a local 0.05-step sweep within
+/-0.15, still clamped to [0.1, 1.0].

Usage:
    uv run python scripts/run_aggregate_reweight_full17.py
"""

from __future__ import annotations

import itertools
import json
import multiprocessing
import time
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z
from digiquant.strategies.sdca import _aggregate_reweight_parallel as worker

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "aggregate_reweight_full17_result.json"

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
EXTRA_SEARCH_NAMES: tuple[str, ...] = tuple(n for n in SURVIVING_INDICATORS if n != "power_law")

MIN_FLOOR = 0.1
MAX_WEIGHT = 1.0
COARSE_GRID = (MIN_FLOOR, MAX_WEIGHT)  # N=17 > 12 -> 2-point coarse grid per task rules
REFINE_STEP = 0.05
REFINE_HALF_WIDTH = 0.15
RATIOS: tuple[tuple[float, float], ...] = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))
PRIMARY_RATIO = (3.0, 1.0)
N_WORKERS = 16
CHUNK_SIZE = 512


def load_inputs():
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    ).to_list()

    extra_z = load_sdca_extra_z(dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None)
    missing = [n for n in EXTRA_SEARCH_NAMES if n not in extra_z]
    if missing:
        raise SystemExit(f"missing extra_z for: {missing} -- have {sorted(extra_z)}")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    return dates, power_law_z, extra_z, long_windows, medium_windows


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


def run_parallel_scan(dates, power_law_z, extra_z, long_windows, medium_windows, names, grid):
    """Exhaustive product over power_law_grid x grid^len(names); returns list
    of (pl_val, combo, long_objective, medium_objective) for every feasible
    combo -- the same combos ``optimize_stage_a_weights_combined`` would
    evaluate with these grids and this ``min_weight_floor``-equivalent grid
    (grids passed in are already floor-clamped, i.e. contain no 0.0)."""
    all_combos = [
        (pl_val, combo)
        for pl_val in grid
        for combo in itertools.product(grid, repeat=len(names))
    ]
    total = len(all_combos)
    print(f"  scanning {total} combos across {N_WORKERS} workers...")
    ctx = multiprocessing.get_context("spawn")
    t0 = time.time()
    results: list[tuple[float, tuple[float, ...], float, float]] = []
    with ctx.Pool(
        processes=N_WORKERS,
        initializer=worker.init_globals,
        initargs=(dates, power_law_z, extra_z, long_windows, medium_windows, names),
    ) as pool:
        for res in pool.imap_unordered(worker.score_chunk, chunked(all_combos, CHUNK_SIZE)):
            results.extend(res)
    dt = time.time() - t0
    print(f"  done in {dt:.1f}s ({total / dt:.0f} evals/s), {len(results)} feasible")
    return results, names


def best_for_ratio(results, names, lw: float, mw: float):
    best = None
    best_obj = float("-inf")
    for pl_val, combo, long_obj, medium_obj in results:
        obj = lw * long_obj + mw * medium_obj
        if obj > best_obj:
            best_obj = obj
            best = (pl_val, combo)
    pl_val, combo = best
    weights = SdcaCompositeWeights(power_law=pl_val, **dict(zip(names, combo, strict=True)))
    return weights, best_obj


def full_score(dates, power_law_z, extra_z, long_windows, medium_windows, weights, lw, mw):
    risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows, long_weight=lw, medium_weight=mw
    )


def main() -> None:
    dates, power_law_z, extra_z, long_windows, medium_windows = load_inputs()
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} bars)")
    print(f"surviving indicators (N={len(SURVIVING_INDICATORS)}): {list(SURVIVING_INDICATORS)}")
    print(f"coarse grid resolution: N={len(SURVIVING_INDICATORS)} > 12 -> 2-point (0.1, 1.0) exhaustive")

    print("\n=== Coarse pass: 2-point floor/max grid, exhaustive product, all ratios reused ===")
    results, names = run_parallel_scan(
        dates, power_law_z, extra_z, long_windows, medium_windows, EXTRA_SEARCH_NAMES, COARSE_GRID
    )

    coarse_weights, coarse_primary_obj = best_for_ratio(results, names, *PRIMARY_RATIO)
    coarse_weights_dict = coarse_weights.model_dump()
    print(f"coarse winner (ratio {PRIMARY_RATIO[0]:g}:{PRIMARY_RATIO[1]:g}): {coarse_weights_dict}")
    print(f"coarse primary objective: {coarse_primary_obj:.3f}")

    at_max = [
        name for name in SURVIVING_INDICATORS if coarse_weights_dict.get(name, 0.0) >= MAX_WEIGHT - 1e-9
    ]
    print(f"\nindicators at coarse max (real signal, candidates for refine): {at_max}")

    refine_grids = {name: refined_window(coarse_weights_dict[name]) for name in at_max}
    joint_evals = 1
    for name in at_max:
        joint_evals *= len(refine_grids[name])
    print(f"joint refine product would be {joint_evals} evals")

    refined_weights_dict = dict(coarse_weights_dict)
    refine_mode = "none"
    if not at_max:
        print("no indicator sat at max on the coarse pass -- skipping refine.")
    elif joint_evals <= 2_000_000:
        refine_mode = "joint"
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
                score = full_score(
                    dates, power_law_z, extra_z, long_windows, medium_windows, weights, *PRIMARY_RATIO
                )
                if score.objective > best_obj:
                    best_obj = score.objective
                    best_payload = payload
        refined_weights_dict = best_payload
        print(f"refined winner: {refined_weights_dict}")
        print(f"refined objective: {best_obj:.3f}")
    else:
        refine_mode = "one-at-a-time"
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
                score = full_score(
                    dates, power_law_z, extra_z, long_windows, medium_windows, weights, *PRIMARY_RATIO
                )
                if score.objective > best_obj:
                    best_obj = score.objective
                    best_val = v
            current[name] = best_val
            print(f"  refined {name}: {best_val} (objective {best_obj:.3f})")
        refined_weights_dict = current

    print(f"\nfinal refined weights: {refined_weights_dict}")
    all_in_range = all(
        MIN_FLOOR - 1e-9 <= v <= MAX_WEIGHT + 1e-9 for v in refined_weights_dict.values() if isinstance(v, float)
    )
    print(f"all weights in [{MIN_FLOOR}, {MAX_WEIGHT}]: {all_in_range}")

    print("\n=== Ratio sensitivity (2:1, 3:1, 5:1), reusing coarse-pass precomputed scores ===")
    ratio_results = {}
    for lw, mw in RATIOS:
        weights, obj = best_for_ratio(results, names, lw, mw)
        key = f"{lw:g}:{mw:g}"
        ratio_results[key] = {"weights": weights.model_dump(), "objective": obj}
        print(f"  {key}: objective={obj:.3f} weights={weights.model_dump()}")

    out = {
        "surviving_indicators": list(SURVIVING_INDICATORS),
        "coarse_grid": list(COARSE_GRID),
        "coarse_winner_3_1": coarse_weights_dict,
        "coarse_primary_objective": coarse_primary_obj,
        "at_coarse_max": at_max,
        "refine_mode": refine_mode,
        "refined_weights": refined_weights_dict,
        "all_weights_in_range": all_in_range,
        "ratio_sensitivity": ratio_results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
