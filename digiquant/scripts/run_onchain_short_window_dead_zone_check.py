#!/usr/bin/env python3
"""Follow-up to ``run_onchain_risk_floor_diagnostic.py``'s root-cause finding:
``onchain_mvrv``/``onchain_rhodl``'s long trailing windows (1095d/730d) keep
fold 1's (2019-07-01..2021-11-20, the COVID-crash OOS window) composite risk
floor above the frozen curve's ``buy_knee_risk`` for the entire window,
"remembering" the 2017 bubble and 2019 rally well past when they should have
rolled off -- a windowing/staleness bug, not a signal-direction bug.

This sweeps much shorter trailing windows for both indicators and checks,
cheaply (no curve search, no walk-forward -- just the risk-index arithmetic),
whether fold 1's composite risk actually dips back below the buy knee at the
COVID low once the stale 2017/2019 history has rolled off. A fast go/no-go
before spending a full Stage 2b/3/4 pipeline run on this.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_onchain_short_window_dead_zone_check.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import apply_calendar_delay
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    onchain_mvrv_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_extra_z
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

TICKER = "BTC-USD"
SIGNAL_DELAY_DAYS = 3

# Same weights as run_onchain_risk_floor_diagnostic.py's rejected mix --
# only the mvrv/rhodl trailing windows vary in this sweep.
WEIGHTS = SdcaCompositeWeights(power_law=0.325, m2=0.1, dxy=0.1, onchain_mvrv=1.0, onchain_rhodl=1.0)

# Original (rejected) windows plus a sweep of shorter candidates.
WINDOW_GRID = [1095, 730, 545, 365, 270, 180, 120, 90]

BUY_KNEE_RISK = 29.7094
SELL_KNEE_RISK = 71.5304

FOLD1_START, FOLD1_END = date(2019, 7, 1), date(2021, 11, 20)
COVID_START, COVID_END = date(2020, 3, 1), date(2020, 3, 31)


def build_frame(cache_dir: Path, mvrv_window: int, rhodl_window: int) -> pl.DataFrame:
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
    extra_z: dict[str, list[float | None]] = load_sdca_extra_z(
        dates.to_list(), price.to_list(), data_path=None, data_dir=cache_dir,
    )
    if sources.onchain_mvrv_dates is None or sources.onchain_rhodl_dates is None:
        raise SystemExit("missing onchain_mvrv/onchain_rhodl source data")
    extra_z["onchain_mvrv"] = onchain_mvrv_z(
        dates, sources.onchain_mvrv_dates, sources.onchain_mvrv_values, window=mvrv_window,
    ).to_list()
    extra_z["onchain_rhodl"] = onchain_rhodl_z(
        dates, sources.onchain_rhodl_dates, sources.onchain_rhodl_values, window=rhodl_window,
    ).to_list()

    risk = risk_from_weighted_z(dates.to_list(), power_law_z, extra_z, WEIGHTS)
    return pl.DataFrame({"date": dates, "price": price, "risk": pl.Series(risk, dtype=pl.Float64)})


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    print(f"frozen weights: {WEIGHTS.model_dump()}")
    print(f"frozen dead zone: buy_knee_risk={BUY_KNEE_RISK}  sell_knee_risk={SELL_KNEE_RISK}\n")
    print("=== fold-1 OOS (2019-07-01..2021-11-20) composite risk vs buy_knee_risk, by mvrv=rhodl window ===\n")

    for window in WINDOW_GRID:
        frame = build_frame(cache_dir, mvrv_window=window, rhodl_window=window)
        fold1 = frame.filter((pl.col("date") >= FOLD1_START) & (pl.col("date") <= FOLD1_END))
        covid = frame.filter((pl.col("date") >= COVID_START) & (pl.col("date") <= COVID_END))
        pct_below = 100.0 * (fold1["risk"] < BUY_KNEE_RISK).sum() / fold1.height
        null_pct = 100.0 * fold1["risk"].null_count() / fold1.height
        print(
            f"window={window:5d}d  fold1 risk mean={fold1['risk'].mean():6.2f}  min={fold1['risk'].min():6.2f}  "
            f"pct_time_below_buy_knee={pct_below:5.1f}%  null%={null_pct:4.1f}  "
            f"covid_low_risk={covid['risk'].min():6.2f}"
        )

    print(
        "\nGo/no-go: any window where pct_time_below_buy_knee > 0 at the COVID low means the dead-zone "
        "actually breaks -- worth spending a full Stage 2b/3/4 pipeline run on. If every window still "
        "shows 0% (or near-0%), the staleness isn't the (whole) story and this lead doesn't pan out."
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
