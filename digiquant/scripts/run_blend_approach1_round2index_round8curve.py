#!/usr/bin/env python3
"""Blend Approach 1: Task #93 Round 2's frozen weighted index + a fresh round-8-style curve search.

Chris likes "the valuation index shape of the 17 indicator strat, then the
performance and behavior of the round 8 [strategy]." Approach 1 tests the
most literal reading of that: keep Task #93 Round 2's 17-indicator composite
weights exactly as scored (``ROUND23_WEIGHTS``/``ROUND23_OSCILLATORS``/
``ROUND23_EXTRA_WINDOWS``, duplicated verbatim below from
``run_baseline_relative_rescore.py`` per this repo's self-contained-script
convention), but throw out Round 2's own curve and re-run the SAME
full-resolution feasibility-aware curve search that produced round 8's curve
(``scripts/run_ablation_best_round_full_resolution.py``'s exact pattern) on
top of that fixed index. Then validate with the standing
``run_sdca_walk_forward_vs_baseline`` gate.

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_blend_approach1_round2index_round8curve.py
"""

from __future__ import annotations

import functools
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
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "blend" / "approach1_round2index_round8curve.json"

# ROUND23_* duplicated verbatim from scripts/run_baseline_relative_rescore.py --
# the authoritative oscillator/window config that actually produced
# task93_round2's recorded score in .scratch/baseline_relative_rescore.json
# (run_aggregate_reweight_full17_fixed_index.py's default-oscillator weights
# were an earlier, superseded search stage, not the final scoring pass).
ROUND23_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    rs_eth_window=60,
    rs_eth_fast_window=30,
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=12,
    macd_slow=26,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=180,
    sma_band_fast_window=45,
    monthly_rsi_length=5,
    monthly_rsi_daily_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)

ROUND23_EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

# ROUND23_WEIGHTS -- Task #93 Round 2's frozen weights, exactly as scored.
ROUND23_WEIGHTS = SdcaCompositeWeights(
    power_law=0.1,
    m2=0.1,
    rs_eth=0.1,
    dxy=0.1,
    onchain_mvrv=0.95,
    onchain_asopr=0.1,
    onchain_puell=0.1,
    onchain_rhodl=1,
    onchain_addr_ratio=1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
    weekly_monthly_macd=1,
    weekly_rsi=0.1,
    weekly_macd=0.1,
    sma_band=0.1,
    monthly_rsi=0.1,
    monthly_macd=0.1,
)

FULL_INITIAL_CASH = 10_000.0


def print_comparison(comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print("=== blend_approach1_round2index_round8curve ===")
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
        date_s,
        price_s,
        rails["low"],
        rails["median"],
        rails["high"],
        trend_window=ROUND23_OSCILLATORS.power_law_trend_window,
    ).to_list()

    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=ROUND23_OSCILLATORS,
        extra_windows=ROUND23_EXTRA_WINDOWS,
    )

    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, ROUND23_WEIGHTS)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)

    print("running full-resolution feasibility-aware curve search (n_random=3000 default)...")
    curve_result = search_wide_knee_curve_feasibility_aware(
        date_s, price_s, risk_s, initial_cash=FULL_INITIAL_CASH
    )
    candidate_params = {
        **freeze_weight_params(ROUND23_WEIGHTS),
        **params_from_shape(curve_result.best.shape),
    }

    round23_evaluator = functools.partial(
        evaluate_sdca_trial_curve_sim, oscillators=ROUND23_OSCILLATORS
    )

    print("running full walk-forward vs. risk50-linear baseline (with sensitivity check)...")
    comparison = run_sdca_walk_forward_vs_baseline(
        dates,
        prices,
        candidate_params,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=round23_evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    print_comparison(comparison)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(comparison.model_dump(), indent=2, default=str))
    print(f"wrote {OUT_PATH}")
    print(
        "\nDiagnostic blend attempt only -- never writes settings.json or "
        'RESEARCH_STATE.md\'s "current best validated candidate" section. Report '
        "this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
