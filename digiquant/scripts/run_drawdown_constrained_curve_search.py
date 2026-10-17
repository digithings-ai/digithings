#!/usr/bin/env python3
"""Stage 3 curve search with a HARD max-drawdown ceiling, not just a
return/drawdown ratio.

Chris's explicit target (2026-09-13): the strategy's own equity drawdown
should sit "in or around 30%, 20% at most" -- achieved by actively de-risking
(selling) on the way up *and* de-risking (not staying near-fully invested)
on the way down, catching every long-term bottom without over-exposing into
the next crash.

Every curve search so far (search_curve()/search_wide_knee_curve()) only
maximizes risk_adjusted_return = total_return_pct / max(max_drawdown_pct,
0.5) -- a ratio, not a ceiling. A shape with 45% drawdown but great returns
can still "win" over one with 25% drawdown and merely good returns. That is
exactly how risk_adj_search_v1 ended up with fold-1 OOS drawdown ~50-53%
(the COVID-crash window, 2019-07-01..2021-11-20) -- widening its dead zone
across the whole 5-50 point range never brought that fold's drawdown under
the existing 50% feasibility cap, let alone Chris's actual 20-30% target
(see run_risk_adj_search_v1_wider_dead_zone_walk_forward.py).

This script re-scores the full wide-knee trial pool directly via
score_shape_on_index() (bypassing search_curve()'s single-best selection,
which discards every non-winning trial) against the standing validated
weights (power_law=1.0/m2=0.5/dxy=0.5), then filters to trials whose
*full-history in-sample* max_drawdown_pct clears explicit ceilings (20%,
25%, 30%), reporting the best few candidates in each bucket by total_return_pct
and by risk_adjusted_return. This surfaces shapes the ratio-based search
would never pick as "best" (because something looser scored a higher ratio)
but that actually satisfy the drawdown target Chris just described.

Diagnostic only, in-sample. Does not touch settings.json or RESEARCH_STATE.md.
Whatever survives here still needs Stage 4 walk-forward (per-fold drawdown,
not just full-history) before any acceptance.

Usage:
    uv run python scripts/run_drawdown_constrained_curve_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_COARSE_GRID,
    WIDE_KNEE_SEARCH_BOUNDS,
    CurveOptimizeGates,
    load_frozen_index,
    sample_wide_knee_curve_trials,
    score_shape_on_index,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)

# Chris's stated target: ~30% drawdown, 20% at best. Report all three so the
# tradeoff (tighter ceiling -> fewer/weaker candidates) is visible.
DRAWDOWN_CEILINGS = (20.0, 25.0, 30.0)

TOP_N = 5


def run(cache_dir: Path = DEFAULT_CACHE_DIR, *, initial_cash: float = 1000.0) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=FROZEN_WEIGHTS)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {weights.model_dump()}\n")

    trials = sample_wide_knee_curve_trials(
        n_random=3000,
        seed=42,
        include_grid=True,
        bounds=WIDE_KNEE_SEARCH_BOUNDS,
        grid=WIDE_KNEE_COARSE_GRID,
    )
    print(f"n trials sampled (wide-knee bounds, independent buy/sell): {len(trials)}\n")

    gates = CurveOptimizeGates()
    scores = []
    for params in trials:
        shape = SdcaCurveShape(
            buy_max_rate=params["buy_max_rate"],
            buy_knee_risk=params["buy_knee_risk"],
            sell_knee_risk=params["sell_knee_risk"],
            sell_max_rate=params["sell_max_rate"],
            buy_curvature=params["buy_curvature"],
            sell_curvature=params["sell_curvature"],
        )
        scores.append(score_shape_on_index(dates, prices, risk, shape, initial_cash, gates=gates))

    feasible = [s for s in scores if s.feasible]
    print(f"evaluated={len(scores)}  feasible(existing gates)={len(feasible)}\n")

    for ceiling in DRAWDOWN_CEILINGS:
        under = [s for s in feasible if s.max_drawdown_pct <= ceiling]
        print(f"=== max_drawdown_pct <= {ceiling:.0f}% : {len(under)} candidates ===")
        if not under:
            print("  (none -- no feasible shape in this search space clears this ceiling)\n")
            continue

        by_return = sorted(under, key=lambda s: s.total_return_pct, reverse=True)[:TOP_N]
        print(f"  -- top {len(by_return)} by total_return_pct --")
        for s in by_return:
            sh = s.shape
            print(
                f"    return={s.total_return_pct:9.2f}%  dd={s.max_drawdown_pct:5.2f}%  "
                f"rar={s.risk_adjusted_return:7.3f}  vs_flat_dca={s.vs_flat_dca_pct:7.2f}%  "
                f"vs_lump={s.vs_lump_pct:7.2f}%  "
                f"knees=({sh.buy_knee_risk:.1f}/{sh.sell_knee_risk:.1f})  "
                f"rates=({sh.buy_max_rate:.1f}/{sh.sell_max_rate:.1f})  "
                f"curv=({sh.buy_curvature:.2f}/{sh.sell_curvature:.2f})"
            )

        by_rar = sorted(under, key=lambda s: s.risk_adjusted_return, reverse=True)[:TOP_N]
        print(f"  -- top {len(by_rar)} by risk_adjusted_return --")
        for s in by_rar:
            sh = s.shape
            print(
                f"    rar={s.risk_adjusted_return:7.3f}  return={s.total_return_pct:9.2f}%  "
                f"dd={s.max_drawdown_pct:5.2f}%  vs_flat_dca={s.vs_flat_dca_pct:7.2f}%  "
                f"knees=({sh.buy_knee_risk:.1f}/{sh.sell_knee_risk:.1f})  "
                f"rates=({sh.buy_max_rate:.1f}/{sh.sell_max_rate:.1f})  "
                f"curv=({sh.buy_curvature:.2f}/{sh.sell_curvature:.2f})"
            )
        print()

    print(
        "Diagnostic only, in-sample, full-history drawdown (not per-fold). Pick a "
        "candidate, then run Stage 4 walk-forward -- per-fold OOS drawdown (especially "
        "the COVID-crash fold) is what actually matters and is NOT guaranteed by a "
        "full-history ceiling alone."
    )


if __name__ == "__main__":
    run()
