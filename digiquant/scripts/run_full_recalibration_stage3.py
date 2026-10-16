#!/usr/bin/env python3
"""Full 11-indicator SDCA recalibration, Stage 3: buy/sell curve optimization.

Freezes the Stage 2 winner weights (floor=0.1/max=1.0 aggregate reweight,
weekly_monthly_rsi=1.0 + weekly_monthly_macd=1.0 dominant, everything else
at the 0.1 floor) and the Stage 1 winner oscillator periods, then searches
independent buy/sell curves for best risk_adjusted_return -- same pipeline
as run_curve_wide_knee_search.py but frozen against the Stage 2 mix instead
of the all-9 diversified weights.

Diagnostic only, in-sample (curve_simulator evaluator, beats_flat_dca_oos
always false here) -- Stage 4 (walk-forward OOS validation) is the real
gate. Do not touch settings.json/RESEARCH_STATE.md until that gate passes.

Usage:
    uv run python scripts/run_full_recalibration_stage3.py
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

# Stage 2 winner (coarse grid, stable across 2:1/3:1/5:1 sensitivity checks).
STAGE2_WINNER_WEIGHTS = SdcaCompositeWeights(
    power_law=0.1,
    rs_eth=0.1,
    weekly_rsi=0.1,
    weekly_macd=0.1,
    sma_band=0.1,
    monthly_rsi=0.1,
    monthly_macd=0.1,
    weekly_monthly_rsi=1.0,
    weekly_monthly_macd=1.0,
)

# Stage 1 winner periods (run_full_recalibration_stage1.py output).
STAGE1_OSCILLATOR_SPEC = SdcaOscillatorSpec(
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=16,
    macd_slow=35,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=120,
    sma_band_fast_window=30,
    rs_eth_window=60,
    rs_eth_fast_window=20,
    power_law_trend_window=180,
    monthly_rsi_length=2,
    monthly_rsi_daily_length=14,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
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
        cache_dir, weights=STAGE2_WINNER_WEIGHTS, oscillators=STAGE1_OSCILLATOR_SPEC
    )
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights: {weights.model_dump()}")
    print(f"wide-knee search bounds: {WIDE_KNEE_SEARCH_BOUNDS}\n")

    print("=== Stage 3: Wide-knee curve fit (risk_adjusted_return objective) ===")
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

    print("=== rate_at() vs reference risk levels ===")
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
        "\nStage 3 complete. Diagnostic only, in-sample. Stage 4 (walk-forward OOS "
        "validation) is required before this counts as a validated candidate -- "
        "do not touch settings.json/RESEARCH_STATE.md until beats_flat_dca_oos=True "
        "with a stable sensitivity check."
    )


if __name__ == "__main__":
    run()
