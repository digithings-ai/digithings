#!/usr/bin/env python3
"""Buy/sell curve-aggressiveness search with knees FIXED at 30/70.

Chris's direction (2026-09-07, same session that accepted the buy_knee_risk
24.1->30 / sell_knee_risk 71.9->70 threshold trial): "I just want to fix a
few of these [thresholds]... then it's just a matter of playing with the
curves once the risk index is adjusted properly." He then explicitly chose
to keep searching against the *live* settings.json 5-weight index
(power_law/m2/dxy/weekly_rsi/weekly_macd), not the 3-weight validated
baseline, despite that live composite being walk-forward-validated as
losing OOS this session (see RESEARCH_STATE.md's "Known discrepancy"
section) -- his call, not this script's.

Only ``buy_max_rate``, ``sell_max_rate``, ``buy_curvature``, ``sell_curvature``
are searched; ``buy_knee_risk``/``sell_knee_risk`` are held at 30.0/70.0
throughout (not passed to the optimizer at all). Objective is
``risk_adjusted_return`` (total_return_pct / max_drawdown_pct), matching
every other curve search in this file family.

Diagnostic only, in-sample (curve_simulator evaluator, beats_flat_dca_oos
always false here) -- not a candidate for settings.json without Chris's
explicit review. Do not --push-supabase from this script (it has no such
flag).

Usage:
    uv run python scripts/run_curve_fixed_knee_30_70_search.py
"""

from __future__ import annotations

import itertools
import random
from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    load_frozen_index,
    published_curve_shape,
    search_curve,
    shape_from_bounds_ok,
)

_SHAPE_KEYS = (
    "buy_max_rate",
    "buy_knee_risk",
    "sell_knee_risk",
    "sell_max_rate",
    "buy_curvature",
    "sell_curvature",
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

BUY_KNEE_RISK = 30.0
SELL_KNEE_RISK = 70.0

# sell_max_rate ceiling widened past the default (3-40) the same way the
# wide-knee search widened it (5-95): worth letting the optimizer explore
# aggressive liquidation even though the knee positions themselves are fixed.
FIXED_KNEE_BOUNDS: dict[str, tuple[float, float]] = {
    "buy_max_rate": (5.0, 40.0),
    "sell_max_rate": (5.0, 95.0),
    "buy_curvature": (1.0, 6.0),
    "sell_curvature": (1.0, 6.0),
}

FIXED_KNEE_GRID: dict[str, tuple[float, ...]] = {
    "buy_max_rate": (8.0, 15.0, 25.0, 35.0, 40.0),
    "sell_max_rate": (8.0, 15.0, 25.0, 35.0, 50.0, 70.0, 90.0),
    "buy_curvature": (1.0, 1.5, 2.0, 3.0, 4.5, 6.0),
    "sell_curvature": (1.0, 1.5, 2.0, 3.0, 4.5, 6.0),
}

REFERENCE_RISK_LEVELS = (20.0, 30.0, 50.0, 70.0, 80.0)


def sample_fixed_knee_curve_trials(
    *,
    n_random: int = 4000,
    seed: int = 42,
    include_grid: bool = True,
    include_published_knees: bool = True,
) -> list[dict[str, float]]:
    """Grid + seeded-random trials, knees pinned to BUY_KNEE_RISK/SELL_KNEE_RISK."""
    seen: set[tuple[float, ...]] = set()
    out: list[dict[str, float]] = []

    def _add(free: dict[str, float]) -> None:
        params = {**free, "buy_knee_risk": BUY_KNEE_RISK, "sell_knee_risk": SELL_KNEE_RISK}
        if not shape_from_bounds_ok(params, bounds=FIXED_KNEE_BOUNDS):
            return
        key = tuple(round(params[k], 6) for k in _SHAPE_KEYS)
        if key in seen:
            return
        seen.add(key)
        out.append(params)

    if include_published_knees:
        pub = published_curve_shape()
        _add(
            {
                "buy_max_rate": pub.buy_max_rate,
                "sell_max_rate": pub.sell_max_rate,
                "buy_curvature": pub.buy_curvature,
                "sell_curvature": pub.sell_curvature,
            }
        )
    if include_grid:
        names = list(FIXED_KNEE_GRID)
        for combo in itertools.product(*(FIXED_KNEE_GRID[n] for n in names)):
            _add(dict(zip(names, combo, strict=True)))
    rng = random.Random(seed)
    for _ in range(max(0, n_random)):
        drawn = {name: round(rng.uniform(lo, hi), 4) for name, (lo, hi) in FIXED_KNEE_BOUNDS.items()}
        _add(drawn)
    return out


def run(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    *,
    initial_cash: float = 1000.0,
    n_random: int = 4000,
    seed: int = 42,
) -> None:
    # weights=None -> published_indicator_weights() -> live settings.json
    # (Chris's explicit choice this session, not the 3-weight validated baseline).
    dates, prices, risk, weights = load_frozen_index(cache_dir)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights (live settings.json): {weights.model_dump()}")
    print(f"knees fixed at buy={BUY_KNEE_RISK}, sell={SELL_KNEE_RISK}")
    print(f"search bounds (free params only): {FIXED_KNEE_BOUNDS}\n")

    trials = sample_fixed_knee_curve_trials(n_random=n_random, seed=seed)
    print(f"=== Fixed-knee (30/70) curve fit, risk_adjusted_return objective, {len(trials)} trials ===")
    result = search_curve(
        dates,
        prices,
        risk,
        trials,
        initial_cash=initial_cash,
        baseline=published_curve_shape(),
        frozen_weights=weights,
        evaluator="curve_simulator",
    )
    winner = result.best.shape
    print(f"  evaluated:            {result.num_evaluations} trials ({result.num_feasible} feasible)")
    print(f"  winning shape:        {winner}")
    print(f"  risk_adjusted_return: {result.best.risk_adjusted_return:.4f}")
    print(f"  total_return_pct:     {result.best.total_return_pct:.2f}%")
    print(f"  max_drawdown_pct:     {result.best.max_drawdown_pct:.2f}%")
    print(f"  vs_flat_dca_pct:      {result.best.vs_flat_dca_pct:.2f}%")
    print(f"  vs published baseline (today's 24.1/71.9 shape) risk_adjusted_return: {result.baseline.risk_adjusted_return:.4f}\n")

    print("=== rate_at() vs reference risk levels ===")
    for r in REFERENCE_RISK_LEVELS:
        print(f"  rate_at({r:5.1f}) = {winner.rate_at(r):+7.3f}")
    print()

    print("=== Trade frequency & cash depletion (full backtest detail) ===")
    from digiquant.strategies.sdca.backtest import run_backtest
    from digiquant.strategies.sdca.curve import AccumDistCurve

    _report, frame = run_backtest(dates, prices, risk, AccumDistCurve(winner.to_nodes()), initial_cash)
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
        "\nDiagnostic only, in-sample (curve_simulator, beats_flat_dca_oos=False), scored on "
        "the LIVE 5-weight settings.json index (Chris's explicit choice, not the 3-weight "
        "validated baseline). Not a validated trading candidate -- route through the standard "
        "trial protocol (Nautilus tearsheet + explicit accept) before any settings.json change."
    )


if __name__ == "__main__":
    run()
