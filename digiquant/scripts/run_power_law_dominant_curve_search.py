#!/usr/bin/env python3
"""Stage 3 proper curve refit for the power-law-dominant reweight
(power_law=1.0, m2=0.15, dxy=0.15) -- see ``run_power_law_dominant_walk_forward.py``
for the isolation test that deliberately reused the OLD published curve
against this changed index, and for the full diagnosis.

Per AGENTS.md's "index-then-curve" rule, curve fitting must never reuse an
old shape against a changed index for a final candidate. This freezes the
power-law-dominant index (a materially different composite than the
published one power_law=1.0/m2=0.5/dxy=0.5 the current curve was fit
against) and runs a fresh wide-knee buy/sell curve search on it.

Follow-up diagnostic (``run_power_law_dominant_walk_forward.py``'s fold-1
investigation): fold 1's OOS window (2019-07-01..2021-11-20) blows its
drawdown cap (~53%) at the exact same point (2020-03-12, the COVID
flash-crash low) for both the baseline and this candidate, with allocation
pinned at 99%+ throughout -- i.e. the strategy was already appropriately
near-fully-deployed for its cycle position (BTC was nowhere near a
valuation top in Jan/Feb 2020) when a fast exogenous macro shock hit. No
curve shape can fix this: a sell curve only fires when composite risk
crosses into "expensive" territory, and none of power_law/m2/dxy read BTC as
expensive at that point. This search may still improve fold 0/fold 2's
drawdowns and the "sell more at tops" behavior Chris asked for, but is not
expected to rescue fold 1.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md. Report
the full curve-search table + a fresh Stage 4 walk-forward to Chris for
explicit accept first, per the standing playbook gate.

Usage:
    uv run python scripts/run_power_law_dominant_curve_search.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_optimize import load_frozen_index, search_wide_knee_curve
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Power-law-dominant reweight (run_power_law_dominant_walk_forward.py).
FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.15, dxy=0.15)


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=FROZEN_WEIGHTS)
    print(f"frozen index: {dates[0]}..{dates[-1]} ({len(dates)} bars), weights={weights.model_dump()}\n")

    print("=== Stage 3: wide-knee curve search on power-law-dominant index ===\n")
    result = search_wide_knee_curve(dates, prices, risk, initial_cash=1000.0, frozen_weights=weights)

    print(f"best shape: {result.best.shape.model_dump()}")
    print(f"  total_return_pct={result.best.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.best.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.best.risk_adjusted_return:.3f}")
    print(f"  vs_lump_pct={result.best.vs_lump_pct:.2f}  vs_flat_dca_pct={result.best.vs_flat_dca_pct:.2f}")
    print()
    print("baseline (published btc_optimized shape, same frozen index -- the isolation-test shape):")
    print(f"  total_return_pct={result.baseline.total_return_pct:.2f}")
    print(f"  max_drawdown_pct={result.baseline.max_drawdown_pct:.2f}")
    print(f"  risk_adjusted_return={result.baseline.risk_adjusted_return:.3f}")
    print(f"  vs_lump_pct={result.baseline.vs_lump_pct:.2f}  vs_flat_dca_pct={result.baseline.vs_flat_dca_pct:.2f}")
    print()
    print(f"evaluated={result.num_evaluations}  feasible={result.num_feasible}")
    print(
        f"beats_baseline_return={result.beats_baseline_return}  "
        f"beats_baseline_concentration={result.beats_baseline_concentration}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "next step is a fresh Stage 4 walk-forward with this shape, then report to Chris."
    )


if __name__ == "__main__":
    run()
