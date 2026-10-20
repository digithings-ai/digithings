#!/usr/bin/env python3
"""Full 11-indicator SDCA recalibration, Stage 1: per-indicator period search.

Extends ``run_dual_timeframe_composite_search.py`` to include the full current
``EXTRA_INDICATOR_NAMES`` (11 total: power_law, m2, rs_eth, dxy, weekly_rsi,
weekly_macd, sma_band, monthly_rsi, monthly_macd, weekly_monthly_rsi,
weekly_monthly_macd) instead of 9. Following the staged procedure:

Stage 1: For each tunable indicator, solo it and grid its own construction
  periods against the combined long+medium objective. Indicators whose best
  score doesn't clear a noise baseline are dropped before Stage 2.

Usage:
    uv run python -m scripts.run_full_recalibration_stage1
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    rs_eth_confluence_z,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import (
    macd_confluence_z,
    monthly_macd_confluence_z,
    monthly_rsi_confluence_z,
    rsi_confluence_z,
    sma_band_confluence_z,
    weekly_monthly_macd_confluence_z,
    weekly_monthly_rsi_confluence_z,
)
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Same period candidates as run_dual_timeframe_composite_search.py
POWER_LAW_CANDIDATES = [{"trend_window": w} for w in (90, 120, 150, 180, 240, 365)]
WEEKLY_RSI_CANDIDATES = [
    {"weekly_length": w, "daily_length": d}
    for w in (5, 7, 8, 9, 10, 12, 14, 18, 21, 26)
    for d in (5, 7, 9, 10, 14)
]
WEEKLY_MACD_CANDIDATES = [
    {"weekly_fast": wf, "weekly_slow": ws, "daily_fast": df, "daily_slow": ds}
    for wf, ws in ((4, 9), (5, 10), (6, 13), (8, 17), (10, 21), (12, 26), (16, 35))
    for df, ds in ((6, 13), (8, 17), (12, 26))
]
MONTHLY_RSI_CANDIDATES = [
    {"monthly_length": w, "daily_length": d}
    for w in (2, 3, 4, 5, 6, 7, 9, 12, 14, 18)
    for d in (5, 7, 9, 10, 14)
]
MONTHLY_MACD_CANDIDATES = [
    {"monthly_fast": wf, "monthly_slow": ws, "daily_fast": df, "daily_slow": ds}
    for wf, ws in ((3, 6), (4, 9), (5, 10), (6, 13), (8, 17), (12, 26))
    for df, ds in ((6, 13), (8, 17), (12, 26))
]
SMA_BAND_CANDIDATES = [
    {"slow_window": 90, "fast_window": 20},
    {"slow_window": 60, "fast_window": 10},
    {"slow_window": 120, "fast_window": 30},
]
RS_ETH_CANDIDATES = [
    {"slow_window": 90, "fast_window": 30},
    {"slow_window": 90, "fast_window": 45},
    {"slow_window": 60, "fast_window": 20},
]
# New: weekly_monthly variants (full 11-indicator set)
WEEKLY_MONTHLY_RSI_CANDIDATES = [
    {"monthly_length": m, "weekly_length": w}
    for m in (2, 3, 4, 5, 6, 7, 9, 12, 14, 18)
    for w in (5, 7, 8, 9, 10, 12, 14, 18, 21, 26)
]
WEEKLY_MONTHLY_MACD_CANDIDATES = [
    {
        "monthly_fast": mf, "monthly_slow": ms,
        "weekly_fast": wf, "weekly_slow": ws,
    }
    for mf, ms in ((3, 6), (4, 9), (5, 10), (6, 13), (8, 17), (12, 26))
    for wf, ws in ((4, 9), (5, 10), (6, 13), (8, 17), (10, 21), (12, 26), (16, 35))
]


def _noise_baseline_objective(
    dates: list,
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float,
    medium_weight: float,
) -> float:
    """Objective for a constant-zero indicator -- the bar step 1 must clear."""
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
        f"medium={score.medium.objective:.2f} combined={score.objective:.2f}"
    )


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)
    print(f"extras available: {sorted(base_extra_z)}\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    # Compute functions for all tunable indicators
    def compute_power_law_z(p: dict[str, int]) -> list[float | None]:
        return power_law_confluence_z(
            date_s, price_s, rails["low"], rails["median"], rails["high"],
            trend_window=p["trend_window"],
        ).to_list()

    def compute_weekly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return rsi_confluence_z(
            date_s, price_s, weekly_length=p["weekly_length"], daily_length=p["daily_length"],
        ).to_list()

    def compute_weekly_macd_z(p: dict[str, int]) -> list[float | None]:
        return macd_confluence_z(
            date_s, price_s,
            weekly_fast=p["weekly_fast"], weekly_slow=p["weekly_slow"],
            daily_fast=p["daily_fast"], daily_slow=p["daily_slow"],
        ).to_list()

    def compute_monthly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return monthly_rsi_confluence_z(
            date_s, price_s, monthly_length=p["monthly_length"], daily_length=p["daily_length"],
        ).to_list()

    def compute_monthly_macd_z(p: dict[str, int]) -> list[float | None]:
        return monthly_macd_confluence_z(
            date_s, price_s,
            monthly_fast=p["monthly_fast"], monthly_slow=p["monthly_slow"],
            daily_fast=p["daily_fast"], daily_slow=p["daily_slow"],
        ).to_list()

    def compute_sma_band_z(p: dict[str, int]) -> list[float | None]:
        return sma_band_confluence_z(
            date_s, price_s, slow_window=p["slow_window"], fast_window=p["fast_window"],
        ).to_list()

    eth_available = sources.eth_dates is not None and sources.eth_close is not None

    def compute_rs_eth_z(p: dict[str, int]) -> list[float | None]:
        return rs_eth_confluence_z(
            date_s, price_s, sources.eth_dates, sources.eth_close,
            slow_window=p["slow_window"], fast_window=p["fast_window"],
        ).to_list()

    def compute_weekly_monthly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return weekly_monthly_rsi_confluence_z(
            date_s, price_s,
            monthly_length=p["monthly_length"], weekly_length=p["weekly_length"],
        ).to_list()

    def compute_weekly_monthly_macd_z(p: dict[str, int]) -> list[float | None]:
        return weekly_monthly_macd_confluence_z(
            date_s, price_s,
            monthly_fast=p["monthly_fast"], monthly_slow=p["monthly_slow"],
            weekly_fast=p["weekly_fast"], weekly_slow=p["weekly_slow"],
        ).to_list()

    # Full 11-indicator tunable list (including weekly_monthly variants)
    tunable = [
        ("power_law", POWER_LAW_CANDIDATES, compute_power_law_z),
        ("weekly_rsi", WEEKLY_RSI_CANDIDATES, compute_weekly_rsi_z),
        ("weekly_macd", WEEKLY_MACD_CANDIDATES, compute_weekly_macd_z),
        ("monthly_rsi", MONTHLY_RSI_CANDIDATES, compute_monthly_rsi_z),
        ("monthly_macd", MONTHLY_MACD_CANDIDATES, compute_monthly_macd_z),
        ("sma_band", SMA_BAND_CANDIDATES, compute_sma_band_z),
        ("rs_eth", RS_ETH_CANDIDATES, compute_rs_eth_z if eth_available else None),
        ("weekly_monthly_rsi", WEEKLY_MONTHLY_RSI_CANDIDATES, compute_weekly_monthly_rsi_z),
        ("weekly_monthly_macd", WEEKLY_MONTHLY_MACD_CANDIDATES, compute_weekly_monthly_macd_z),
    ]

    print("=== Stage 1: per-indicator period search (full 11-indicator set) ===\n")
    default_power_law_z = compute_power_law_z({"trend_window": 180})
    best_params: dict[str, dict[str, int]] = {}
    best_scores: dict[str, CombinedCycleOverlapScore] = {}
    surviving: list[str] = []

    for name, candidates, compute_fn in tunable:
        if compute_fn is None:
            print(f"[{name}] SKIPPED -- no ETH data available\n")
            continue
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=name,
            param_candidates=candidates,
            compute_indicator_z=compute_fn,
            base_power_law_z=default_power_law_z,
            base_extra_z=base_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
            long_weight=long_weight,
            medium_weight=medium_weight,
        )
        best_params[name] = dict(result.best.params)
        best_scores[name] = result.best.score
        beats_noise = result.best.score.objective > noise_objective
        if name != "power_law":
            if beats_noise:
                surviving.append(name)
            status = "OK" if beats_noise else "DROP (<= noise baseline)"
        else:
            status = "OK (anchor, never dropped)"
        print(f"[{name}] {status}")
        print(f"  best params: {result.best.params}")
        _print_score("score", result.best.score)
        print()

    print(f"\n=== Stage 1 Results ===")
    print(f"surviving indicators: {sorted(surviving)}")
    print(f"power_law (anchor): {best_params['power_law']}")
    print(f"non-tunable (m2, dxy): included by default\n")
    print("All results ready for Stage 2 (aggregate reweight, floor=0.1).")


if __name__ == "__main__":
    run()
