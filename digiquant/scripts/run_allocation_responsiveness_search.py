#!/usr/bin/env python3
"""Curve search scored on allocation RESPONSIVENESS, not just return.

Context (Chris, 2026-09-18, looking at the validated baseline's tearsheet):
the published ``btc_optimized`` curve on the validated baseline
(power_law=1.0, m2=0.5, dxy=0.5) rides allocation up to ~97-99% by 2021 and
never meaningfully lets go again -- even the 2022 bear market (BTC -75%)
only pulled it down to 71.7%, and 2024-2026 sit in a 96.5-99.9% band. Every
curve/weight search this project has run so far (see RESEARCH_STATE.md)
scored candidates purely on vs-flat-DCA return / risk_adjusted_return. None
of them scored whether the allocation line actually oscillates with
valuation mid-cycle -- so a curve that saturates to ~100% and coasts was
never penalized for it, even though that behavior is close to buy-and-hold,
not a real dynamic DCA strategy.

This script adds a second objective -- allocation responsiveness -- and
reports it ALONGSIDE (not instead of) risk_adjusted_return / vs_flat_dca_pct
for every candidate in the existing wide-knee curve search space. Diagnostic
only: go/no-go via the fast ``run_backtest`` evaluator (curve_simulator),
same as every other Stage-3 trial in RESEARCH_STATE.md's standard trial
protocol. A candidate that clears both bars still needs a full walk-forward
OOS run (Stage 4) before it can be proposed as a new baseline. Never touches
settings.json/RESEARCH_STATE.md/presets.json/Supabase per the standing gate.

Responsiveness metric (``allocation_responsiveness_score``): mean absolute
day-over-day change in allocated-pct-of-equity, restricted to bars where
price is within 25% of its trailing-1y high (i.e. "mid/late bull market" --
the exact regime Chris flagged: allocation should be able to trim 20-30%
off the top there and rebuy dips, not just coast at ~100%). A curve that
never trims in that regime scores near 0 here regardless of its return.

Usage:
    uv run python -m scripts.run_allocation_responsiveness_search
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    fill_concentration,
    load_frozen_index,
    published_curve_shape,
    sample_wide_knee_curve_trials,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

VALIDATED_BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
BULL_PROXIMITY_PCT = 25.0  # "mid/late bull" = within this % of trailing-1y high
DRAWDOWN_EPSILON = 0.5


def allocated_pct_series(frame: pl.DataFrame) -> list[float]:
    cash = frame["cash"].to_list()
    units = frame["asset_units"].to_list()
    price = frame["price"].to_list() if "price" in frame.columns else None
    portfolio = frame["portfolio_value"].to_list()
    out = []
    for c, u, pv in zip(cash, units, portfolio, strict=True):
        asset_value = pv - c
        out.append(100.0 * asset_value / pv if pv > 0 else 0.0)
    return out


def trailing_high_proximity_pct(prices: list[float], window: int = 365) -> list[float]:
    """% below trailing window high (0 = at the high)."""
    out = []
    for i in range(len(prices)):
        start = max(0, i - window + 1)
        peak = max(prices[start : i + 1])
        out.append(100.0 * (peak - prices[i]) / peak)
    return out


def allocation_responsiveness_score(
    frame: pl.DataFrame, prices: list[float], bull_proximity_pct: float = BULL_PROXIMITY_PCT
) -> float:
    alloc = allocated_pct_series(frame)
    proximity = trailing_high_proximity_pct(prices)
    deltas = [abs(alloc[i] - alloc[i - 1]) for i in range(1, len(alloc)) if proximity[i] <= bull_proximity_pct]
    return sum(deltas) / len(deltas) if deltas else 0.0


def run(cache_dir: Path = DEFAULT_CACHE_DIR, initial_cash: float = 1000.0) -> None:
    dates, prices_s, risk, weights = load_frozen_index(cache_dir, weights=VALIDATED_BASELINE_WEIGHTS)
    prices = prices_s.to_list()
    print(f"Frozen index: validated baseline weights {weights}\n")

    baseline_shape = published_curve_shape()
    baseline_report, baseline_frame = run_backtest(
        dates, prices_s, risk, AccumDistCurve(baseline_shape.to_nodes()), initial_cash
    )
    baseline_max_dd = abs(baseline_report.dca_max_drawdown_pct) * 100.0
    baseline_rar = baseline_report.total_return_pct / max(baseline_max_dd, DRAWDOWN_EPSILON)
    baseline_resp = allocation_responsiveness_score(baseline_frame, prices)
    print("=== published btc_optimized curve (today's baseline) ===")
    print(
        f"  vs_flat_dca={baseline_report.vs_flat_dca_pct:+.2f}%  risk_adjusted_return={baseline_rar:.3f}"
        f"  allocation_responsiveness={baseline_resp:.3f} (mean |Δalloc%| per day, in-bull-only)"
    )
    print(f"  (Chris's read of this curve's tearsheet: pins ~97-99% allocation 2024-2026, barely moves)\n")

    trials = sample_wide_knee_curve_trials(n_random=1500, seed=42, include_grid=True)
    print(f"Scoring {len(trials)} wide-knee curve candidates on (return, responsiveness) jointly...\n")

    scored = []
    for params in trials:
        shape = SdcaCurveShape(**params)
        report, frame = run_backtest(dates, prices_s, risk, AccumDistCurve(shape.to_nodes()), initial_cash)
        conc = fill_concentration(frame)
        if conc.sell_notional <= 0.0:
            continue  # long-only shape, can't be "responsive" by construction
        max_dd = abs(report.dca_max_drawdown_pct) * 100.0
        rar = report.total_return_pct / max(max_dd, DRAWDOWN_EPSILON)
        resp = allocation_responsiveness_score(frame, prices)
        # Joint objective: don't let a responsiveness-only winner torch returns.
        # Require rar >= 60% of baseline's, then rank by responsiveness among survivors.
        scored.append(
            {
                "shape": params,
                "vs_flat_dca_pct": report.vs_flat_dca_pct,
                "risk_adjusted_return": rar,
                "allocation_responsiveness": resp,
                "max_drawdown_pct": max_dd,
            }
        )

    survivors = [s for s in scored if s["risk_adjusted_return"] >= 0.6 * baseline_rar]
    survivors.sort(key=lambda s: -s["allocation_responsiveness"])
    print(f"{len(scored)} feasible (has sells) candidates scored, {len(survivors)} clear >=60% of baseline's risk_adjusted_return\n")

    print("=== top 8 by allocation_responsiveness among return-feasible survivors ===")
    for s in survivors[:8]:
        sh = s["shape"]
        print(
            f"  resp={s['allocation_responsiveness']:.3f}  rar={s['risk_adjusted_return']:.3f}"
            f"  vs_flat_dca={s['vs_flat_dca_pct']:+.2f}%  maxDD={s['max_drawdown_pct']:.1f}%"
            f"  buy_knee={sh['buy_knee_risk']:.1f} sell_knee={sh['sell_knee_risk']:.1f}"
            f" buy_rate={sh['buy_max_rate']:.1f} sell_rate={sh['sell_max_rate']:.1f}"
            f" buy_curv={sh['buy_curvature']:.2f} sell_curv={sh['sell_curvature']:.2f}"
        )

    if not survivors:
        print("  none -- every candidate with meaningful allocation responsiveness loses too much return.")

    print(
        "\nDiagnostic only (curve_simulator go/no-go). Not touching RESEARCH_STATE.md/settings.json -- "
        "a survivor here still needs a full walk-forward OOS run (Stage 4) before it's a baseline proposal."
    )


if __name__ == "__main__":
    run()
