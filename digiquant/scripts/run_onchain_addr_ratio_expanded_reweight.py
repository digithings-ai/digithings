#!/usr/bin/env python3
"""Stage 2 of the Phase B indicator-addition playbook: combined reweight
across the validated baseline, the 4 Bitview on-chain series, and the new
CoinMetrics active-address-ratio series (``onchain_addr_ratio``).

Extends ``run_onchain_expanded_reweight.py``'s diagnostic 7-dimension mix
(power_law + m2 + dxy + 4 on-chain ratios) with ``onchain_addr_ratio`` at
its Stage 1 winning window (365d, see ``run_onchain_addr_ratio_solo_search.py``),
per Phase B step 3: a candidate only clears this gate if it earns a weight
*strictly above* the 0.1 floor in the winning mix -- a candidate pinned at
the floor is contributing no signal beyond what the floor forces.

Grid: a single 5-point pass (0.1, 0.325, 0.55, 0.775, 1.0) across all 8
dimensions -- 5**8 = 390,625 evaluations, the same order of magnitude as the
8-dimension price-oscillator run already completed and cited in
``run_onchain_expanded_reweight.py``.

This produces a diagnostic index only -- does not touch settings.json or
RESEARCH_STATE.md. Report the full table to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    python scripts/run_onchain_addr_ratio_expanded_reweight.py
"""

from __future__ import annotations

import time
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    onchain_addr_ratio_z,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    optimize_stage_a_weights_combined,
    risk_from_weighted_z,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Winning windows from the Stage 1 solo searches
# (run_onchain_solo_search.py, run_onchain_addr_ratio_solo_search.py).
ONCHAIN_WINDOWS = {
    "onchain_mvrv": 1095,
    "onchain_asopr": 1095,
    "onchain_puell": 1095,
    "onchain_rhodl": 730,
    "onchain_addr_ratio": 365,
}

SEARCH_NAMES = (
    "m2", "dxy", "onchain_mvrv", "onchain_asopr", "onchain_puell", "onchain_rhodl",
    "onchain_addr_ratio",
)

SEARCH_GRID = (0.1, 0.325, 0.55, 0.775, 1.0)
FLOOR = 0.1
MAX_WEIGHT = 1.0


def _print_score(label: str, score: CombinedCycleOverlapScore) -> None:
    print(
        f"  {label}: long={score.long.objective:.2f} "
        f"medium={score.medium.objective:.2f} combined={score.objective:.2f} "
        f"(ratio {score.long_weight:g}:{score.medium_weight:g})"
    )


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)
    print(f"extras available: {sorted(base_extra_z)}\n")

    onchain_ratio_z_fns = {
        "onchain_mvrv": onchain_mvrv_z,
        "onchain_asopr": onchain_asopr_z,
        "onchain_puell": onchain_puell_z,
        "onchain_rhodl": onchain_rhodl_z,
    }
    extra_z = dict(base_extra_z)
    for name, z_fn in onchain_ratio_z_fns.items():
        src_dates = getattr(sources, f"{name}_dates")
        src_values = getattr(sources, f"{name}_values")
        if src_dates is None:
            raise SystemExit(f"no {name} source found -- expected all 4 on-chain series present")
        extra_z[name] = z_fn(date_s, src_dates, src_values, window=ONCHAIN_WINDOWS[name]).to_list()

    if sources.onchain_addr_ratio_dates is None:
        raise SystemExit("no onchain_addr_ratio source found")
    extra_z["onchain_addr_ratio"] = onchain_addr_ratio_z(
        date_s, price_s, sources.onchain_addr_ratio_dates, sources.onchain_addr_ratio_values,
        window=ONCHAIN_WINDOWS["onchain_addr_ratio"],
    ).to_list()

    missing = [n for n in SEARCH_NAMES if n not in extra_z]
    if missing:
        raise SystemExit(f"missing required extras for search_names: {missing}")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    # Validated baseline (power_law=1.0, m2=0.5, dxy=0.5) as the reference point.
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
        f"{'reweighted (+addr_ratio)':<32} {result.score.long.objective:>8.2f} "
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
