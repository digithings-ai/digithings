#!/usr/bin/env python3
"""Single reproducible driver for the full SDCA recalibration (Stage 1 -> Stage 4).

This chains the four stages of this session's recalibration into one script:

  Stage 1 -- per-indicator oscillator period search
             (``scripts/run_dual_timeframe_composite_search.py``, frozen here
             as ``STAGE1_OSCILLATORS``; not re-run -- that search is a
             multi-minute grid over every indicator's own construction
             period(s)).
  Stage 2 -- 17-indicator floor-diversified aggregate reweight
             (``scripts/run_aggregate_reweight_full17.py`` /
             ``.scratch/aggregate_reweight_full17_result.json``, frozen here
             as ``STAGE2_WEIGHTS``; not re-run -- that search is a
             multiprocessing exhaustive product).
  Stage 3 -- wide-knee curve search frozen against Stage 1+2
             (``.scratch/run_stage3_curve_search.py`` /
             ``.scratch/stage3_curve_search_result.json``, frozen here as
             ``STAGE3_CURVE``; not re-run -- that search is a
             ``curve_optimize.search_wide_knee_curve`` grid, in-sample only).
  Stage 4 -- walk-forward OOS validation gate (the actual computation this
             script performs): ``optimize.run_sdca_walk_forward`` with
             ``evaluator=curve_sim.evaluate_sdca_trial_curve_sim``,
             ``rails_fitter=optimize.btc_power_law_rails_fitter``. This is
             the SAME walk-forward mechanism (3 expanding-IS/rolling-OOS
             folds + a held-out tail + a +/-5% sensitivity sweep) that
             produced the currently validated baseline's +84.90% mean OOS
             vs-flat-DCA number and the live-settings 5-weight config's
             -51.28% number (RESEARCH_STATE.md "Current best validated
             candidate" / "Known discrepancy" sections) -- so this trial's
             numbers are directly comparable to those.

Stages 1-3 only PRINT their frozen inputs here for a single-command
reproducible record of the whole chain; they do not re-search. Stage 4 is
the only stage that runs a live computation, and its full per-fold table is
the actual validation gate.

Data-loading plumbing is reused unchanged from
``scripts/run_dual_timeframe_composite_search.py``
(``optimize.load_sdca_ohlcv``, ``optimize.load_sdca_extra_z``,
``power_law_zscore.power_law_confluence_z``, ``cycle_windows.SdcaCycleWindows``)
-- Stage 1/2's diagnostic header reuses the same full-history rails +
power-law z + cycle-window objects those scripts compute, purely for
reporting; Stage 4's actual walk-forward call has its own per-fold IS-only
rails refit (``btc_power_law_rails_fitter``, #3173 rails-leakage rule) and
never touches that full-history model.

``STAGE1_OSCILLATORS`` is bound onto the Stage 4 evaluator via
``functools.partial`` (per ``curve_sim.evaluate_sdca_trial_curve_sim``'s
documented pattern) and passed to ``load_sdca_extra_z`` so Stage 4 scores
the SAME index Stage 3's curve was fit against -- oscillator periods stay
frozen at Stage 1's winners throughout, never silently reverting to
production defaults.

GATE (see RESEARCH_STATE.md "Standard trial protocol" step 6): this script
NEVER writes ``settings.json`` or RESEARCH_STATE.md's "Current best
validated candidate" section. It only qualifies as a candidate for that
section once ``beats_flat_dca_oos=True`` AND the sensitivity report says
``stable=True`` -- and even then only on Chris's explicit accept, never
this script's own say-so.

Usage:
    uv run python scripts/run_full_recalibration.py
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "full_recalibration_walk_forward_result.json"

# ---------------------------------------------------------------------------
# Stage 1 winners (run_dual_timeframe_composite_search.py per-indicator period
# search) -- copied verbatim from .scratch/run_stage3_curve_search.py's
# STAGE1_OSCILLATORS, which cross-checked every shared confluence-pair field
# agrees. m2/dxy/onchain_*/fear_greed periods are NOT controllable via
# SdcaOscillatorSpec (build_extra_indicators() only takes one shared
# window=90 for those five) -- documented caveat, not fixed here.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Stage 2 winner (run_aggregate_reweight_full17.py 17-indicator
# floor-diversified 3:1 long:medium reweight) -- the final trial's weights.
# ---------------------------------------------------------------------------
STAGE2_WEIGHTS = SdcaCompositeWeights(
    power_law=1,
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
    weekly_monthly_macd=1,
    weekly_rsi=0.1,
    weekly_macd=0.1,
    sma_band=0.95,
    monthly_rsi=0.1,
    monthly_macd=0.1,
)

# ---------------------------------------------------------------------------
# Stage 3 winner (.scratch/run_stage3_curve_search.py wide-knee curve search,
# frozen against Stage 1 oscillator periods + Stage 2 weights above).
# ---------------------------------------------------------------------------
STAGE3_CURVE = SdcaCurveShape(
    buy_max_rate=29.8104,
    buy_knee_risk=34.4041,
    sell_knee_risk=76.0423,
    sell_max_rate=94.348,
    buy_curvature=1.4072,
    sell_curvature=1.5252,
)


def print_stage1_summary(dates: list, prices: list) -> None:
    print("=== Stage 1: oscillator period winners (frozen, not re-searched) ===")
    for field, value in STAGE1_OSCILLATORS.model_dump().items():
        print(f"  {field}: {value}")

    # Informational only -- full-history rails + power-law z, purely for a
    # sanity-check summary stat. Stage 4 below never uses this full-history
    # model; it refits rails per fold on the IS window only (#3173).
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = BtcPowerLawRiskModel(load_coefficients()).rails(date_s)
    pl_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"],
        trend_window=STAGE1_OSCILLATORS.power_law_trend_window,
    )
    z_stats = pl_z.drop_nulls()
    print(
        f"  power_law_confluence_z (trend_window={STAGE1_OSCILLATORS.power_law_trend_window}, "
        f"full-history diagnostic only): min={z_stats.min():.2f} median={z_stats.median():.2f} "
        f"max={z_stats.max():.2f}"
    )

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    print(
        f"  cycle windows: long={len(long_windows.windows)} pins, "
        f"medium={len(medium_windows.windows)} pins (Stage 1/2 scoring context only)"
    )


def print_stage2_summary() -> None:
    print("\n=== Stage 2: 17-indicator floor-diversified aggregate reweight (frozen) ===")
    for name, value in STAGE2_WEIGHTS.model_dump().items():
        if value != 0.0:
            print(f"  {name}: {value:g}")


def print_stage3_summary() -> None:
    print("\n=== Stage 3: wide-knee curve search, frozen against Stage 1+2 index (frozen) ===")
    for field, value in STAGE3_CURVE.model_dump().items():
        print(f"  {field}: {value:g}")


def build_stage4_trial() -> dict[str, float | int | str]:
    """Stage 2 weights + Stage 3 curve shape as one ``run_sdca_walk_forward`` trial dict."""
    trial: dict[str, float | int | str] = dict(freeze_weight_params(STAGE2_WEIGHTS))
    trial.update(STAGE3_CURVE.model_dump())
    return trial


def load_stage4_inputs() -> tuple[list, list, dict]:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None, oscillators=STAGE1_OSCILLATORS
    )
    return dates, prices, extra_z


def run_stage4_walk_forward(dates: list, prices: list, extra_z: dict) -> SdcaWalkForwardResult:
    trial = build_stage4_trial()
    # oscillators is outside SdcaTrialEvaluator's Protocol signature (per
    # curve_sim.evaluate_sdca_trial_curve_sim's docstring) -- bind it so the
    # power-law leg's trend window matches Stage 1's winner on every fold,
    # the same index Stage 3's curve was fit against.
    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=STAGE1_OSCILLATORS)
    return run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
    )


def print_stage4_fold_table(result: SdcaWalkForwardResult) -> None:
    print(f"\n=== Stage 4: walk-forward OOS validation gate ({result.evaluator_label}) ===")
    print(f"{len(result.folds)} folds, holdout tail {result.holdout[0]}..{result.holdout[1]}\n")
    for fs in result.fold_scores:
        f = fs.fold
        is_m, oos_m = fs.in_sample, fs.out_of_sample
        print(
            f"  fold {f.fold}: IS {f.is_start}..{f.is_end}  OOS {f.oos_start}..{f.oos_end}\n"
            f"    IS  vs_flat_dca={is_m.vs_flat_dca_pct:+8.2f}%  vs_lump={is_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={is_m.capital_deployed_pct:5.1f}%  max_dd={is_m.max_drawdown_pct:5.1f}%\n"
            f"    OOS vs_flat_dca={oos_m.vs_flat_dca_pct:+8.2f}%  vs_lump={oos_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={oos_m.capital_deployed_pct:5.1f}%  max_dd={oos_m.max_drawdown_pct:5.1f}%  "
            f"oos_minus_is={oos_m.vs_flat_dca_pct - is_m.vs_flat_dca_pct:+6.2f}  feasible={fs.feasible}"
        )
    print(
        f"\n  mean IS vs_flat_dca={result.mean_is_vs_flat_dca_pct:+.2f}%  "
        f"mean OOS vs_flat_dca={result.mean_oos_vs_flat_dca_pct:+.2f}%  "
        f"IS-OOS gap (is_oos_gap_pct = mean_is - mean_oos)={result.is_oos_gap_pct:+.2f}"
    )
    print(f"  beats_flat_dca_oos={result.beats_flat_dca_oos}")
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"  holdout: vs_flat_dca={h.vs_flat_dca_pct:+.2f}%  vs_lump={h.vs_lump_pct:+.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.1f}%  max_dd={h.max_drawdown_pct:.1f}%"
        )
    s = result.sensitivity
    print(
        f"\n  sensitivity (+/-{s.frac:g} on every numeric param, {s.neighbor_count} valid neighbors):\n"
        f"    max_abs_delta_oos_pct={s.max_abs_delta_oos_pct:.2f}  "
        f"spike_threshold_pct={s.spike_threshold_pct:g}  stable={s.stable}"
    )
    print(f"\n  num_evaluations={result.num_evaluations}  objective={result.objective.model_dump()}")


def main() -> None:
    dates, prices, extra_z = load_stage4_inputs()
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"extras available: {sorted(extra_z)}\n")

    print_stage1_summary(dates, prices)
    print_stage2_summary()
    print_stage3_summary()

    result = run_stage4_walk_forward(dates, prices, extra_z)
    print_stage4_fold_table(result)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result.model_dump(), indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")

    qualifies = result.beats_flat_dca_oos and result.sensitivity.stable
    infeasible_folds = [fs.fold.fold for fs in result.fold_scores if not fs.feasible]
    print(
        f"\nOVERALL: beats_flat_dca_oos={result.beats_flat_dca_oos}  "
        f"sensitivity_stable={result.sensitivity.stable}  "
        f"qualifies_as_new_baseline_candidate={qualifies}"
    )
    if infeasible_folds:
        print(
            f"  NOTE: fold(s) {infeasible_folds} are infeasible under the objective's "
            f"capital-deployed floor / drawdown cap (SdcaOptimizeObjective) -- "
            f"mean_oos_vs_flat_dca_pct and beats_flat_dca_oos are plain averages over ALL "
            f"folds regardless of feasibility (see optimize.py's _mean_oos/_mean_is), so a "
            f"positive beats_flat_dca_oos here does not by itself mean every fold cleared the "
            f"feasibility rails -- check the per-fold feasible= flags above."
        )
    print(
        "\nDiagnostic walk-forward gate only -- this script NEVER writes settings.json or "
        "RESEARCH_STATE.md's \"current best validated candidate\" section, regardless of this "
        "result. Report this table to Chris for explicit accept/reject; qualifying for the gate "
        "(beats_flat_dca_oos=True AND sensitivity stable=True) is necessary but not sufficient -- "
        "only his explicit accept promotes a candidate."
    )


if __name__ == "__main__":
    main()
