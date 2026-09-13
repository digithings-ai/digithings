#!/usr/bin/env python3
"""Stage 1 of the Phase B indicator-addition playbook: solo-validate the
fast-reacting crash-detection candidate (``fast_crash_vol``).

Every extra indicator in the standing composite (power_law/m2/dxy, plus the
research-only price oscillators) is a slow/structural or macro read that lags
a sharp price move by construction. ``fast_crash_vol`` is a short-window
realized volatility of daily log returns instead (see
``indicator_catalog.fast_crash_vol_z`` docstring), added this session to test
whether a genuinely fast-reacting signal can force the SDCA composite to
de-risk quickly enough to keep fold 1's OOS drawdown (COVID crash,
2019-07-01..2021-11-20) within Chris's 20-30% target -- every curve-shape
variant tried against the existing slow-only composite failed on this fold
specifically because a buy/sell curve can only react to what the composite
already sees.

Per the Phase B procedure, before this candidate is allowed anywhere near the
aggregate composite it must clear a solo-validation gate: soloed (weight=1,
every other indicator at 0) and scored against the same combined long+medium
cycle-overlap objective the rest of the composite is tuned against
(``stage_a.combined_cycle_overlap_score`` via
``weight_search.search_oscillator_periods_by_cycle_overlap``), it must beat a
constant-zero noise baseline. This mirrors
``run_onchain_addr_ratio_solo_search.py``'s pattern, but simpler:
``fast_crash_vol_z`` is derived purely from ``btc_price`` (no external source
series needed), so this grids over the raw realized-vol lookback window only,
holding the z-normalization stage at its default (``DEFAULT_ROLLING_WINDOW``).

This produces a go/no-go signal only. It does not touch settings.json,
RESEARCH_STATE.md, or any other indicator's weight -- per the playbook, that
requires re-running Stage 2 (floor-diversified reweight) with the surviving
candidate added and Chris's explicit accept.

Usage:
    uv run python scripts/run_fast_crash_indicator_search.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    fast_crash_vol_z,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Raw realized-vol lookback candidates -- short on purpose (the fast-reacting
# part of the signal); min_samples scales with window the same way the
# indicator's own default (14/7, i.e. window/2) does.
WINDOW_CANDIDATES = [
    {"window": w, "min_samples": max(3, w // 2)}
    for w in (7, 10, 14, 21, 30, 45)
]


def _noise_baseline_objective(
    dates: list,
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float,
    medium_weight: float,
) -> float:
    """Objective for a constant-zero indicator -- the bar this search must clear."""
    zeros = [0.0] * len(dates)
    dummy_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)
    risk = risk_from_weighted_z(dates, zeros, {"m2": zeros}, dummy_weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    ).objective


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
    default_power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    print(f"extras available: {sorted(base_extra_z)}\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    def compute_z(p: dict[str, int]) -> list[float | None]:
        return fast_crash_vol_z(
            date_s, price_s, window=p["window"], min_samples=p["min_samples"]
        ).to_list()

    print("=== Stage 1: fast_crash_vol solo period search (combined objective) ===\n")
    result = search_oscillator_periods_by_cycle_overlap(
        dates,
        indicator_name="fast_crash_vol",
        param_candidates=WINDOW_CANDIDATES,
        compute_indicator_z=compute_z,
        base_power_law_z=default_power_law_z,
        base_extra_z=base_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        long_weight=long_weight,
        medium_weight=medium_weight,
    )
    beats_noise = result.best.score.objective > noise_objective
    status = "OK -- clears noise baseline" if beats_noise else "DROP (<= noise baseline)"
    print(f"[fast_crash_vol] {status}")
    print(f"  best params: {result.best.params}")
    _print_score("score", result.best.score)
    print(f"  noise baseline: {noise_objective:.2f}\n")

    print("all candidates:")
    for candidate in sorted(result.all_scores, key=lambda s: s.score.objective, reverse=True):
        marker = " <-- best" if candidate.params == result.best.params else ""
        print(
            f"  window={candidate.params['window']:>3} min_samples={candidate.params['min_samples']:>3}  "
            f"objective={candidate.score.objective:>7.2f}{marker}"
        )
    print()

    print("=== Stage 1 summary ===")
    print(f"  fast_crash_vol: {'PASS' if beats_noise else 'DROP'}")


if __name__ == "__main__":
    run()
