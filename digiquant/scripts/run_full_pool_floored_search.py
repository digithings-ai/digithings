#!/usr/bin/env python3
"""Phase 1 of the 2026-09-24 recalibration: full 12-name pool, weight-floored.

N=12 dimensions (power_law + the 11 ``EXTRA_INDICATOR_NAMES``, the pool this
repo has already individually validated -- see
``docs/superpowers/specs/2026-09-24-sdca-recalibration-v1-design.md`` S2.1).
Unlike ``run_aggregate_reweight_full17.py``'s N=17 search, N=12 sits inside
this repo's exhaustive-serial dimensionality boundary (N<=12 per that
script's own documented rule), so a finer 3-point floored grid -- (0.1, 0.5,
1.0), i.e. ``stage_a._floor_candidates((0.0, 0.5, 1.0), 0.1)`` -- is usable
directly instead of the coarser 2-point floor/max compromise N=17 needed:
3**12 = 531441 combos. Measured directly against this exact objective on
real data: ~12ms/eval serial (~106min total) vs ~6.6min with the same
16-way fork-based parallel infrastructure ``run_aggregate_reweight_full17.py``
already built and validated (``_aggregate_reweight_parallel.py``) -- reused
here as-is (it is generic in ``extra_names``), not reimplemented. Every
evaluated combo is byte-for-byte what
``stage_a.optimize_stage_a_weights_combined_multi_ratio(search_names=EXTRA_INDICATOR_NAMES,
grid=(0.0, 0.5, 1.0), min_weight_floor=0.1)`` would search; only the outer
loop is parallelized, so results are the true grid-search winner, not an
approximation.

No refine pass: the grid is already 3-point (finer than N17's coarse pass),
and every candidate's per-indicator weight is already floor-guaranteed >=
0.1 by construction (``_floor_candidates`` makes 0.0 illegal once a floor is
set) -- there is no "still at the coarse max, refine locally" question the
way N17's binary grid had.

Uses the same frozen Stage 1 oscillator periods and macro/on-chain
``extra_windows`` override as ``run_full_recalibration_fixed_index.py`` (see
that script's own docstring for why: ``SdcaOscillatorSpec()``'s bare
constructor is generic library defaults, not this repo's validated periods).
A first version of this script omitted both, so rs_eth /
weekly_monthly_rsi / weekly_monthly_macd and every macro/on-chain extra were
built against the wrong windows before the result was committed -- fixed
here.

Usage:
    uv run python scripts/run_full_pool_floored_search.py
"""

from __future__ import annotations

import itertools
import json
import multiprocessing
import time
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca import _aggregate_reweight_parallel as worker
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import EXTRA_INDICATOR_NAMES, SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import _floor_candidates

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "full_pool_floored_search_result.json"

EXTRA_SEARCH_NAMES: tuple[str, ...] = EXTRA_INDICATOR_NAMES
MIN_FLOOR = 0.1
BASE_GRID = (0.0, 0.5, 1.0)
RATIOS: tuple[tuple[float, float], ...] = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))
PRIMARY_RATIO = (3.0, 1.0)
N_WORKERS = 16
CHUNK_SIZE = 512

# Frozen Stage 1 oscillator winners and macro/on-chain window overrides,
# duplicated verbatim from run_full_recalibration_fixed_index.py /
# run_ablation_best_round_full_resolution.py per this repo's self-contained
# script convention. SdcaOscillatorSpec()'s bare constructor defaults
# (rsi_length=14, rs_eth_window=90, ...) are generic library defaults, NOT
# these validated periods -- omitting this override (as this script's first
# version did) silently builds rs_eth/weekly_monthly_rsi/weekly_monthly_macd
# extra_z against the wrong oscillator periods, and every macro/on-chain
# extra (dxy, the four on-chain series, fear_greed) against the wrong
# rolling-z window (shared 90-day default instead of each series' own
# Stage-1-searched period). Fixed before Phase 1's result was committed.
STAGE1_OSCILLATORS = SdcaOscillatorSpec(
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
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}


def load_inputs():
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
        trend_window=STAGE1_OSCILLATORS.power_law_trend_window,
    ).to_list()

    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=STAGE1_OSCILLATORS,
        extra_windows=EXTRA_WINDOWS,
    )
    missing = [n for n in EXTRA_SEARCH_NAMES if n not in extra_z]
    if missing:
        raise SystemExit(f"missing extra_z for: {missing} -- have {sorted(extra_z)}")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    return dates, power_law_z, extra_z, long_windows, medium_windows


def chunked(iterable, size):
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, size))
        if not batch:
            return
        yield batch


def run_parallel_scan(dates, power_law_z, extra_z, long_windows, medium_windows, names, extra_grid, pl_grid):
    all_combos = [
        (pl_val, combo) for pl_val in pl_grid for combo in itertools.product(extra_grid, repeat=len(names))
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
    return results


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


def main() -> None:
    dates, power_law_z, extra_z, long_windows, medium_windows = load_inputs()
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} bars)")
    print(f"search pool (N={len(EXTRA_SEARCH_NAMES) + 1}, incl. power_law): {list(EXTRA_SEARCH_NAMES)}")

    extra_grid = _floor_candidates(BASE_GRID, MIN_FLOOR)
    pl_grid = _floor_candidates(BASE_GRID, MIN_FLOOR)
    print(f"floored grid (min_weight_floor={MIN_FLOOR}): {extra_grid}")

    print("\n=== Exhaustive floored pass: 3-point grid, all ratios reused ===")
    results = run_parallel_scan(
        dates, power_law_z, extra_z, long_windows, medium_windows, EXTRA_SEARCH_NAMES, extra_grid, pl_grid
    )

    primary_weights, primary_obj = best_for_ratio(results, EXTRA_SEARCH_NAMES, *PRIMARY_RATIO)
    primary_weights_dict = primary_weights.model_dump()
    print(f"\nprimary winner (ratio {PRIMARY_RATIO[0]:g}:{PRIMARY_RATIO[1]:g}): {primary_weights_dict}")
    print(f"primary objective: {primary_obj:.3f}")

    all_extras_floored = all(
        primary_weights_dict[name] >= MIN_FLOOR - 1e-9 for name in EXTRA_SEARCH_NAMES
    )
    print(f"every extra indicator >= floor ({MIN_FLOOR}): {all_extras_floored}")
    print(f"power_law weight: {primary_weights_dict['power_law']} (>= floor: {primary_weights_dict['power_law'] >= MIN_FLOOR - 1e-9})")

    print("\n=== Ratio sensitivity (2:1, 3:1, 5:1), reusing precomputed scores ===")
    ratio_results = {}
    for lw, mw in RATIOS:
        weights, obj = best_for_ratio(results, EXTRA_SEARCH_NAMES, lw, mw)
        key = f"{lw:g}:{mw:g}"
        ratio_results[key] = {"weights": weights.model_dump(), "objective": obj}
        print(f"  {key}: objective={obj:.3f} weights={weights.model_dump()}")

    out = {
        "search_pool": ["power_law", *EXTRA_SEARCH_NAMES],
        "grid": list(extra_grid),
        "min_weight_floor": MIN_FLOOR,
        "primary_winner_3_1": primary_weights_dict,
        "primary_objective": primary_obj,
        "all_extras_at_or_above_floor": all_extras_floored,
        "ratio_sensitivity": ratio_results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
