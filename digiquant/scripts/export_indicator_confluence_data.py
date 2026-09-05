#!/usr/bin/env python3
"""Export per-indicator z-score histories + cycle windows for visualization.

Companion to ``run_dual_timeframe_composite_search.py``: that script finds
each indicator's winning construction periods against the combined
long+medium objective; this script recomputes each indicator's full z-score
history at those winning periods (hardcoded below -- update after a fresh
search re-derives them) alongside BTC price and the long-/medium-term cycle
windows, and dumps one JSON blob for a standalone confluence chart to embed.

Not itself a search or a trial -- purely a data export for the "does this
indicator's extremes line up with the cycle windows" visual check Chris asked
for before deciding whether monthly RSI/MACD are worth pursuing further.

Usage:
    python scripts/export_indicator_confluence_data.py > out.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
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

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Winning periods from run_dual_timeframe_composite_search.py's most recent
# real-data run (2026-09-05, widened weekly + monthly grids). Update these
# whenever that script's Stage 2/2b results change.
WINNING_PARAMS: dict[str, dict[str, int]] = {
    "power_law": {"trend_window": 180},
    "weekly_rsi": {"weekly_length": 5, "daily_length": 5},
    "weekly_macd": {"weekly_fast": 16, "weekly_slow": 35, "daily_fast": 12, "daily_slow": 26},
    "sma_band": {"slow_window": 120, "fast_window": 30},
    "rs_eth": {"slow_window": 60, "fast_window": 20},
    # monthly_rsi/monthly_macd filled in by main() from the latest Stage 2b
    # winner once known -- see MONTHLY_PARAMS below.
}

# Stage 2b's latest monthly winners (diagnostic-only indicators).
# monthly_rsi updated 2026-09-05 after widening the grid down to
# monthly_length=2 (RSI's mathematical floor): the winner moved from 3 to 2,
# i.e. it tracked the widened floor rather than settling on an interior
# value -- reinforces rather than resolves the overfit/edge-artifact concern.
# monthly_macd's winner (unchanged) is not at a grid edge.
MONTHLY_PARAMS: dict[str, dict[str, int]] = {
    "monthly_rsi": {"monthly_length": 2, "daily_length": 7},
    "monthly_macd": {"monthly_fast": 4, "monthly_slow": 9, "daily_fast": 12, "daily_slow": 26},
}

# Comparison-only: Chris visually inspected monthly_length=2 in the
# confluence dashboard and found it plausible (it bottoms out on both long-
# and medium-term lows), but asked to also see monthly_length=14 (the
# classic RSI period) since it visually maps long-term-only tops/bottoms,
# like power_law. Its best daily_length (5) is pulled from the widened
# grid's own results, not re-optimized here -- this is not a promotion
# candidate, just a second line for side-by-side visual comparison.
COMPARISON_PARAMS: dict[str, dict[str, int]] = {
    "monthly_rsi_14": {"monthly_length": 14, "daily_length": 5},
}


def _window_json(windows: SdcaCycleWindows) -> list[dict[str, str]]:
    return [
        {"name": w.name, "kind": w.kind.value, "start": w.start.isoformat(), "end": w.end.isoformat()}
        for w in windows.windows
    ]


def export(data_path: Path = DEFAULT_DATA_PATH) -> dict:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)
    eth_available = sources.eth_dates is not None and sources.eth_close is not None

    p = WINNING_PARAMS
    m = MONTHLY_PARAMS
    indicators: dict[str, list[float | None]] = {
        "power_law": power_law_confluence_z(
            date_s, price_s, rails["low"], rails["median"], rails["high"],
            trend_window=p["power_law"]["trend_window"],
        ).to_list(),
        "weekly_rsi": rsi_confluence_z(
            date_s, price_s,
            weekly_length=p["weekly_rsi"]["weekly_length"], daily_length=p["weekly_rsi"]["daily_length"],
        ).to_list(),
        "weekly_macd": macd_confluence_z(
            date_s, price_s,
            weekly_fast=p["weekly_macd"]["weekly_fast"], weekly_slow=p["weekly_macd"]["weekly_slow"],
            daily_fast=p["weekly_macd"]["daily_fast"], daily_slow=p["weekly_macd"]["daily_slow"],
        ).to_list(),
        "monthly_rsi": monthly_rsi_confluence_z(
            date_s, price_s,
            monthly_length=m["monthly_rsi"]["monthly_length"], daily_length=m["monthly_rsi"]["daily_length"],
        ).to_list(),
        "monthly_macd": monthly_macd_confluence_z(
            date_s, price_s,
            monthly_fast=m["monthly_macd"]["monthly_fast"], monthly_slow=m["monthly_macd"]["monthly_slow"],
            daily_fast=m["monthly_macd"]["daily_fast"], daily_slow=m["monthly_macd"]["daily_slow"],
        ).to_list(),
        "monthly_rsi_14": monthly_rsi_confluence_z(
            date_s, price_s,
            monthly_length=COMPARISON_PARAMS["monthly_rsi_14"]["monthly_length"],
            daily_length=COMPARISON_PARAMS["monthly_rsi_14"]["daily_length"],
        ).to_list(),
        "sma_band": sma_band_confluence_z(
            date_s, price_s,
            slow_window=p["sma_band"]["slow_window"], fast_window=p["sma_band"]["fast_window"],
        ).to_list(),
        "m2": base_extra_z.get("m2", []),
        "dxy": base_extra_z.get("dxy", []),
    }
    if eth_available:
        indicators["rs_eth"] = rs_eth_confluence_z(
            date_s, price_s, sources.eth_dates, sources.eth_close,
            slow_window=p["rs_eth"]["slow_window"], fast_window=p["rs_eth"]["fast_window"],
        ).to_list()

    # Equal-weight composite over ALL indicators (Stage 3b in
    # run_dual_timeframe_composite_search.py, 2026-09-05 run): promotes
    # monthly_rsi/monthly_macd from diagnostic-only into a real weighted
    # composite, per Chris's green light after visually validating
    # monthly_rsi=2 in this dashboard. Plotted as composite_z (not the
    # [0,100] risk rescaling) so it sits on the same -3..3 axis as every
    # other indicator here. Combined cycle-overlap score: long=33.25,
    # medium=14.49, combined=114.23 (3:1) vs. the surviving-7 equal-weight
    # baseline's long=27.65, medium=14.19, combined=97.15.
    all9_names = ["m2", "dxy", "weekly_rsi", "weekly_macd", "sma_band", "monthly_rsi", "monthly_macd"]
    if eth_available:
        all9_names.insert(1, "rs_eth")
    eq_weight = 1.0 / (len(all9_names) + 1)
    all9_weighted = [
        IndicatorWeight(name="power_law", z=pl.Series(indicators["power_law"], dtype=pl.Float64), weight=eq_weight)
    ] + [
        IndicatorWeight(name=n, z=pl.Series(indicators[n], dtype=pl.Float64), weight=eq_weight)
        for n in all9_names
    ]
    indicators["equal_weight_all9"] = compute_composite_risk(all9_weighted)["composite_z"].to_list()

    return {
        "dates": [d.isoformat() for d in dates],
        "price": prices,
        "indicators": indicators,
        "params": {
            **p, **m, **COMPARISON_PARAMS,
            "equal_weight_all9": {"n_indicators": len(all9_names) + 1},
        },
        "long_windows": _window_json(SdcaCycleWindows.btc_v1()),
        "medium_windows": _window_json(SdcaCycleWindows.btc_medium_term_v1()),
    }


def main() -> None:
    data = export()

    def _round(v: float | None) -> float | None:
        return v if v is None else round(v, 4)

    data["price"] = [round(v, 2) for v in data["price"]]
    data["indicators"] = {k: [_round(v) for v in vs] for k, vs in data["indicators"].items()}
    json.dump(data, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
