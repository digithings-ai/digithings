#!/usr/bin/env python3
"""Wide-knee curve search on the weekly+monthly confluence index.

"Index then curve" (RESEARCH_STATE.md's standard protocol): the index half
of this pass (``run_weekly_monthly_confluence_composite_search.py``) picked
a frozen composite over the Chris-approved 7-indicator pool -- power_law,
m2, dxy, rs_eth, sma_band, weekly_monthly_rsi, weekly_monthly_macd -- in
place of the older separate weekly_rsi/monthly_rsi/weekly_macd/monthly_macd
legs. This script fits the buy/sell curve against *that* index, not a stale
one: it freezes both the winning weights (Stage 4, 3:1 long:medium) and the
Stage-2 winning construction periods for the two new confluence indicators
(and for sma_band/rs_eth, which were re-optimized against the same combined
objective).

Uses ``search_wide_knee_curve`` -- independent buy/sell knees, curvature>=1
(exponential ramp), sell_max_rate up to 95 -- matching the wide-knee
convention Chris settled on in RESEARCH_STATE.md backlog item 8, purely for
``risk_adjusted_return``.

Diagnostic only, in-sample (curve_simulator evaluator, beats_flat_dca_oos
always false here) -- not a candidate for settings.json without Chris's
explicit review. Do not --push-supabase from this script (it has no such
flag).

Usage:
    uv run python scripts/run_weekly_monthly_confluence_curve_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_SEARCH_BOUNDS,
    load_frozen_index,
    search_wide_knee_curve,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Stage 4 winner (3:1 long:medium, floor-diversified) from
# run_weekly_monthly_confluence_composite_search.py.
WEEKLY_MONTHLY_CONFLUENCE_WEIGHTS = SdcaCompositeWeights(
    power_law=1.0,
    weekly_monthly_rsi=1.0,
    weekly_monthly_macd=1.0,
    m2=0.25,
    dxy=0.25,
    rs_eth=0.25,
    sma_band=0.25,
)

# Stage 2 winning construction periods, same run. power_law_trend_window
# already matches the spec default (180); set explicitly for the record.
WEEKLY_MONTHLY_CONFLUENCE_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    monthly_rsi_length=2,
    rsi_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
    macd_fast=16,
    macd_slow=35,
    sma_band_window=120,
    sma_band_fast_window=30,
    rs_eth_window=60,
    rs_eth_fast_window=20,
)

REFERENCE_RISK_LEVELS = (25.0, 40.0, 60.0, 75.0)


def run(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    *,
    initial_cash: float = 1000.0,
    n_random: int = 4000,
    seed: int = 42,
) -> None:
    dates, prices, risk, weights = load_frozen_index(
        cache_dir,
        weights=WEEKLY_MONTHLY_CONFLUENCE_WEIGHTS,
        oscillators=WEEKLY_MONTHLY_CONFLUENCE_OSCILLATORS,
    )
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights: {weights.model_dump()}")
    print(f"frozen oscillators: {WEEKLY_MONTHLY_CONFLUENCE_OSCILLATORS.model_dump()}")
    print(f"wide-knee search bounds: {WIDE_KNEE_SEARCH_BOUNDS}\n")

    print("=== Wide-knee curve fit (risk_adjusted_return objective, independent buy/sell knees) ===")
    result = search_wide_knee_curve(
        dates,
        prices,
        risk,
        initial_cash=initial_cash,
        frozen_weights=weights,
        n_random=n_random,
        seed=seed,
    )
    winner = result.best.shape
    print(f"  evaluated:            {result.num_evaluations} trials ({result.num_feasible} feasible)")
    print(f"  winning shape:        {winner}")
    print(f"  risk_adjusted_return: {result.best.risk_adjusted_return:.4f}")
    print(f"  total_return_pct:     {result.best.total_return_pct:.2f}%")
    print(f"  max_drawdown_pct:     {result.best.max_drawdown_pct:.2f}%")
    print(f"  vs published baseline risk_adjusted_return: {result.baseline.risk_adjusted_return:.4f}\n")

    print("=== rate_at() vs Chris's reference risk levels ===")
    for r in REFERENCE_RISK_LEVELS:
        print(f"  rate_at({r:5.1f}) = {winner.rate_at(r):+7.3f}")
    print()

    print("=== Trade frequency & cash depletion (full backtest detail) ===")
    from digiquant.strategies.sdca.backtest import run_backtest
    from digiquant.strategies.sdca.curve import AccumDistCurve

    _report, frame = run_backtest(
        dates,
        prices,
        risk,
        AccumDistCurve(winner.to_nodes()),
        initial_cash,
    )
    buy_days = int((frame["rate"] > 0).sum())
    sell_days = int((frame["rate"] < 0).sum())
    no_trade_days = int((frame["rate"] == 0).sum())
    total_days = frame.height
    cash_frac = frame["cash"] / frame["portfolio_value"]
    print(f"  buy_days:       {buy_days}")
    print(f"  sell_days:      {sell_days}")
    print(f"  no_trade_days:  {no_trade_days}")
    print(
        f"  trade_days:     {buy_days + sell_days}/{total_days} "
        f"({100.0 * (buy_days + sell_days) / total_days:.1f}%)"
    )
    print(f"  max_cash_frac:  {cash_frac.max():.4f} (1.0 == fully in cash)")
    print(f"  min_cash_frac:  {cash_frac.min():.4f}")
    print(
        "\nDiagnostic only, in-sample (curve_simulator, beats_flat_dca_oos=False). "
        "Not a validated trading candidate -- route through the standard trial "
        "protocol (tearsheet + walk-forward) before any settings.json change."
    )


if __name__ == "__main__":
    run()
