#!/usr/bin/env python3
"""Full-resolution re-validation of Phase 4's best ablation round (post-mortem Phase 4/5 bridge).

``scripts/run_iterative_ablation.py``'s per-round gate deliberately uses a
reduced ``n_random=300`` feasibility-aware curve search (fast sanity check,
not a final answer) -- see that script's own docstring: "Only the best round
gets a full-resolution re-search before being written up." This script does
that re-search for round 8 (the best-seen round, +52.01% duration-weighted
OOS in the fast gate), then runs the full baseline-relative walk-forward
comparison (Phase 2's ``run_sdca_walk_forward_vs_baseline``) so the result
carries ``beats_flat_dca_oos`` and a sensitivity-neighbor stability check --
exactly what Phase 5's decision memo needs and what the standing accept gate
(RESEARCH_STATE.md "Standard trial protocol") requires before any
settings.json change is even considered.

Round 8's weights (``.scratch/ablation/round_8.json``): m2=1.0, rs_eth=0.1,
onchain_asopr=0.1, fear_greed=0.1, weekly_monthly_rsi=0.1, power_law=0.0 and
every other indicator at 0.0 -- duplicated verbatim below along with
``EXTRA_WINDOWS`` from ``run_iterative_ablation.py``, per this repo's
self-contained-script convention (no cross-script imports).

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_ablation_best_round_full_resolution.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.baseline_evaluator import (
    WalkForwardBaselineComparison,
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import params_from_shape
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    search_wide_knee_curve_feasibility_aware,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "ablation" / "best_round_full_resolution.json"

# EXTRA_WINDOWS duplicated verbatim from scripts/run_iterative_ablation.py --
# round 8's weights were reweighted against extra_z built with these windows,
# so the full-resolution re-search must use the same inputs.
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

ROUND8_WEIGHTS = SdcaCompositeWeights(
    power_law=0.0,
    m2=1.0,
    rs_eth=0.1,
    onchain_asopr=0.1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
)

FULL_INITIAL_CASH = 10_000.0


def print_comparison(comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print("=== ablation_round8_full_resolution ===")
    print(
        f"  candidate  mean_oos(unweighted)={c.mean_oos_vs_flat_dca_pct_unweighted:+7.2f}%  "
        f"mean_oos(duration)={c.mean_oos_vs_flat_dca_pct_duration_weighted:+7.2f}%  "
        f"beats_flat_dca_oos={c.beats_flat_dca_oos}  sensitivity_stable={c.sensitivity.stable}"
    )
    print(
        f"  baseline   mean_oos(unweighted)={b.mean_oos_vs_flat_dca_pct_unweighted:+7.2f}%  "
        f"mean_oos(duration)={b.mean_oos_vs_flat_dca_pct_duration_weighted:+7.2f}%  "
        f"beats_flat_dca_oos={b.beats_flat_dca_oos}  sensitivity_stable={b.sensitivity.stable}"
    )
    print(
        f"  delta_mean_oos_vs_flat_dca_pct={comparison.delta_mean_oos_vs_flat_dca_pct:+7.2f}%  "
        f"beats_baseline_oos={comparison.beats_baseline_oos}\n"
    )


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    ).to_list()

    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None, extra_windows=EXTRA_WINDOWS
    )

    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, ROUND8_WEIGHTS)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)

    print("running full-resolution feasibility-aware curve search (n_random=3000 default)...")
    curve_result = search_wide_knee_curve_feasibility_aware(
        date_s, price_s, risk_s, initial_cash=FULL_INITIAL_CASH
    )
    candidate_params = {
        **freeze_weight_params(ROUND8_WEIGHTS),
        **params_from_shape(curve_result.best.shape),
    }

    print("running full walk-forward vs. risk50-linear baseline (with sensitivity check)...")
    comparison = run_sdca_walk_forward_vs_baseline(
        dates,
        prices,
        candidate_params,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    print_comparison(comparison)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(comparison.model_dump(), indent=2, default=str))
    print(f"wrote {OUT_PATH}")
    print(
        "\nDiagnostic re-validation only -- never writes settings.json or "
        'RESEARCH_STATE.md\'s "current best validated candidate" section. Report '
        "this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
