#!/usr/bin/env python3
"""Stage 3 curve refit, take 2: same power-law-dominant frozen index as
``run_power_law_dominant_curve_search.py``, but with ``buy_knee_risk``'s
search floor raised from the default 20.0 back to 24.0.

Finding from the unconstrained search's fresh tearsheet
(``pld_fresh_curve_full_history.json``): the unconstrained winner
(buy_knee_risk=20.18, buy_curvature=1.5735) drove ``max_drawdown_pct`` down
by generically staying in cash longer -- but this specifically delayed
re-entry at the actual 2022-11 long-term bottom. Allocation there fell to
~47-56% for months (Nov 2022-Apr 2023) vs. 85-90% for the *same weights*
under the old published curve (buy_knee_risk=24.1) over the same window,
only ramping to >80% by May 2023 -- after most of the price recovery
($16,885 -> ~$27,000+) had already happened. The generic
risk_adjusted_return objective (total_return / max_drawdown) is blind to
*when* in the cycle a drawdown reduction happens, so it happily trades away
bottom-capture speed for smoother multi-year drawdown -- exactly backwards
from Chris's explicit, non-negotiable priority ("long-term bottoms are
necessary... not at the expense of medium-term bottoms, but long-term
bottoms are necessary").

Fix: constrain the search so buy_knee_risk can never be set *stricter*
(lower) than the already-validated published value (24.1, which the
isolation test confirmed catches the 2022 bottom at 85% allocation for
these same weights). Sell-side params and buy_max_rate/buy_curvature stay
fully free -- this only prevents the optimizer from sacrificing bottom
re-entry speed for a smoother drawdown number elsewhere.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full table to Chris for explicit accept first.

Usage:
    uv run python scripts/run_power_law_dominant_curve_search_constrained.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_COARSE_GRID,
    WIDE_KNEE_SEARCH_BOUNDS,
    load_frozen_index,
    search_wide_knee_curve,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.15, dxy=0.15)

# Raise buy_knee_risk's floor to the published, bottom-capture-validated
# value (24.1 -> round down slightly to 24.0 to keep a clean grid point).
# Everything else keeps the default wide-knee bounds/grid.
CONSTRAINED_BOUNDS = {**WIDE_KNEE_SEARCH_BOUNDS, "buy_knee_risk": (24.0, 48.0)}
CONSTRAINED_GRID = {**WIDE_KNEE_COARSE_GRID, "buy_knee_risk": (24.0, 30.0, 35.0, 40.0, 45.0)}


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=FROZEN_WEIGHTS)
    print(f"frozen index: {dates[0]}..{dates[-1]} ({len(dates)} bars), weights={weights.model_dump()}\n")

    print("=== Stage 3 (constrained): buy_knee_risk floor raised to 24.0 ===\n")
    result = search_wide_knee_curve(
        dates,
        prices,
        risk,
        initial_cash=1000.0,
        frozen_weights=weights,
        bounds=CONSTRAINED_BOUNDS,
        grid=CONSTRAINED_GRID,
    )

    print(f"best shape: {result.best.shape.model_dump()}")
    print(f"  total_return_pct={result.best.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.best.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.best.risk_adjusted_return:.3f}")
    print(f"  vs_lump_pct={result.best.vs_lump_pct:.2f}  vs_flat_dca_pct={result.best.vs_flat_dca_pct:.2f}")
    print(f"  persist_ok={result.persist_ok}  feasible={result.best.feasible}")
    print()
    print("baseline (published btc_optimized shape, same frozen index):")
    print(f"  total_return_pct={result.baseline.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.baseline.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.baseline.risk_adjusted_return:.3f}")
    print()
    print(f"evaluated={result.num_evaluations}  feasible={result.num_feasible}")
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "next: regenerate the full-history tearsheet + fresh Stage 4 walk-forward with this shape."
    )


if __name__ == "__main__":
    run()
