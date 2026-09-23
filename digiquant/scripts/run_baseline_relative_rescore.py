#!/usr/bin/env python3
"""Baseline-relative re-score of existing SDCA candidates (post-mortem Phase 3).

Chris's post-mortem follow-up flagged that binary in/out-of-zone timing
correctness isn't the bar he wants: a candidate must beat a simple,
non-optimized reference curve (buy below composite risk 50, sell above,
linear rate schedule) under walk-forward OOS, not just "does it make
money." Phase 2 built that machinery
(``baseline_evaluator.run_sdca_walk_forward_vs_baseline``, already
committed). This script is Phase 3: run it over the existing candidates
and print/emit one comparison table -- no new library code.

Configs re-scored:

  1. validated_baseline -- the current best validated candidate
     (power_law=1.0, m2=0.5, dxy=0.5; published ``btc_optimized`` curve;
     RESEARCH_STATE.md, dated 2026-09-03).
  2. live_settings_json -- the live ``settings.json`` config, sourced via
     ``curve_optimize.published_indicator_weights()``. That function had a
     genuine bug (read ``block.get("power_law", ...)`` but the on-disk key
     is ``"valuation"``) which this phase fixed as part of exercising it
     directly -- see the accompanying regression test in
     test_curve_optimize.py. RESEARCH_STATE.md's "known discrepancy" already
     validated this 5-weight config twice and it loses (-16.21% OOS via
     walk-forward, -46% to -51% OOS via an ad-hoc Stage-A search).
  3. task93_round2 -- Task #93 Round 2's 17-indicator floor-diversified
     reweight + fixed-index wide-knee curve search winner (commit
     60cf0777c). ``beats_flat_dca_oos=True`` but ``sensitivity.stable=False``
     -- not promoted.
  4. task93_round3 -- Round 2's same weights + the feasibility-aware curve
     search winner (commit 54c4a95f9). REJECT, ``beats_flat_dca_oos=False``.

EXCLUDED: the plan's originally-named "2026-09-18 regime-switch candidate."
Its own commit message documents that it feeds a per-fold regime-switched
risk series directly into ``run_backtest``, bypassing
``run_sdca_walk_forward``'s single-fixed-weight-vector interface entirely --
there is no ``candidate_params`` dict that represents it, so it cannot go
through ``run_sdca_walk_forward_vs_baseline`` without new plumbing, which is
out of this phase's scope ("no new library code"). Its driver script no
longer exists on disk. In its place this table carries Task #93's Round 2
AND Round 3 as two separate rows (the plan named them together as one
item), preserving the intended four-row comparison.

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_baseline_relative_rescore.py
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from digiquant.strategies.sdca.baseline_evaluator import (
    WalkForwardBaselineComparison,
    run_sdca_walk_forward_vs_baseline,
)
from digiquant.strategies.sdca.curve_optimize import (
    params_from_shape,
    published_curve_shape,
    published_indicator_weights,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
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
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "baseline_relative_rescore.json"

# ---------------------------------------------------------------------------
# Task #93 Round 2/3 constants, duplicated verbatim from
# scripts/run_full_recalibration_fixed_index.py /
# run_full_recalibration_feasible_curve.py per this repo's run_*.py
# self-contained-script convention (no cross-script imports).
# ---------------------------------------------------------------------------
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

ROUND2_CURVE = SdcaCurveShape(
    buy_max_rate=36.5518,
    buy_knee_risk=25.3504,
    sell_knee_risk=73.1633,
    sell_max_rate=16.9461,
    buy_curvature=1.2667,
    sell_curvature=4.5296,
)

ROUND3_CURVE = SdcaCurveShape(
    buy_max_rate=35.0,
    buy_knee_risk=30.0,
    sell_knee_risk=70.0,
    sell_max_rate=15.0,
    buy_curvature=1.5,
    sell_curvature=4.0,
)


def _candidate_params(
    weights: SdcaCompositeWeights, shape: SdcaCurveShape
) -> dict[str, float | int | str]:
    params: dict[str, float | int | str] = dict(freeze_weight_params(weights))
    params.update(params_from_shape(shape))
    return params


def build_configs() -> list[tuple[str, str, dict[str, float | int | str], object]]:
    """Each entry: (key, label, candidate_params, evaluator)."""
    default_evaluator = evaluate_sdca_trial_curve_sim
    round23_evaluator = functools.partial(
        evaluate_sdca_trial_curve_sim, oscillators=ROUND23_OSCILLATORS
    )
    return [
        (
            "validated_baseline",
            "Current best validated candidate (power_law=1.0, m2=0.5, dxy=0.5; "
            "published btc_optimized curve; RESEARCH_STATE.md 2026-09-03)",
            _candidate_params(
                SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5),
                published_curve_shape(),
            ),
            default_evaluator,
        ),
        (
            "live_settings_json",
            "Live settings.json config (published_indicator_weights(), now reading "
            'the on-disk "valuation" key correctly) -- previously validated at '
            "-16.21% OOS via walk-forward, loses",
            _candidate_params(published_indicator_weights(), published_curve_shape()),
            default_evaluator,
        ),
        (
            "task93_round2",
            "Task #93 Round 2: 17-indicator floor-diversified reweight + fixed-index "
            "wide-knee curve (commit 60cf0777c) -- beats_flat_dca_oos=True, "
            "sensitivity unstable, not promoted",
            _candidate_params(ROUND23_WEIGHTS, ROUND2_CURVE),
            round23_evaluator,
        ),
        (
            "task93_round3",
            "Task #93 Round 3: Round 2 weights + feasibility-aware curve search "
            "winner (commit 54c4a95f9) -- REJECT, beats_flat_dca_oos=False",
            _candidate_params(ROUND23_WEIGHTS, ROUND3_CURVE),
            round23_evaluator,
        ),
    ]


def print_exclusion_note() -> None:
    print(
        'NOTE: the plan\'s originally-named "2026-09-18 regime-switch candidate" '
        "(commit d913a1dc4) is excluded from this rescore. Its own commit message "
        "documents that it feeds a per-fold regime-switched risk series directly "
        "into run_backtest, bypassing run_sdca_walk_forward's single-fixed-weight-"
        "vector interface -- there is no candidate_params dict that represents it, "
        "so it cannot go through run_sdca_walk_forward_vs_baseline without new "
        "plumbing (out of this phase's scope). Its driver script no longer exists "
        "on disk. In its place this table carries Task #93's Round 2 AND Round 3 as "
        "two separate rows (the plan named them together as one item).\n"
    )


def print_comparison(key: str, label: str, comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print(f"=== {key} ===")
    print(f"  {label}")
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

    extra_z_default = load_sdca_extra_z(dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None)
    extra_z_round23 = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=ROUND23_OSCILLATORS,
        extra_windows=ROUND23_EXTRA_WINDOWS,
    )

    print_exclusion_note()

    results: dict[str, WalkForwardBaselineComparison] = {}
    for key, label, candidate_params, evaluator in build_configs():
        extra_z = extra_z_round23 if key.startswith("task93_") else extra_z_default
        comparison = run_sdca_walk_forward_vs_baseline(
            dates,
            prices,
            candidate_params,
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label="curve_simulator",
            extra_z=extra_z,
            fold_weighting="duration",
        )
        results[key] = comparison
        print_comparison(key, label, comparison)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({key: c.model_dump() for key, c in results.items()}, indent=2, default=str)
    )
    print(f"wrote {OUT_PATH}")
    print(
        "\nDiagnostic re-score only -- never writes settings.json or "
        'RESEARCH_STATE.md\'s "current best validated candidate" section. Report '
        "this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
