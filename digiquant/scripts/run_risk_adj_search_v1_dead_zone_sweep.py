#!/usr/bin/env python3
"""Stage B dead-zone-width sweep on risk_adj_search_v1's reproduced curve.

Stage 4 walk-forward on risk_adj_search_v1's exact reproduced shape
(buy_knee_risk=45, sell_knee_risk=50 -- a 5-point dead zone) showed
beats_flat_dca_oos=True but an UNSTABLE sensitivity check (+/-9.04pp) and
fold 1 going infeasible with OOS capital_deployed_pct collapsing to -390%,
i.e. the narrow dead zone causes pathological churn in at least one regime.

Chris asked to keep that direction (fast overbought/oversold cycling) but
fix the pathology: "revisit... but widen the dead zone slightly to kill the
churn while keeping most of the frequent-cycling behavior." This holds
risk_adj_search_v1's rates/curvatures fixed (buy_max_rate=35,
sell_max_rate=25, buy_curvature=1.5, sell_curvature=1.0) and its knee
midpoint (47.5) as the fixed crossing point -- exactly Stage B's
``sweep_dead_zone_width`` -- and reports the risk_adjusted_return-vs-
trade-count frontier from a near-continuous 0.5-point zone out to a 50-point
zone (wider than the current baseline's ~48-point gap), so a width can be
picked that keeps most of the cycling frequency while resolving the churn
pathology.

Diagnostic only, in-sample (curve_simulator). Does not touch settings.json
or RESEARCH_STATE.md. Pick a width from the frontier below, then re-run
Stage 4 walk-forward on it before any acceptance.

Usage:
    uv run python scripts/run_risk_adj_search_v1_dead_zone_sweep.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    DEAD_ZONE_WIDTH_GRID,
    load_frozen_index,
    sweep_dead_zone_width,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)

# risk_adj_search_v1's reproduced shape, treated as "Stage A's winner" for
# Stage B's purposes: crossing_risk = midpoint of its two knees (47.5),
# rates/curvatures held fixed at its values.
RISK_ADJ_V1_SHAPE = SdcaCurveShape(
    buy_max_rate=35.0,
    buy_knee_risk=45.0,
    sell_knee_risk=50.0,
    sell_max_rate=25.0,
    buy_curvature=1.5,
    sell_curvature=1.0,
)


def run(cache_dir: Path = DEFAULT_CACHE_DIR, *, initial_cash: float = 1000.0) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=FROZEN_WEIGHTS)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({dates.len()} daily bars)")
    print(f"frozen weights: {weights.model_dump()}")
    print(f"fixed rates/curvatures: buy_max_rate=35.0 sell_max_rate=25.0 buy_curvature=1.5 sell_curvature=1.0\n")

    print("=== Stage B: dead-zone-width sweep (fixed risk_adj_search_v1 crossing/rates/curvatures) ===")
    stage_b = sweep_dead_zone_width(
        dates,
        prices,
        risk,
        RISK_ADJ_V1_SHAPE,
        initial_cash=initial_cash,
        frozen_weights=weights,
        widths=DEAD_ZONE_WIDTH_GRID,
    )
    print(f"  crossing_risk: {stage_b.crossing_risk:.4f}  (current risk_adj_search_v1 width=5.0)\n")
    header = f"{'width':>6} {'rar':>9} {'return_pct':>11} {'dd_pct':>8} {'trade_days':>11} {'buy_days':>9} {'sell_days':>10} {'feasible':>9}"
    print(f"  {header}")
    for t in stage_b.trials:
        print(
            f"  {t.width:6.1f} {t.risk_adjusted_return:9.3f} {t.total_return_pct:11.2f} {t.max_drawdown_pct:8.2f} "
            f"{t.trade_days:11d} {t.buy_days:9d} {t.sell_days:10d} {str(t.feasible):>9}"
        )
    print(
        f"\n  continuous baseline (crossing only, width=0): "
        f"rar={stage_b.continuous_baseline.risk_adjusted_return:.3f} "
        f"trade_days={stage_b.continuous_baseline.trade_days}"
    )
    print(
        "\nDiagnostic only, in-sample (curve_simulator, beats_flat_dca_oos=False here by "
        "construction). Pick a width, then re-run Stage 4 walk-forward on it -- fold-1 "
        "feasibility and sensitivity stability are NOT visible from this in-sample sweep."
    )


if __name__ == "__main__":
    run()
