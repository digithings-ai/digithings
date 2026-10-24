#!/usr/bin/env python3
"""Extend the dual-timeframe composite search to the full 17-indicator
universe, per Chris's methodology pivot (2026-09-21):

    "our strategy with power law, M2 and DXY isn't sufficient. It lacks
    indicator diversification... even if we sacrifice a bit of performance,
    being able to diversify our indicator pool is a long-term gain... I
    think the more indicators we could add, the better. Especially the
    on-chain ones (MVRV, aSOPR)... leave the buying and selling curves out
    of [the index-search stage]... optimize those curves once we find the
    right aggregate index to fit."

``run_dual_timeframe_composite_search.py`` already implements exactly this
staged approach (period-search each tunable indicator -> floor-diversified
reweight, curve-free throughout -- Stage A's objective never runs a
backtest) but only covers 5 of the 17 names in ``EXTRA_INDICATOR_NAMES``:
power_law, weekly_rsi, weekly_macd, sma_band, rs_eth. It never touches the
6 on-chain/sentiment indicators (onchain_mvrv, onchain_asopr, onchain_puell,
onchain_rhodl, onchain_addr_ratio, fear_greed) Chris explicitly asked for,
nor the other technical extras (monthly_rsi, monthly_macd,
weekly_monthly_rsi, weekly_monthly_macd, m2, dxy already included as m2/dxy
in the baseline but never period-searched since they have no periods).

On-chain/sentiment indicators have no tunable construction period (they're
sourced series, not oscillators with a window/length) -- ``load_sdca_extra_z``
already returns their production z-series. So Stage 1 for these is a
solo-score only (no grid), reusing the identical mechanism
``search_oscillator_periods_by_cycle_overlap`` uses internally: solo the
indicator (weight=1, else 0) and score via
``stage_a.combined_cycle_overlap_score``, checked against the same noise
baseline used to drop tunable indicators.

Stage 2 (floor-diversified reweight) then runs across every surviving
indicator -- power_law, m2, dxy, rs_eth, the tunable technicals, and the
on-chain/sentiment set together -- via the existing
``optimize_stage_a_weights_combined``, ``min_weight_floor=0.1`` (same
convention as the previously-approved plan). No curve is used anywhere in
this script, consistent with Chris's explicit ordering and Stage A's
existing curve-free objective.

Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- report the
surviving indicator set and floor-respecting weight mix to Chris before any
curve optimization (a separate, later stage) or walk-forward OOS validation
(Stage 4, required before any baseline proposal per the standing gate).

Usage:
    uv run python -m scripts.run_full_indicator_diversification_search
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
    rsi_confluence_z,
    sma_band_confluence_z,
)
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    optimize_stage_a_weights_combined,
    optimize_stage_a_weights_combined_multi_ratio,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Period-tunable indicators (existing coverage from
# run_dual_timeframe_composite_search.py) -- unchanged period grids.
POWER_LAW_CANDIDATES = [{"trend_window": w} for w in (90, 120, 150, 180, 240, 365)]
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

# Period-less indicators: no construction window to search -- solo-scored
# once against load_sdca_extra_z's production series. m2/dxy already ride
# in the validated baseline (never dropped here); the 6 on-chain/sentiment
# names are the new additions Chris asked for.
PERIODLESS_NAMES = (
    "m2",
    "dxy",
    "onchain_mvrv",
    "onchain_asopr",
    "onchain_puell",
    "onchain_rhodl",
    "onchain_addr_ratio",
    "fear_greed",
)

FLOOR = 0.1
# Coarse grid: with up to 12 surviving indicators, a 5-point grid explodes
# to 5^12+ evaluations (itertools.product over search_names) -- effectively
# never finishes. Per the previously-approved plan's own warning about this
# exact blowup, use a coarse 3-point grid here; a local refinement pass
# (narrowed +/-0.15 around the coarse winner) can follow once this
# diagnostic result is in and Chris has a chance to weigh in on floor/grid
# tradeoffs given his diversification-over-performance framing.
GRID = (0.1, 0.55, 1.0)


def _noise_baseline_objective(
    dates: list, long_windows: SdcaCycleWindows, medium_windows: SdcaCycleWindows,
    *, long_weight: float, medium_weight: float,
) -> float:
    zeros = [0.0] * len(dates)
    dummy_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)
    risk = risk_from_weighted_z(dates, zeros, {"m2": zeros}, dummy_weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    ).objective


def _print_score(label: str, score: CombinedCycleOverlapScore) -> None:
    print(
        f"  {label}: long={score.long.objective:.2f} medium={score.medium.objective:.2f} "
        f"combined={score.objective:.2f} (ratio {score.long_weight:g}:{score.medium_weight:g})"
    )


def _score_periodless(
    dates: list, name: str, z_series: list, long_windows, medium_windows, long_weight, medium_weight
) -> CombinedCycleOverlapScore:
    weights = SdcaCompositeWeights(power_law=0.0, **{name: 1.0})
    risk = risk_from_weighted_z(dates, [0.0] * len(dates), {name: z_series}, weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    sources = load_sdca_extra_sources(cache_dir)
    print(f"extras available: {sorted(base_extra_z)}\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    def compute_power_law_z(p):
        return power_law_confluence_z(
            date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=p["trend_window"],
        ).to_list()

    def compute_weekly_rsi_z(p):
        return rsi_confluence_z(date_s, price_s, weekly_length=p["weekly_length"], daily_length=p["daily_length"]).to_list()

    def compute_weekly_macd_z(p):
        return macd_confluence_z(
            date_s, price_s, weekly_fast=p["weekly_fast"], weekly_slow=p["weekly_slow"],
            daily_fast=p["daily_fast"], daily_slow=p["daily_slow"],
        ).to_list()

    def compute_sma_band_z(p):
        return sma_band_confluence_z(date_s, price_s, slow_window=p["slow_window"], fast_window=p["fast_window"]).to_list()

    eth_available = sources.eth_dates is not None and sources.eth_close is not None

    def compute_rs_eth_z(p):
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

    print("=== Stage 1a: per-indicator period search (tunable, combined objective) ===\n")
    default_power_law_z = compute_power_law_z({"trend_window": 180})
    best_params: dict[str, dict] = {}
    final_extra_z: dict[str, list] = dict(base_extra_z)
    surviving: list[str] = []
    for name, candidates, compute_fn in tunable:
        if compute_fn is None:
            print(f"[{name}] SKIPPED -- no ETH data available\n")
            continue
        result = search_oscillator_periods_by_cycle_overlap(
            dates, indicator_name=name, param_candidates=candidates, compute_indicator_z=compute_fn,
            base_power_law_z=default_power_law_z, base_extra_z=base_extra_z,
            long_windows=long_windows, medium_windows=medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        )
        best_params[name] = dict(result.best.params)
        beats_noise = result.best.score.objective > noise_objective
        if name != "power_law":
            if beats_noise:
                surviving.append(name)
                final_extra_z[name] = compute_fn(result.best.params)
            status = "OK" if beats_noise else "DROP (<= noise baseline)"
        else:
            status = "OK (anchor, never dropped)"
            final_power_law_z = compute_fn(result.best.params)
        print(f"[{name}] {status}  best params: {result.best.params}")
        _print_score("score", result.best.score)
        print()

    print("=== Stage 1b: period-less indicators (solo-score, no period to search) ===\n")
    for name in PERIODLESS_NAMES:
        z_series = base_extra_z.get(name)
        if z_series is None:
            print(f"[{name}] SKIPPED -- no source data cached\n")
            continue
        score = _score_periodless(dates, name, z_series, long_windows, medium_windows, long_weight, medium_weight)
        beats_noise = score.objective > noise_objective
        # m2/dxy ride in unconditionally (already part of the validated baseline);
        # the new on-chain/sentiment names must clear the noise bar like any extra.
        if name in ("m2", "dxy") or beats_noise:
            surviving.append(name)
            status = "OK (anchor macro, never dropped)" if name in ("m2", "dxy") else "OK"
        else:
            status = "DROP (<= noise baseline)"
        print(f"[{name}] {status}")
        _print_score("score", score)
        print()

    print(f"surviving indicators (excl. power_law anchor): {surviving}\n")

    search_names = tuple(n for n in EXTRA_INDICATOR_NAMES if n in surviving)

    n_total = len(search_names) + 1
    eq_weight = 1.0 / n_total
    equal_weights = SdcaCompositeWeights(power_law=eq_weight, **{n: eq_weight for n in search_names})
    equal_risk = risk_from_weighted_z(dates, final_power_law_z, final_extra_z, equal_weights)
    equal_score = combined_cycle_overlap_score(
        dates, equal_risk, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight,
    )
    print("=== Stage 2 (baseline): equal-weight composite over full surviving set ===\n")
    print(f"  weights: {equal_weights.model_dump()}")
    _print_score("score", equal_score)
    print()

    print(f"=== Stage 3: floor-diversified reweight (floor={FLOOR}, 3:1) ===\n")
    final_result = optimize_stage_a_weights_combined(
        dates, power_law_z=final_power_law_z, extra_z=final_extra_z,
        long_windows=long_windows, medium_windows=medium_windows,
        search_names=search_names, grid=GRID, power_law_grid=GRID,
        long_weight=long_weight, medium_weight=medium_weight, min_weight_floor=FLOOR,
    )
    print(f"  evaluated: {final_result.num_evaluations} combinations")
    print(f"  weights: {final_result.weights.model_dump()}")
    _print_score("score", final_result.score)
    print()

    print("=== Stage 4: long:medium ratio sensitivity ===\n")
    for lw in (2.0, 5.0):
        result_lw = optimize_stage_a_weights_combined(
            dates, power_law_z=final_power_law_z, extra_z=final_extra_z,
            long_windows=long_windows, medium_windows=medium_windows,
            search_names=search_names, grid=GRID, power_law_grid=GRID,
            long_weight=lw, medium_weight=medium_weight, min_weight_floor=FLOOR,
        )
        print(f"  ratio {lw:g}:1 -> weights: {result_lw.weights.model_dump()}")
        _print_score("  score", result_lw.score)
        print()

    print(
        "Diagnostic only -- no curve used anywhere above. Not touching RESEARCH_STATE.md/settings.json -- "
        "report the surviving indicator set + floor-respecting weight mix to Chris before curve optimization "
        "(a separate later stage) or Stage 4 walk-forward OOS validation."
    )


if __name__ == "__main__":
    run()
