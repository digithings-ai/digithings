#!/usr/bin/env python3
"""Single composite, dual-timeframe valuation index: end-to-end search.

Chris's staged procedure (see ``.claude/plans`` "Single composite,
dual-timeframe valuation index" and ``DCA_VALUATION_FRAMEWORK.md``): one
composite risk index whose sub-indicators are individually tuned so some fit
long-term cycle extremes and some fit medium-term pullbacks/rallies, combined
into a single index scored against both timeframes at once
(``stage_a.combined_cycle_overlap_score``, long-term weighted 3x medium-term
by default).

1. Load BTC-USD (+ M2/ETH/DXY) data once.
2. For each tunable indicator (power_law, weekly_rsi, weekly_macd, sma_band,
   rs_eth), solo it and grid its own construction periods against the
   combined objective (``weight_search.search_oscillator_periods_by_cycle_overlap``).
   m2/dxy have no tunable periods -- they pass through unchanged. An
   indicator whose best score doesn't clear a noise baseline is dropped
   before step 4 (power_law is never dropped -- it's the anchor indicator
   and the explicit hedge floored back in at step 4).
2b. Exploration only: solo-score ``monthly_rsi``/``monthly_macd``
    (``price_oscillators.monthly_rsi_confluence_z`` /
    ``monthly_macd_confluence_z`` -- completed-calendar-month long-term leg
    instead of completed-ISO-week) against the same combined objective, for
    a direct comparison against weekly_rsi/weekly_macd's own step-2 score.
    Both have dormant, zero-weight fields on ``SdcaCompositeWeights`` (the
    minimal hook this search machinery needs) but neither is in
    ``EXTRA_INDICATOR_NAMES``/``build_extra_indicators``/settings.json, so
    neither participates in steps 3-5 below -- this only answers "does a
    monthly cadence track the long-term cycle better than weekly," not
    "should it ship."
3. Recombine all individually-optimized, surviving indicators at equal
   weight -- the baseline the reweight stage must beat.
4. Reweight the composite (``stage_a.optimize_stage_a_weights_combined``)
   with a diversification floor so no surviving indicator, including
   power_law, can be zeroed back out.
5. Sensitivity: rerun step 4 at long:medium = 2:1 and 5:1 so the ratio
   choice is visible before treating 3:1 as final.

This produces a diagnostic **index**, not a validated trading candidate --
curve/threshold/risk-adjusted-return optimization is a separate, later step
per Chris's explicit ordering.

Usage:
    python scripts/run_dual_timeframe_composite_search.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    rs_eth_confluence_z,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import (
    macd_confluence_z,
    monthly_macd_confluence_z,
    monthly_rsi_confluence_z,
    rsi_confluence_z,
    sma_band_confluence_z,
)
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    optimize_stage_a_weights_combined,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

PRICE_OSC_TUNABLE = ("weekly_rsi", "weekly_macd", "sma_band", "rs_eth")

# Candidate period grids: each indicator's current default plus the
# already-smoke-tested alternates from RESEARCH_STATE.md's backlog item 2
# ("RSI 8/7, MACD 6/13 or 8/17, SMA-band 60/10, rs_eth 90/45,
# power_law-trend 120d"), applied jointly for the first time here against
# the combined long+medium objective.
POWER_LAW_CANDIDATES = [{"trend_window": w} for w in (90, 120, 150, 180, 240, 365)]
# Widened from the original ~4-combo grid: the first pass's winning periods
# (8/7, and default 12/26 for MACD) barely moved off library defaults and
# scored far below power_law/sma_band solo -- widen to see whether that's a
# genuine optimum or just a grid too coarse to find a better one.
WEEKLY_RSI_CANDIDATES = [
    {"weekly_length": w, "daily_length": d}
    for w in (5, 7, 8, 9, 10, 12, 14, 18, 21, 26)
    for d in (5, 7, 9, 10, 14)
]
WEEKLY_MACD_CANDIDATES = [
    {"weekly_fast": wf, "weekly_slow": ws, "daily_fast": df, "daily_slow": ds}
    for wf, ws in ((4, 9), (5, 10), (6, 13), (8, 17), (10, 21), (12, 26), (16, 35))
    for df, ds in ((6, 13), (8, 17), (12, 26))
]
# New this round: same period space as the weekly grids above, but scored
# with a completed-calendar-month long-term leg instead of a completed-ISO-
# week one (see module docstring's step 2b) -- exploration only, not fed
# into steps 3-5.
# monthly_length widened further (2026-09-05): the first monthly pass's
# winner (3) sat at the grid's short edge, so extend down to 2 (RSI's
# mathematical floor -- length=1 degenerates to a single-delta RSI) and add
# 4/6 for resolution, to see whether the score keeps climbing toward the
# floor (overfit signal) or peaks at an interior value.
MONTHLY_RSI_CANDIDATES = [
    {"monthly_length": w, "daily_length": d}
    for w in (2, 3, 4, 5, 6, 7, 9, 12, 14, 18)
    for d in (5, 7, 9, 10, 14)
]
MONTHLY_MACD_CANDIDATES = [
    {"monthly_fast": wf, "monthly_slow": ws, "daily_fast": df, "daily_slow": ds}
    for wf, ws in ((3, 6), (4, 9), (5, 10), (6, 13), (8, 17), (12, 26))
    for df, ds in ((6, 13), (8, 17), (12, 26))
]
SMA_BAND_CANDIDATES = [
    {"slow_window": 90, "fast_window": 20},
    {"slow_window": 60, "fast_window": 10},
    {"slow_window": 120, "fast_window": 30},
]
RS_ETH_CANDIDATES = [
    {"slow_window": 90, "fast_window": 30},
    {"slow_window": 90, "fast_window": 45},
    {"slow_window": 60, "fast_window": 20},
]

# SdcaOscillatorSpec field names each indicator's winning params map onto.
SPEC_FIELD_MAP = {
    "power_law": {"trend_window": "power_law_trend_window"},
    "weekly_rsi": {"weekly_length": "rsi_length", "daily_length": "daily_rsi_length"},
    "weekly_macd": {
        "weekly_fast": "macd_fast",
        "weekly_slow": "macd_slow",
        "daily_fast": "macd_daily_fast",
        "daily_slow": "macd_daily_slow",
    },
    "sma_band": {"slow_window": "sma_band_window", "fast_window": "sma_band_fast_window"},
    "rs_eth": {"slow_window": "rs_eth_window", "fast_window": "rs_eth_fast_window"},
    # Informational only -- these aren't real SdcaOscillatorSpec fields yet
    # (see SdcaCompositeWeights.monthly_rsi/monthly_macd's docstring note).
    "monthly_rsi": {"monthly_length": "monthly_rsi_length", "daily_length": "daily_rsi_length"},
    "monthly_macd": {
        "monthly_fast": "monthly_macd_fast",
        "monthly_slow": "monthly_macd_slow",
        "daily_fast": "macd_daily_fast",
        "daily_slow": "macd_daily_slow",
    },
}


def _spec_fields(indicator_name: str, params: dict[str, int]) -> dict[str, int]:
    mapping = SPEC_FIELD_MAP[indicator_name]
    return {mapping[k]: v for k, v in params.items()}


def _noise_baseline_objective(
    dates: list,
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float,
    medium_weight: float,
) -> float:
    """Objective for a constant-zero indicator -- the bar step 2 must clear."""
    zeros = [0.0] * len(dates)
    dummy_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)
    risk = risk_from_weighted_z(dates, zeros, {"m2": zeros}, dummy_weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    ).objective


def _print_score(label: str, score: CombinedCycleOverlapScore) -> None:
    print(
        f"  {label}: long={score.long.objective:.2f} "
        f"medium={score.medium.objective:.2f} combined={score.objective:.2f} "
        f"(ratio {score.long_weight:g}:{score.medium_weight:g})"
    )


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    sources = load_sdca_extra_sources(data_path.parent)
    print(f"extras available: {sorted(base_extra_z)}\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    def compute_power_law_z(p: dict[str, int]) -> list[float | None]:
        return power_law_confluence_z(
            date_s, price_s, rails["low"], rails["median"], rails["high"],
            trend_window=p["trend_window"],
        ).to_list()

    def compute_weekly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return rsi_confluence_z(
            date_s, price_s, weekly_length=p["weekly_length"], daily_length=p["daily_length"],
        ).to_list()

    def compute_weekly_macd_z(p: dict[str, int]) -> list[float | None]:
        return macd_confluence_z(
            date_s, price_s,
            weekly_fast=p["weekly_fast"], weekly_slow=p["weekly_slow"],
            daily_fast=p["daily_fast"], daily_slow=p["daily_slow"],
        ).to_list()

    def compute_monthly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return monthly_rsi_confluence_z(
            date_s, price_s, monthly_length=p["monthly_length"], daily_length=p["daily_length"],
        ).to_list()

    def compute_monthly_macd_z(p: dict[str, int]) -> list[float | None]:
        return monthly_macd_confluence_z(
            date_s, price_s,
            monthly_fast=p["monthly_fast"], monthly_slow=p["monthly_slow"],
            daily_fast=p["daily_fast"], daily_slow=p["daily_slow"],
        ).to_list()

    def compute_sma_band_z(p: dict[str, int]) -> list[float | None]:
        return sma_band_confluence_z(
            date_s, price_s, slow_window=p["slow_window"], fast_window=p["fast_window"],
        ).to_list()

    eth_available = sources.eth_dates is not None and sources.eth_close is not None

    def compute_rs_eth_z(p: dict[str, int]) -> list[float | None]:
        return rs_eth_confluence_z(
            date_s, price_s, sources.eth_dates, sources.eth_close,
            slow_window=p["slow_window"], fast_window=p["fast_window"],
        ).to_list()

    tunable = [
        ("power_law", POWER_LAW_CANDIDATES, compute_power_law_z),
        ("weekly_rsi", WEEKLY_RSI_CANDIDATES, compute_weekly_rsi_z),
        ("weekly_macd", WEEKLY_MACD_CANDIDATES, compute_weekly_macd_z),
        ("sma_band", SMA_BAND_CANDIDATES, compute_sma_band_z),
        ("rs_eth", RS_ETH_CANDIDATES, compute_rs_eth_z if eth_available else None),
    ]

    print("=== Stage 2: per-indicator period search (combined objective) ===\n")
    # Default-period power-law z; ignored by search_oscillator_periods_by_cycle_overlap
    # when the target indicator IS power_law (it solos the candidate z-series instead).
    default_power_law_z = compute_power_law_z({"trend_window": 180})
    best_params: dict[str, dict[str, int]] = {}
    best_scores: dict[str, CombinedCycleOverlapScore] = {}
    surviving: list[str] = []
    for name, candidates, compute_fn in tunable:
        if compute_fn is None:
            print(f"[{name}] SKIPPED -- no ETH data available\n")
            continue
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=name,
            param_candidates=candidates,
            compute_indicator_z=compute_fn,
            base_power_law_z=default_power_law_z,
            base_extra_z=base_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
            long_weight=long_weight,
            medium_weight=medium_weight,
        )
        best_params[name] = dict(result.best.params)
        best_scores[name] = result.best.score
        beats_noise = result.best.score.objective > noise_objective
        if name != "power_law":
            if beats_noise:
                surviving.append(name)
            status = "OK" if beats_noise else "DROP (<= noise baseline)"
        else:
            status = "OK (anchor, never dropped)"
        print(f"[{name}] {status}")
        print(f"  best params: {result.best.params}")
        print(f"  SdcaOscillatorSpec fields: {_spec_fields(name, result.best.params)}")
        _print_score("score", result.best.score)
        print()

    print(f"surviving extras after step 2: {surviving}\n")

    print("=== Stage 2b: monthly RSI/MACD exploration (diagnostic only) ===\n")
    monthly_tunable = [
        ("monthly_rsi", MONTHLY_RSI_CANDIDATES, compute_monthly_rsi_z, "weekly_rsi"),
        ("monthly_macd", MONTHLY_MACD_CANDIDATES, compute_monthly_macd_z, "weekly_macd"),
    ]
    for name, candidates, compute_fn, weekly_counterpart in monthly_tunable:
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=name,
            param_candidates=candidates,
            compute_indicator_z=compute_fn,
            base_power_law_z=default_power_law_z,
            base_extra_z=base_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
            long_weight=long_weight,
            medium_weight=medium_weight,
        )
        beats_noise = result.best.score.objective > noise_objective
        status = "OK" if beats_noise else "DROP (<= noise baseline)"
        print(f"[{name}] {status} (not fed into steps 3-5 -- comparison only)")
        print(f"  best params: {result.best.params}")
        print(f"  SdcaOscillatorSpec fields (informational): {_spec_fields(name, result.best.params)}")
        _print_score("score", result.best.score)
        weekly_score = best_scores.get(weekly_counterpart)
        if weekly_score is not None:
            print(f"  vs. {weekly_counterpart} best params {best_params[weekly_counterpart]}:")
            _print_score(f"  {weekly_counterpart} score", weekly_score)
        print()

    # Step 3: recombine surviving indicators (their optimized periods) at equal weight.
    final_power_law_z = compute_power_law_z(best_params["power_law"])
    final_extra_z = dict(base_extra_z)
    compute_by_name = {
        "weekly_rsi": compute_weekly_rsi_z,
        "weekly_macd": compute_weekly_macd_z,
        "sma_band": compute_sma_band_z,
        "rs_eth": compute_rs_eth_z if eth_available else None,
    }
    for name in surviving:
        final_extra_z[name] = compute_by_name[name](best_params[name])

    search_names = tuple(
        n for n in EXTRA_INDICATOR_NAMES
        if (n in PRICE_OSC_TUNABLE and n in surviving)
        or (n not in PRICE_OSC_TUNABLE and n in final_extra_z)
    )
    print(f"search_names for steps 3-4: {search_names}\n")

    n_total = len(search_names) + 1  # +1 for power_law
    eq_weight = 1.0 / n_total
    equal_weights = SdcaCompositeWeights(
        power_law=eq_weight, **{n: eq_weight for n in search_names}
    )
    equal_risk = risk_from_weighted_z(dates, final_power_law_z, final_extra_z, equal_weights)
    equal_score = combined_cycle_overlap_score(
        dates, equal_risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    )
    print("=== Stage 3: equal-weight composite (baseline for reweighting) ===\n")
    print(f"  weights: {equal_weights.model_dump()}")
    _print_score("score", equal_score)
    print()

    # Step 4: reweight the aggregate with a diversification floor.
    grid = (0.0, 0.25, 0.5, 0.75, 1.0)
    floor = 0.25
    print("=== Stage 4: aggregate reweight (floor-diversified, 3:1) ===\n")
    final_result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=final_power_law_z,
        extra_z=final_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=search_names,
        grid=grid,
        power_law_grid=grid,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=floor,
    )
    print(f"  evaluated: {final_result.num_evaluations} combinations")
    print(f"  weights: {final_result.weights.model_dump()}")
    _print_score("score", final_result.score)
    print()

    # Step 5: sensitivity sweep on the long:medium ratio.
    print("=== Stage 5: long:medium ratio sensitivity ===\n")
    sensitivity_results = {3.0: final_result}
    for lw in (2.0, 5.0):
        result_lw = optimize_stage_a_weights_combined(
            dates,
            power_law_z=final_power_law_z,
            extra_z=final_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
            search_names=search_names,
            grid=grid,
            power_law_grid=grid,
            long_weight=lw,
            medium_weight=medium_weight,
            min_weight_floor=floor,
        )
        sensitivity_results[lw] = result_lw
        print(f"  ratio {lw:g}:1 -> weights: {result_lw.weights.model_dump()}")
        _print_score("  score", result_lw.score)
        print()

    # Summary table.
    print("=== Summary ===\n")
    header = f"{'config':<28} {'long':>8} {'medium':>8} {'combined':>10}"
    print(header)
    print("-" * len(header))
    print(
        f"{'equal-weight baseline':<28} {equal_score.long.objective:>8.2f} "
        f"{equal_score.medium.objective:>8.2f} {equal_score.objective:>10.2f}"
    )
    for lw, result_lw in sorted(sensitivity_results.items()):
        label = f"reweighted ({lw:g}:1)"
        print(
            f"{label:<28} {result_lw.score.long.objective:>8.2f} "
            f"{result_lw.score.medium.objective:>8.2f} {result_lw.score.objective:>10.2f}"
        )


if __name__ == "__main__":
    run()
