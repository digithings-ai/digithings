#!/usr/bin/env python3
"""Remaining-book curve Stage A/B search on the all-9 floor-diversified index.

Chris's framing (this session): fit the best *continuous* (no dead-zone) buy/
sell curve purely for risk-adjusted return against the aggregate valuation
index, then -- as a separate, later step -- widen a dead zone only to cap
trade frequency to something realistic, without letting that threshold shape
the underlying curve fit. "I wouldn't want the thresholds to play a role...
find the best buy and sell curves if it was a continuous thing and then we
could just clean up the middle area, which has the least impact and just
keep the edges where the most buying and selling happens."

Index: the all-9 floor-diversified, optimized-weight composite from
``run_dual_timeframe_composite_search.py`` (RESEARCH_STATE.md) --
``power_law=1.0, sma_band=1.0, monthly_rsi=1.0`` at the grid ceiling,
``m2, rs_eth, dxy, weekly_rsi, weekly_macd, monthly_macd`` all floored at
``0.25``. That search is a diagnostic **index**, not settings.json's
published weights, so this script freezes it explicitly via
``load_frozen_index(..., weights=...)`` rather than reading settings.json.

Stage A: ``search_continuous_curve`` fits a single free crossing point (plus
a fixed tiny epsilon gap) that maximizes ``risk_adjusted_return`` --
``curve_optimize.py``'s objective, not raw return.
Stage B: ``sweep_dead_zone_width`` fixes Stage A's winning crossing/rates/
curvatures and widens the knee gap, reporting risk_adjusted_return against
trade_days (``buy_days + sell_days``) at each width -- the frontier for
picking a realistic trade cadence.

This is a diagnostic search on today's cached data (curve_simulator
evaluator, in-sample, ``beats_flat_dca_oos`` always false here) -- not a
walk-forward OOS claim, and not a candidate for settings.json without
Chris's explicit review. Do not --push-supabase from this script (it has no
such flag).

Usage:
    uv run python scripts/run_curve_stage_ab_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    DEAD_ZONE_WIDTH_GRID,
    load_frozen_index,
    search_continuous_curve,
    sweep_dead_zone_width,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# The all-9 floor-diversified, optimized-weight composite (RESEARCH_STATE.md,
# "Sixth pass"): power_law/sma_band/monthly_rsi at the grid ceiling, the rest
# floored at 0.25 so the reweight can never collapse back to a single
# indicator. Identical across the 2:1/3:1/5:1 long:medium sensitivity sweep.
ALL9_FLOOR_DIVERSIFIED_WEIGHTS = SdcaCompositeWeights(
    power_law=1.0,
    sma_band=1.0,
    monthly_rsi=1.0,
    m2=0.25,
    rs_eth=0.25,
    dxy=0.25,
    weekly_rsi=0.25,
    weekly_macd=0.25,
    monthly_macd=0.25,
)


def run(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    *,
    initial_cash: float = 1000.0,
    n_random: int = 400,
    seed: int = 42,
) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=ALL9_FLOOR_DIVERSIFIED_WEIGHTS)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights: {weights.model_dump()}\n")

    print("=== Stage A: continuous curve fit (risk_adjusted_return objective) ===")
    stage_a = search_continuous_curve(
        dates,
        prices,
        risk,
        initial_cash=initial_cash,
        frozen_weights=weights,
        n_random=n_random,
        seed=seed,
    )
    winner = stage_a.best.shape
    print(f"  evaluated:            {stage_a.num_evaluations} trials ({stage_a.num_feasible} feasible)")
    print(f"  winning shape:        {winner}")
    print(f"  risk_adjusted_return: {stage_a.best.risk_adjusted_return:.4f}")
    print(f"  total_return_pct:     {stage_a.best.total_return_pct:.2f}%")
    print(f"  max_drawdown_pct:     {stage_a.best.max_drawdown_pct:.2f}%")
    print(f"  vs published baseline risk_adjusted_return: {stage_a.baseline.risk_adjusted_return:.4f}\n")

    print("=== Stage B: dead-zone-width sweep (fixed Stage A crossing/rates/curvatures) ===")
    stage_b = sweep_dead_zone_width(
        dates,
        prices,
        risk,
        winner,
        initial_cash=initial_cash,
        frozen_weights=weights,
        widths=DEAD_ZONE_WIDTH_GRID,
    )
    print(f"  crossing_risk: {stage_b.crossing_risk:.4f}\n")
    header = f"{'width':>6} {'rar':>9} {'return_pct':>11} {'trade_days':>11} {'buy_days':>9} {'sell_days':>10} {'feasible':>9}"
    print(f"  {header}")
    for t in stage_b.trials:
        print(
            f"  {t.width:6.1f} {t.risk_adjusted_return:9.3f} {t.total_return_pct:11.2f} "
            f"{t.trade_days:11d} {t.buy_days:9d} {t.sell_days:10d} {str(t.feasible):>9}"
        )
    print(
        f"\n  continuous baseline (Stage A winner, width=0): "
        f"rar={stage_b.continuous_baseline.risk_adjusted_return:.3f} "
        f"trade_days={stage_b.continuous_baseline.trade_days}"
    )
    print(
        "\nDiagnostic only, in-sample (curve_simulator, beats_flat_dca_oos=False). "
        "Not a validated trading candidate; pick a width from the frontier above "
        "and route through the standard trial protocol before any settings.json change."
    )


if __name__ == "__main__":
    run()
