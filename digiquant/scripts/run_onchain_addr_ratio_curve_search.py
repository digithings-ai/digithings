#!/usr/bin/env python3
"""Stage 3 of the Phase B indicator-addition playbook: buy/sell curve refit
against the Stage 2 winning index (validated baseline + 4 Bitview on-chain
series + the new CoinMetrics ``onchain_addr_ratio``).

Per the playbook, curve fitting must never reuse an old shape against a
changed index ("index-then-curve"). This freezes a fresh index built from
``run_onchain_addr_ratio_expanded_reweight.py``'s Stage 2 winning weights and
per-indicator windows, then runs ``search_wide_knee_curve`` (independent
buy/sell knees, rates, curvature) exactly as ``run_published_curve_search``
does for the published ``settings.json`` mix.

This does NOT reuse ``curve_optimize.load_frozen_index`` /
``build_extra_indicators`` directly: those only accept one shared ``window``
across every onchain ratio indicator (``onchain_mvrv`` / ``onchain_asopr`` /
``onchain_puell`` / ``onchain_rhodl`` / ``onchain_addr_ratio``), but Stage 1
found each series wants a different window (1095/1095/1095/730/365 days).
Stage 2's reweight script already worked around this the same way -- building
each series' z manually with its own winning window via
``stage_a.risk_from_weighted_z`` instead of the shared-window path. This
script mirrors that, then reproduces ``load_frozen_index``'s delayed-cache +
trade-start slicing manually so the curve search sees the same realistic
(signal-delayed, post-2018) trading window ``run_published_curve_search``
uses.

This produces a diagnostic curve shape only -- does not touch settings.json
or RESEARCH_STATE.md. Report the full table to Chris for explicit accept
first, per the standing playbook gate.

Usage:
    python scripts/run_onchain_addr_ratio_curve_search.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import apply_calendar_delay, search_wide_knee_curve
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    onchain_addr_ratio_z,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_extra_z
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

TICKER = "BTC-USD"
SIGNAL_DELAY_DAYS = 3
TRADE_START = "2018-01-01"

# Stage 2 winner (run_onchain_addr_ratio_expanded_reweight.py).
STAGE2_WEIGHTS = SdcaCompositeWeights(
    power_law=0.325,
    m2=0.1,
    dxy=0.1,
    onchain_mvrv=1.0,
    onchain_asopr=0.1,
    onchain_puell=0.1,
    onchain_rhodl=1.0,
    onchain_addr_ratio=1.0,
)

# Stage 1 winning windows (run_onchain_solo_search.py, run_onchain_addr_ratio_solo_search.py).
ONCHAIN_WINDOWS = {
    "onchain_mvrv": 1095,
    "onchain_asopr": 1095,
    "onchain_puell": 1095,
    "onchain_rhodl": 730,
    "onchain_addr_ratio": 365,
}

ONCHAIN_Z_FNS = {
    "onchain_mvrv": onchain_mvrv_z,
    "onchain_asopr": onchain_asopr_z,
    "onchain_puell": onchain_puell_z,
    "onchain_rhodl": onchain_rhodl_z,
}


def build_frozen_index(cache_dir: Path) -> tuple[pl.Series, pl.Series, pl.Series]:
    ohlcv = load_cached(TICKER, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        raise FileNotFoundError(f"no cached {TICKER} under {cache_dir}")
    ohlcv = apply_calendar_delay(ohlcv, SIGNAL_DELAY_DAYS)
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    dates = ohlcv[ts_col]
    if dates.dtype != pl.Date:
        dates = dates.cast(pl.Date)
    price = ohlcv["close"]

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(dates)
    power_law_z = power_law_confluence_z(
        dates, price, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    sources = load_sdca_extra_sources(cache_dir)
    # m2/dxy don't have per-indicator window overrides in this Stage 2 mix
    # (both floor-pinned at 0.1); reuse the standard loader for those, then
    # overwrite the 5 onchain ratio series with their Stage-1-winning windows.
    extra_z: dict[str, list[float | None]] = load_sdca_extra_z(
        dates.to_list(), price.to_list(), data_path=None, data_dir=cache_dir,
    )
    for name, z_fn in ONCHAIN_Z_FNS.items():
        src_dates = getattr(sources, f"{name}_dates")
        src_values = getattr(sources, f"{name}_values")
        if src_dates is None:
            raise SystemExit(f"no {name} source found -- expected all 4 on-chain series present")
        extra_z[name] = z_fn(dates, src_dates, src_values, window=ONCHAIN_WINDOWS[name]).to_list()
    if sources.onchain_addr_ratio_dates is None:
        raise SystemExit("no onchain_addr_ratio source found")
    extra_z["onchain_addr_ratio"] = onchain_addr_ratio_z(
        dates, price, sources.onchain_addr_ratio_dates, sources.onchain_addr_ratio_values,
        window=ONCHAIN_WINDOWS["onchain_addr_ratio"],
    ).to_list()

    risk = risk_from_weighted_z(dates.to_list(), power_law_z, extra_z, STAGE2_WEIGHTS)

    frame = pl.DataFrame({"date": dates, "price": price, "risk": pl.Series(risk, dtype=pl.Float64)})
    cutoff = date.fromisoformat(TRADE_START)
    window = frame.filter(pl.col("date") >= cutoff)
    if window.is_empty():
        raise ValueError(f"frozen index empty after trade_start={TRADE_START}")
    return window["date"], window["price"], window["risk"]


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices, risk = build_frozen_index(cache_dir)
    print(f"frozen index: {dates[0]}..{dates[-1]} ({len(dates)} bars), weights={STAGE2_WEIGHTS.model_dump()}\n")

    print("=== Stage 3: wide-knee curve search on Stage 2 winning index ===\n")
    result = search_wide_knee_curve(
        dates, prices, risk, initial_cash=1000.0, frozen_weights=STAGE2_WEIGHTS,
    )
    print(f"best shape: {result.best.shape.model_dump()}")
    print(f"  total_return_pct={result.best.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.best.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.best.risk_adjusted_return:.3f}")
    print(f"  vs_lump_pct={result.best.vs_lump_pct:.2f}  vs_flat_dca_pct={result.best.vs_flat_dca_pct:.2f}")
    print()
    print("baseline (published btc_optimized shape, same frozen index):")
    print(f"  total_return_pct={result.baseline.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.baseline.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.baseline.risk_adjusted_return:.3f}")
    print(f"  vs_lump_pct={result.baseline.vs_lump_pct:.2f}  vs_flat_dca_pct={result.baseline.vs_flat_dca_pct:.2f}")
    print()
    print(f"evaluated={result.num_evaluations}  feasible={result.num_feasible}")
    print(f"beats_baseline_return={result.beats_baseline_return}  beats_baseline_concentration={result.beats_baseline_concentration}")


if __name__ == "__main__":
    run()
