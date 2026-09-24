#!/usr/bin/env python3
"""Phase 4 of the 2026-09-24 recalibration: combined search + calibration loop.

Chains Phase 1's floored 12-name weight search
(``run_full_pool_floored_search.py``'s primary 3:1 winner, duplicated
verbatim below per this repo's self-contained-script convention) into
Phase 3's widened, drawdown-capped, feasibility-aware curve search
(``curve_optimize_feasibility.search_wide_knee_curve_feasibility_aware`` --
already picks up the widened ``WIDE_KNEE_SEARCH_BOUNDS``/
``WIDE_KNEE_COARSE_GRID`` and the new ``MAX_DRAWDOWN_CAP_PCT`` gate with no
code change needed here), then runs the standard
``run_sdca_walk_forward_vs_baseline`` comparison (duration-weighted, with
sensitivity check) -- same mechanism as every prior ablation round
(``run_ablation_best_round_full_resolution.py``), so directly comparable to
round 8's baseline (-61.32% max drawdown, RESEARCH_STATE.md, unpromoted).

Unlike the curve search itself, ``crash_override`` is a walk-forward
/evaluator-level circuit breaker layered on top of whatever risk series and
curve shape are chosen (``curve_sim.evaluate_sdca_trial_curve_sim`` applies
it to the risk series right before the backtest) -- it plays no part in
``search_wide_knee_curve_feasibility_aware``'s in-sample curve-shape search.
Bound via ``functools.partial`` (same pattern as ``oscillators=`` in
``run_full_recalibration_feasible_curve.py``) since it's not part of
``SdcaTrialEvaluator``'s Protocol signature.

GATE (see RESEARCH_STATE.md "Standard trial protocol"): this script NEVER
writes settings.json or RESEARCH_STATE.md's "current best validated
candidate" section, regardless of result. Report this table to Chris for
explicit accept/reject.

Usage:
    uv run python scripts/run_recalibration_v1_full_resolution.py
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
    MAX_DRAWDOWN_CAP_PCT,
    MAX_DRAWDOWN_COMFORT_PCT,
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
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "recalibration_v1_full_resolution.json"

FULL_INITIAL_CASH = 10_000.0

# Frozen Stage 1 oscillator winners + macro/on-chain window override --
# identical to run_full_pool_floored_search.py (Phase 1 was re-run against
# these same windows) and every prior fixed-index round.
STAGE1_OSCILLATORS = SdcaOscillatorSpec(
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
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

# ---------------------------------------------------------------------------
# Phase 1 winner (primary 3:1 ratio), duplicated verbatim from the corrected
# re-run's .scratch/full_pool_floored_search_result.json ("primary_winner_3_1")
# -- every extra indicator sits at the 0.1 floor except weekly_monthly_macd
# (0.5) and power_law (1.0); every non-searched name (fast_crash_vol, adx,
# stochastic, vol_regime, halving_cycle, weekly_rsi, weekly_macd, sma_band,
# monthly_rsi, monthly_macd) is 0.0, matching SdcaCompositeWeights defaults.
# ---------------------------------------------------------------------------
PHASE1_WEIGHTS = SdcaCompositeWeights(
    power_law=1.0,
    m2=0.1,
    rs_eth=0.1,
    dxy=0.1,
    onchain_mvrv=0.1,
    onchain_asopr=0.1,
    onchain_puell=0.1,
    onchain_rhodl=0.1,
    onchain_addr_ratio=0.1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
    weekly_monthly_macd=0.5,
)


def build_crash_override_evaluator():
    """Bind crash_override on top of the plain curve-sim evaluator.

    Calibrated defaults (verified against real 2020-03-12 COVID-crash BTC
    data -- fires same-day, pushes risk straight to 95, not the "end of
    February" lateness this was meant to fix): trigger_z=-2.0, ramp_z=1.0,
    override_risk=95.0, window=14 -- all just the function's own defaults,
    so the only change needed is flipping crash_override_enabled=True.
    """
    return functools.partial(
        evaluate_sdca_trial_curve_sim,
        oscillators=STAGE1_OSCILLATORS,
        crash_override_enabled=True,
    )


def print_comparison(label: str, comparison: WalkForwardBaselineComparison) -> None:
    c, b = comparison.candidate, comparison.baseline
    print(f"=== {label} ===")
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
        f"beats_baseline_oos={comparison.beats_baseline_oos}"
    )
    for fs in c.fold_scores:
        oos = fs.out_of_sample
        print(
            f"    fold {fs.fold.fold}: OOS vs_flat_dca={oos.vs_flat_dca_pct:+7.2f}%  "
            f"max_drawdown_pct={oos.max_drawdown_pct:5.1f}%  capital_deployed={oos.capital_deployed_pct:5.1f}%  "
            f"feasible={fs.feasible}"
        )
    if c.holdout_metrics is not None:
        h = c.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:+7.2f}%  max_drawdown_pct={h.max_drawdown_pct:5.1f}%  "
            f"capital_deployed={h.capital_deployed_pct:5.1f}%"
        )
    print()


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
        trend_window=STAGE1_OSCILLATORS.power_law_trend_window,
    ).to_list()

    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=STAGE1_OSCILLATORS,
        extra_windows=EXTRA_WINDOWS,
    )

    print("=== Phase 1 weights (floored 12-name search, primary 3:1 ratio) ===")
    for name, value in PHASE1_WEIGHTS.model_dump().items():
        if value != 0.0:
            print(f"  {name}: {value:g}")

    risk_list = risk_from_weighted_z(dates, power_law_z, extra_z, PHASE1_WEIGHTS)
    risk_s = pl.Series("risk", risk_list, dtype=pl.Float64)

    print(
        f"\n=== Phase 3 curve search: widened bounds, drawdown-capped "
        f"(comfort={MAX_DRAWDOWN_COMFORT_PCT:g}%, cap={MAX_DRAWDOWN_CAP_PCT:g}%) ===\n"
        "running full-resolution feasibility-aware curve search (n_random=3000 default)..."
    )
    curve_result = search_wide_knee_curve_feasibility_aware(
        date_s, price_s, risk_s, initial_cash=FULL_INITIAL_CASH
    )
    print(
        f"  num_evaluations={curve_result.num_evaluations}  "
        f"num_capital_deployed_rejected={curve_result.num_capital_deployed_rejected}  "
        f"num_drawdown_rejected={curve_result.num_drawdown_rejected}"
    )
    print(f"  best shape: {curve_result.best.shape.model_dump()}")
    print(
        f"  best in-sample: risk_adjusted_return={curve_result.best.risk_adjusted_return:.4f}  "
        f"max_drawdown_pct={curve_result.best.base.max_drawdown_pct:.2f}%  "
        f"capital_deployed_pct={curve_result.best.capital_deployed_pct:.1f}%"
    )

    candidate_params = {
        **freeze_weight_params(PHASE1_WEIGHTS),
        **params_from_shape(curve_result.best.shape),
    }

    evaluator = build_crash_override_evaluator()
    print("\n=== Phase 4: full walk-forward vs. risk50-linear baseline, crash_override enabled ===")
    comparison = run_sdca_walk_forward_vs_baseline(
        dates,
        prices,
        candidate_params,
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator+crash_override",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    print_comparison("recalibration_v1_full_resolution", comparison)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(comparison.model_dump(), indent=2, default=str))
    print(f"wrote {OUT_PATH}")
    print(
        "\nDiagnostic walk-forward gate only -- this script NEVER writes settings.json or "
        "RESEARCH_STATE.md's \"current best validated candidate\" section, regardless of this "
        "result. Report this table to Chris for explicit accept/reject."
    )


if __name__ == "__main__":
    main()
