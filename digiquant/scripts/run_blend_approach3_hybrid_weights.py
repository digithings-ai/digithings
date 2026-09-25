#!/usr/bin/env python3
"""Blend Approach 3: literal hybrid weight vector, round 8's curve reused unchanged, no new search.

Chris likes "the valuation index shape of the 17 indicator strat, then the
performance and behavior of the round 8 [strategy]." Approach 3 is the
cheapest, most literal blend: keep round 8's 5 nonzero weights (m2=1.0,
rs_eth=0.1, onchain_asopr=0.1, fear_greed=0.1, weekly_monthly_rsi=0.1,
duplicated verbatim from ``.scratch/ablation/round_8.json``) as fixed floors,
unchanged. Layer in Task #93 Round 2's other ~12 nonzero weights
(``ROUND23_WEIGHTS`` minus the 5 names round 8 already covers, duplicated
verbatim from ``run_baseline_relative_rescore.py``) at HALF their Round 2
value -- a documented, reproducible scaling rule, not a re-search. Reuse
round 8's exact curve-shape + crash-override params, duplicated verbatim
from ``.scratch/ablation/best_round_full_resolution.json``'s
``candidate.best_params`` -- no curve search at all. Run ONE backtest + ONE
``run_sdca_walk_forward_vs_baseline`` validation pass.

Composite-index construction note: this hybrid vector mixes round 8's floor
indicators (rs_eth, weekly_monthly_rsi -- originally scored under
``SdcaOscillatorSpec()``'s defaults) with Task #93 Round 2's indicators
(originally scored under ``ROUND23_OSCILLATORS``). A single composite build
can only use one ``SdcaOscillatorSpec`` for the whole vector; this script
uses ``ROUND23_OSCILLATORS``/``ROUND23_EXTRA_WINDOWS`` throughout (same
choice as Approaches 1 and 2, for consistency), which means round 8's own
floor indicators are evaluated under different periods than round 8 itself
picked them under. This is a genuine, unavoidable cross-round
methodological wrinkle of blending two candidates scored under different
oscillator configs -- flagged here and in the tearsheet notes, not silently
papered over.

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_blend_approach3_hybrid_weights.py
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from digiquant.strategies.sdca.baseline_evaluator import (
    WalkForwardBaselineComparison,
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "blend" / "approach3_hybrid_weights_round8_curve.json"

# Round 8's 5 nonzero weights, duplicated verbatim from
# .scratch/ablation/round_8.json -- fixed floors, unchanged.
ROUND8_FLOORS: dict[str, float] = {
    "m2": 1.0,
    "rs_eth": 0.1,
    "onchain_asopr": 0.1,
    "fear_greed": 0.1,
    "weekly_monthly_rsi": 0.1,
}

# Task #93 Round 2's full weight vector, duplicated verbatim from
# run_baseline_relative_rescore.py's ROUND23_WEIGHTS.
ROUND23_WEIGHTS_DICT: dict[str, float] = {
    "power_law": 0.1,
    "m2": 0.1,
    "rs_eth": 0.1,
    "dxy": 0.1,
    "onchain_mvrv": 0.95,
    "onchain_asopr": 0.1,
    "onchain_puell": 0.1,
    "onchain_rhodl": 1.0,
    "onchain_addr_ratio": 1.0,
    "fear_greed": 0.1,
    "weekly_monthly_rsi": 0.1,
    "weekly_monthly_macd": 1.0,
    "weekly_rsi": 0.1,
    "weekly_macd": 0.1,
    "sma_band": 0.1,
    "monthly_rsi": 0.1,
    "monthly_macd": 0.1,
}

HALF_SCALE = 0.5

# Round 8's exact curve-shape + crash-override params, duplicated verbatim
# from .scratch/ablation/best_round_full_resolution.json's
# candidate.best_params -- reused unchanged, no curve search.
ROUND8_CURVE_PARAMS: dict[str, float | bool] = {
    "buy_max_rate": 25.0,
    "buy_knee_risk": 45.0,
    "sell_knee_risk": 70.0,
    "sell_max_rate": 90.0,
    "buy_curvature": 1.5,
    "sell_curvature": 2.5,
    "crash_override_enabled": False,
    "crash_override_window": 14,
    "crash_override_min_samples": 7,
    "crash_override_trigger_z": -2.0,
    "crash_override_ramp_z": 1.0,
    "crash_override_risk": 95.0,
}

# ROUND23_* duplicated verbatim from run_baseline_relative_rescore.py -- see
# module docstring for why this (not round 8's own defaults) governs the
# combined index build.
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


def build_hybrid_weights() -> SdcaCompositeWeights:
    """Round 8's 5 nonzero weights as floors, Round 2's other ~12 at half value."""
    payload: dict[str, float] = dict(ROUND8_FLOORS)
    for name, value in ROUND23_WEIGHTS_DICT.items():
        if name in ROUND8_FLOORS:
            continue  # already covered by round 8's floor, not overwritten
        payload[name] = value * HALF_SCALE
    return SdcaCompositeWeights(**payload)


def print_comparison(comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print("=== blend_approach3_hybrid_weights_round8_curve ===")
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

    hybrid_weights = build_hybrid_weights()
    print(f"hybrid weights: {hybrid_weights.model_dump()}\n")

    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=ROUND23_OSCILLATORS,
        extra_windows=ROUND23_EXTRA_WINDOWS,
    )

    candidate_params: dict[str, float | int | str] = {
        **freeze_weight_params(hybrid_weights),
        **ROUND8_CURVE_PARAMS,
    }

    round23_evaluator = functools.partial(
        evaluate_sdca_trial_curve_sim, oscillators=ROUND23_OSCILLATORS
    )

    print("running ONE walk-forward vs. risk50-linear baseline pass (with sensitivity check)...")
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
    OUT_PATH.write_text(
        json.dumps(
            {
                "hybrid_weights": hybrid_weights.model_dump(),
                "candidate_params": candidate_params,
                "comparison": comparison.model_dump(),
            },
            indent=2,
            default=str,
        )
    )
    print(f"wrote {OUT_PATH}")
    print(
        "\nDiagnostic blend attempt only -- never writes settings.json or "
        'RESEARCH_STATE.md\'s "current best validated candidate" section. Report '
        "this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
