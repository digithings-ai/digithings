#!/usr/bin/env python3
"""Stage 2 of the Phase B indicator-addition playbook: combined reweight of
the validated baseline (power_law/m2/dxy) with ``fast_crash_vol`` added.

``fast_crash_vol`` cleared Stage 1 solo validation
(``run_fast_crash_indicator_search.py``): best window=30/min_samples=15,
combined objective 55.09 vs. a 0.00 noise baseline. Per Phase B step 3, a
candidate only clears this gate if it earns a weight *strictly above* the
0.1 floor in the winning mix -- a candidate pinned at the floor is
contributing no signal beyond what the floor forces.

This produces a diagnostic index only -- does not touch settings.json or
RESEARCH_STATE.md. Report the full table to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    uv run python scripts/run_fast_crash_indicator_reweight.py
"""

from __future__ import annotations

import time
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, fast_crash_vol_z
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    optimize_stage_a_weights_combined,
    risk_from_weighted_z,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Stage 1 winning window (run_fast_crash_indicator_search.py).
FAST_CRASH_VOL_WINDOW = 30
FAST_CRASH_VOL_MIN_SAMPLES = 15

SEARCH_NAMES = ("m2", "dxy", "fast_crash_vol")
SEARCH_GRID = (0.1, 0.325, 0.55, 0.775, 1.0)
FLOOR = 0.1
MAX_WEIGHT = 1.0


def _print_score(label: str, score: CombinedCycleOverlapScore) -> None:
    print(
        f"  {label}: long={score.long.objective:.2f} "
        f"medium={score.medium.objective:.2f} combined={score.objective:.2f} "
        f"(ratio {score.long_weight:g}:{score.medium_weight:g})"
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    extra_z = dict(load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir)))
    extra_z["fast_crash_vol"] = fast_crash_vol_z(
        date_s, price_s, window=FAST_CRASH_VOL_WINDOW, min_samples=FAST_CRASH_VOL_MIN_SAMPLES
    ).to_list()
    print(f"extras available: {sorted(extra_z)}\n")

    missing = [n for n in SEARCH_NAMES if n not in extra_z]
    if missing:
        raise SystemExit(f"missing required extras for search_names: {missing}")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    # True validated baseline (power_law=1.0, m2=0.5, dxy=0.5) as the reference point.
    baseline_weights = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
    baseline_risk = risk_from_weighted_z(dates, power_law_z, extra_z, baseline_weights)
    baseline_score = combined_cycle_overlap_score(
        dates, baseline_risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    )
    print("=== Reference: validated baseline (power_law=1.0, m2=0.5, dxy=0.5) ===\n")
    print(f"  weights: {baseline_weights.model_dump()}")
    _print_score("score", baseline_score)
    print()

    print(f"=== Stage 2 reweight: floor=0.1/max=1.0, grid={SEARCH_GRID} ===\n")
    t0 = time.monotonic()
    result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=power_law_z,
        extra_z=extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=SEARCH_NAMES,
        grid=SEARCH_GRID,
        power_law_grid=SEARCH_GRID,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=FLOOR,
    )
    elapsed = time.monotonic() - t0
    print(f"  evaluated: {result.num_evaluations} combinations in {elapsed:.1f}s")
    print(f"  weights: {result.weights.model_dump()}")
    _print_score("score", result.score)
    print()

    print("=== Summary ===\n")
    header = f"{'config':<32} {'long':>8} {'medium':>8} {'combined':>10}"
    print(header)
    print("-" * len(header))
    print(
        f"{'validated baseline (3wt)':<32} {baseline_score.long.objective:>8.2f} "
        f"{baseline_score.medium.objective:>8.2f} {baseline_score.objective:>10.2f}"
    )
    print(
        f"{'reweighted (+fast_crash_vol)':<32} {result.score.long.objective:>8.2f} "
        f"{result.score.medium.objective:>8.2f} {result.score.objective:>10.2f}"
    )
    print()

    print("=== Floor check (Phase B step 3: weight must exceed 0.1 to count as real signal) ===\n")
    final_weights = result.weights.model_dump()
    for name in ("power_law",) + SEARCH_NAMES:
        w = final_weights[name]
        note = "at floor -- no real signal beyond diversification" if abs(w - FLOOR) < 1e-9 else ""
        print(f"  {name:<16} {w:.3f}  {note}")


if __name__ == "__main__":
    run()
