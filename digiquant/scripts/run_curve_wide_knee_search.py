#!/usr/bin/env python3
"""Wide-knee curve search on the all-9 floor-diversified index.

Chris's framing (this session, 2026-09-05): the strategy trades far too
often -- ~98% of days on the pure continuous Stage A winner -- and he wants
a genuinely wide, independently-fit dead zone instead. Looking at the
aggregate risk chart, his starting hypothesis is: start buying around
risk=40 (aggressive by ~25), start selling around risk=60 (aggressive by
~75), symmetric only as a *seed* since the composite is z-scored, and the
buy/sell curves are free to end up asymmetric -- "we'll have to play around
with those variables." He also flagged that fills never deplete cash below
~25%, even after aggressive selling, and wants the sell side to be able to
liquidate much closer to zero in a bear market: "we could be more aggressive
with our selling... we're pretty aggressive with our buying, but not so much
with our selling."

This script runs ``search_wide_knee_curve`` -- independent buy/sell knees,
curvature >= 1 (already gives the exponential "slow near the knee, fast at
the edge" ramp), and a sell_max_rate ceiling widened to 95 (vs the default
search's 40) so the optimizer can actually explore near-full liquidation --
against the same ALL9 floor-diversified frozen index Stage A/B used, purely
for ``risk_adjusted_return``.

Reports, for the winner: the fitted shape, rate_at() evaluated at Chris's
four reference risk levels (25/40/60/75) so the fitted curve's aggressiveness
can be compared directly against his visual-inspection intuition, trade-day
frequency (buy/sell/no-trade days, so "how often are we transacting" is a
number), and the maximum fraction of the portfolio held in cash during the
backtest (so "do we ever get close to fully out" has an answer).

Diagnostic only, in-sample (curve_simulator evaluator, beats_flat_dca_oos
always false here) -- not a candidate for settings.json without Chris's
explicit review. Do not --push-supabase from this script (it has no such
flag).

Usage:
    uv run python scripts/run_curve_wide_knee_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_SEARCH_BOUNDS,
    load_frozen_index,
    search_wide_knee_curve,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Same all-9 floor-diversified, optimized-weight composite as
# run_curve_stage_ab_search.py (RESEARCH_STATE.md, "Sixth pass").
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

REFERENCE_RISK_LEVELS = (25.0, 40.0, 60.0, 75.0)


def run(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    *,
    initial_cash: float = 1000.0,
    n_random: int = 4000,
    seed: int = 42,
) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=ALL9_FLOOR_DIVERSIFIED_WEIGHTS)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights: {weights.model_dump()}")
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
        "Starting-point hypothesis was buy_knee~40/sell_knee~60 (aggressive by 25/75); "
        "not a validated trading candidate -- route through the standard trial protocol "
        "before any settings.json change."
    )


if __name__ == "__main__":
    run()
