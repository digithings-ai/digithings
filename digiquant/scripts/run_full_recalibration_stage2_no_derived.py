#!/usr/bin/env python3
"""Full 11-indicator SDCA recalibration, Stage 2 variant: exclude the derived
weekly_monthly_rsi/weekly_monthly_macd confluence indicators from the search.

Follow-up to run_full_recalibration_stage2/4.py and the capped-max-weight
variant, both of which showed that whenever weekly_monthly_rsi/macd are
available to the floor=0.1 aggregate reweight, the optimizer concentrates
weight into them (1.0 uncapped, 0.5 capped) and the result fails Stage 4 OOS
either way -- their in-sample edge doesn't generalize. This variant removes
both from search_names entirely, so the floor/cap search must diversify
only across the 7 remaining non-derived extras (rs_eth, weekly_rsi,
weekly_macd, sma_band, monthly_rsi, monthly_macd).

Usage:
    uv run python -m scripts.run_full_recalibration_stage2_no_derived
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import rs_eth_confluence_z
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
)
from digiquant.strategies.sdca.stage_a import (
    optimize_stage_a_weights_combined,
    optimize_stage_a_weights_combined_multi_ratio,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

STAGE1_WINNERS = {
    "power_law": {"trend_window": 180},
    "weekly_rsi": {"weekly_length": 5, "daily_length": 5},
    "weekly_macd": {"weekly_fast": 16, "weekly_slow": 35, "daily_fast": 12, "daily_slow": 26},
    "monthly_rsi": {"monthly_length": 2, "daily_length": 14},
    "monthly_macd": {"monthly_fast": 4, "monthly_slow": 9, "daily_fast": 12, "daily_slow": 26},
    "sma_band": {"slow_window": 120, "fast_window": 30},
    "rs_eth": {"slow_window": 60, "fast_window": 20},
}

COARSE_GRID = (0.1, 0.55, 1.0)


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    print("=== Stage 2 (no derived): Aggregate reweight, weekly_monthly_* excluded ===\n")
    print("Computing Stage 1 winner z-series...\n")

    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"],
        **STAGE1_WINNERS["power_law"]
    )
    weekly_rsi_z = rsi_confluence_z(date_s, price_s, **STAGE1_WINNERS["weekly_rsi"])
    weekly_macd_z = macd_confluence_z(date_s, price_s, **STAGE1_WINNERS["weekly_macd"])
    monthly_rsi_z = monthly_rsi_confluence_z(date_s, price_s, **STAGE1_WINNERS["monthly_rsi"])
    monthly_macd_z = monthly_macd_confluence_z(date_s, price_s, **STAGE1_WINNERS["monthly_macd"])
    sma_band_z = sma_band_confluence_z(date_s, price_s, **STAGE1_WINNERS["sma_band"])

    eth_available = sources.eth_dates is not None and sources.eth_close is not None
    if eth_available:
        rs_eth_z = rs_eth_confluence_z(
            date_s, price_s, sources.eth_dates, sources.eth_close, **STAGE1_WINNERS["rs_eth"]
        )
    else:
        rs_eth_z = None

    extra_z = dict(base_extra_z)
    extra_z["weekly_rsi"] = weekly_rsi_z.to_list()
    extra_z["weekly_macd"] = weekly_macd_z.to_list()
    extra_z["monthly_rsi"] = monthly_rsi_z.to_list()
    extra_z["monthly_macd"] = monthly_macd_z.to_list()
    extra_z["sma_band"] = sma_band_z.to_list()
    if rs_eth_z is not None:
        extra_z["rs_eth"] = rs_eth_z.to_list()

    search_names = (
        "weekly_rsi", "weekly_macd", "monthly_rsi", "monthly_macd", "sma_band", "rs_eth"
    ) if eth_available else (
        "weekly_rsi", "weekly_macd", "monthly_rsi", "monthly_macd", "sma_band"
    )

    print(f"Search indicators (weekly_monthly_rsi/macd excluded): {search_names}\n")

    print("Running COARSE grid search (3-point: 0.1, 0.55, 1.0)...\n")
    coarse_result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=power_law_z.to_list(),
        extra_z=extra_z,
        search_names=search_names,
        grid=COARSE_GRID,
        power_law_grid=COARSE_GRID,
        long_windows=long_windows,
        medium_windows=medium_windows,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=0.1,
    )

    coarse_winner = coarse_result.weights.model_dump()
    print(f"Coarse winner: {coarse_winner}")
    print(f"  Combined score: {coarse_result.score.objective:.2f}")
    print(f"  Long: {coarse_result.score.long.objective:.2f}, Medium: {coarse_result.score.medium.objective:.2f}\n")

    print("=== Sensitivity check at different long:medium ratios ===\n")
    ratios_to_check = [(2.0, 1.0), (3.0, 1.0), (5.0, 1.0)]
    multi_results = optimize_stage_a_weights_combined_multi_ratio(
        dates,
        power_law_z=power_law_z.to_list(),
        extra_z=extra_z,
        search_names=search_names,
        grid=COARSE_GRID,
        power_law_grid=COARSE_GRID,
        long_windows=long_windows,
        medium_windows=medium_windows,
        ratios=ratios_to_check,
        min_weight_floor=0.1,
    )

    for ratio_key, result in multi_results.items():
        ratio_long, ratio_medium = ratio_key
        print(f"Ratio {ratio_long:.0f}:{ratio_medium:.0f}")
        w = result.weights.model_dump()
        print(f"  weights: {w}")
        print(f"  combined: {result.score.objective:.2f}")
        print(f"  long: {result.score.long.objective:.2f}, medium: {result.score.medium.objective:.2f}\n")

    print("\n=== Stage 2 (no derived) Complete ===")
    print("Winner weights ready for Stage 3 (curve optimization) + Stage 4 (OOS gate).")


if __name__ == "__main__":
    run()
