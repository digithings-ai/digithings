#!/usr/bin/env python3
"""Sweep ``compute_composite_risk``'s existing (unused) ``rolling_window`` knob
on the frozen validated baseline, to see if it fixes allocation saturation.

Context: Chris flagged the validated baseline's allocation-of-equity curve
pins near 97-99% from 2024 on and barely reacts, even through the 2022 bear
market. A curve-reshuffle search (run_allocation_responsiveness_search.py /
run_allocation_responsiveness_walk_forward.py) tried fixing this by reshaping
the buy/sell curve and failed OOS validation on all 3 candidates tested.

Investigation of composite_risk.py found the likely real mechanism already
has an existing, unused fix: compute_composite_risk() takes an optional
``rolling_window`` (default None) that re-normalizes the weighted-blend
z-score against a *trailing* window via causal_rolling_z, instead of the
plain whole-history clip currently used everywhere (build_risk_index's
``composite_rolling_window`` forwards to it, but every call site -- the
baseline's load_frozen_index, stage_a.py -- passes None). So "expensive"
essentially can't be reached again once the composite has drifted rich-of-
mean for years, because the implicit scale is dragged by all of 2014-2022.

This script freezes the validated baseline's weights (power_law=1.0,
m2=0.5, dxy=0.5) and published curve, and sweeps composite_rolling_window
over a few multi-year widths -- reusing build_risk_index directly (bypassing
load_frozen_index, which doesn't expose this param) rather than editing any
production file. No new signal-processing code: this is a parameter sweep
over infrastructure that already exists.

Diagnostic only (curve_simulator go/no-go via run_backtest). Not touching
RESEARCH_STATE.md/settings.json -- any width that un-saturates allocation
without torching return still needs a full walk-forward OOS run (Stage 4)
before it's a baseline proposal, same standing gate as every other trial.

Usage:
    uv run python -m scripts.run_composite_rolling_window_sweep
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.curve_optimize import apply_calendar_delay, published_curve_shape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, build_extra_indicators
from digiquant.strategies.sdca.optimize import drop_extras_missing_sources, load_sdca_extra_sources
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

VALIDATED_BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
TICKER = "BTC-USD"
SIGNAL_DELAY_DAYS = 3
TRADE_START = "2018-01-01"
DRAWDOWN_EPSILON = 0.5
BULL_PROXIMITY_PCT = 25.0

# Multi-year windows only -- narrow enough to actually re-center against a
# recent regime, wide enough to still span a meaningful chunk of a ~4y cycle
# rather than collapsing into short-horizon noise.
ROLLING_WINDOWS = [None, 365, 730, 1095, 1460]


def build_frozen_index(cache_dir: Path, *, composite_rolling_window: int | None):
    ohlcv = load_cached(TICKER, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        raise FileNotFoundError(f"no cached {TICKER} under {cache_dir}")
    ohlcv = apply_calendar_delay(ohlcv, SIGNAL_DELAY_DAYS)
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    dates = ohlcv[ts_col]
    if dates.dtype != pl.Date:
        dates = dates.cast(pl.Date)
    sources = load_sdca_extra_sources(cache_dir)
    resolved = drop_extras_missing_sources(VALIDATED_BASELINE_WEIGHTS, sources)
    extras = build_extra_indicators(dates, ohlcv["close"], resolved, sources, oscillators=None)
    index = build_risk_index(
        dates,
        ohlcv["close"],
        BtcPowerLawRiskModel(load_coefficients()),
        extra_indicators=extras or None,
        power_law_weight=resolved.power_law,
        composite_rolling_window=composite_rolling_window,
    )
    cutoff = date.fromisoformat(TRADE_START)
    window = index.filter(pl.col("date") >= cutoff)
    if window.is_empty():
        raise ValueError(f"frozen index empty after trade_start={TRADE_START}")
    return window["date"], window["price"], window["risk"], resolved


def allocated_pct_series(frame: pl.DataFrame) -> list[float]:
    cash = frame["cash"].to_list()
    portfolio = frame["portfolio_value"].to_list()
    return [100.0 * (pv - c) / pv if pv > 0 else 0.0 for c, pv in zip(cash, portfolio, strict=True)]


def trailing_high_proximity_pct(prices: list[float], window: int = 365) -> list[float]:
    out = []
    for i in range(len(prices)):
        start = max(0, i - window + 1)
        peak = max(prices[start : i + 1])
        out.append(100.0 * (peak - prices[i]) / peak)
    return out


def allocation_responsiveness_score(frame: pl.DataFrame, prices: list[float]) -> float:
    alloc = allocated_pct_series(frame)
    proximity = trailing_high_proximity_pct(prices)
    deltas = [abs(alloc[i] - alloc[i - 1]) for i in range(1, len(alloc)) if proximity[i] <= BULL_PROXIMITY_PCT]
    return sum(deltas) / len(deltas) if deltas else 0.0


def year_stats(dates: list, alloc: list[float]) -> dict[int, tuple[float, float, float]]:
    by_year: dict[int, list[float]] = {}
    for d, a in zip(dates, alloc, strict=True):
        by_year.setdefault(d.year, []).append(a)
    return {y: (min(v), max(v), sum(v) / len(v)) for y, v in sorted(by_year.items())}


def run(cache_dir: Path = DEFAULT_CACHE_DIR, initial_cash: float = 1000.0) -> None:
    shape = published_curve_shape()
    curve = AccumDistCurve(shape.to_nodes())

    for rw in ROLLING_WINDOWS:
        dates, prices_s, risk, weights = build_frozen_index(cache_dir, composite_rolling_window=rw)
        prices = prices_s.to_list()
        report, frame = run_backtest(dates, prices_s, risk, curve, initial_cash)
        max_dd = abs(report.dca_max_drawdown_pct) * 100.0
        rar = report.total_return_pct / max(max_dd, DRAWDOWN_EPSILON)
        resp = allocation_responsiveness_score(frame, prices)
        alloc = allocated_pct_series(frame)
        stats = year_stats(dates.to_list(), alloc)

        label = f"rolling_window={rw}" if rw is not None else "rolling_window=None (today's baseline)"
        print(f"=== {label} ===")
        print(
            f"  vs_flat_dca={report.vs_flat_dca_pct:+.2f}%  risk_adjusted_return={rar:.3f}"
            f"  allocation_responsiveness={resp:.3f}  maxDD={max_dd:.1f}%"
        )
        for y, (mn, mx, mean) in stats.items():
            print(f"    {y}: min={mn:5.1f}%  max={mx:5.1f}%  mean={mean:5.1f}%")
        print()

    print(
        "Diagnostic only (curve_simulator/run_backtest). Not touching RESEARCH_STATE.md/settings.json -- "
        "any window that un-saturates allocation without torching return still needs the full Stage-4 "
        "walk-forward OOS gate before it's a baseline proposal."
    )


if __name__ == "__main__":
    run()
