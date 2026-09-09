#!/usr/bin/env python3
"""Aggregate valuation index search: merged weekly+monthly RSI/MACD confluence.

Chris (2026-09-09): fold the new ``weekly_monthly_rsi``/``weekly_monthly_macd``
confluence indicators (monthly long-term leg + weekly medium-term leg, no
daily leg -- see ``price_oscillators.weekly_monthly_rsi_confluence_z`` /
``weekly_monthly_macd_confluence_z``) into the aggregate composite, **in
place of** the older separate ``weekly_rsi``/``monthly_rsi``/``weekly_macd``/
``monthly_macd`` legs (each of those confluenced its own timeframe against a
daily leg instead of against each other). Confirmed via ``AskUserQuestion``:
replace, don't add alongside.

New candidate pool (7 total): power_law, m2, dxy, rs_eth, sma_band,
weekly_monthly_rsi, weekly_monthly_macd.

Same staged procedure as ``run_dual_timeframe_composite_search.py``, minus
that script's Stage 2b/3b/4b/5b "all-9" machinery (not applicable here --
Chris chose replace, so there is no separate legacy-vs-new comparison to
run):

1. Load BTC-USD (+ M2/ETH/DXY) data once.
2. For each tunable indicator (power_law, weekly_monthly_rsi,
   weekly_monthly_macd, sma_band, rs_eth), solo it and grid its own
   construction periods against the combined long+medium objective
   (``weight_search.search_oscillator_periods_by_cycle_overlap``). m2/dxy
   have no tunable periods -- they pass through unchanged. An indicator
   whose best score doesn't clear a noise baseline is dropped before step 4
   (power_law is never dropped -- it's the anchor indicator and the
   explicit hedge floored back in at step 4).
3. Recombine all individually-optimized, surviving indicators at equal
   weight -- the baseline the reweight stage must beat.
4. Reweight the composite (``stage_a.optimize_stage_a_weights_combined``)
   with a diversification floor so no surviving indicator, including
   power_law, can be zeroed back out.
5. Sensitivity: rerun step 4 at long:medium = 2:1 and 5:1 so the ratio
   choice is visible before treating 3:1 as final.

This produces a diagnostic **index**, not a validated trading candidate --
curve/threshold/risk-adjusted-return optimization ("index then curve") is
the separate next step once this index is picked.

Usage:
    python scripts/run_weekly_monthly_confluence_composite_search.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, rs_eth_confluence_z
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import (
    sma_band_confluence_z,
    weekly_monthly_macd_confluence_z,
    weekly_monthly_rsi_confluence_z,
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

# Indicators whose construction periods are tunable (m2/dxy pass through
# base_extra_z unchanged -- they're single-leg, no dual-timeframe blend).
PRICE_OSC_TUNABLE = ("weekly_monthly_rsi", "weekly_monthly_macd", "sma_band", "rs_eth")
# The fixed, Chris-approved pool for steps 3-5 (power_law handled separately
# via SdcaCompositeWeights.power_law). Built explicitly rather than by
# filtering EXTRA_INDICATOR_NAMES/base_extra_z, since base_extra_z still
# carries the *old* weekly_rsi/monthly_rsi/weekly_macd/monthly_macd keys at
# their default periods (price_oscillator_z_vectors computes all of them) --
# those must NOT leak back into the search via a generic "in extra_z" check.
CANDIDATE_EXTRA_NAMES = ("m2", "dxy", "rs_eth", "sma_band", "weekly_monthly_rsi", "weekly_monthly_macd")

POWER_LAW_CANDIDATES = [{"trend_window": w} for w in (90, 120, 150, 180, 240, 365)]
# monthly_length space mirrors the old MONTHLY_RSI_CANDIDATES grid;
# weekly_length space mirrors the old WEEKLY_RSI_CANDIDATES grid -- both
# indicators' periods, now blended against each other instead of against a
# daily leg, so a fresh joint grid is warranted rather than reusing either
# indicator's previously-solo-optimized period.
WEEKLY_MONTHLY_RSI_CANDIDATES = [
    {"monthly_length": m, "weekly_length": w}
    for m in (2, 3, 4, 5, 6, 7, 9, 12, 14, 18)
    for w in (5, 7, 8, 9, 10, 12, 14, 18, 21, 26)
]
WEEKLY_MONTHLY_MACD_CANDIDATES = [
    {"monthly_fast": mf, "monthly_slow": ms, "weekly_fast": wf, "weekly_slow": ws}
    for mf, ms in ((3, 6), (4, 9), (5, 10), (6, 13), (8, 17), (12, 26))
    for wf, ws in ((4, 9), (5, 10), (6, 13), (8, 17), (10, 21), (12, 26), (16, 35))
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

# SdcaOscillatorSpec field names each indicator's winning params map onto --
# matches build_extra_indicators()'s exact kwarg wiring (indicator_catalog.py).
SPEC_FIELD_MAP = {
    "power_law": {"trend_window": "power_law_trend_window"},
    "weekly_monthly_rsi": {"monthly_length": "monthly_rsi_length", "weekly_length": "rsi_length"},
    "weekly_monthly_macd": {
        "monthly_fast": "monthly_macd_fast",
        "monthly_slow": "monthly_macd_slow",
        "weekly_fast": "macd_fast",
        "weekly_slow": "macd_slow",
    },
    "sma_band": {"slow_window": "sma_band_window", "fast_window": "sma_band_fast_window"},
    "rs_eth": {"slow_window": "rs_eth_window", "fast_window": "rs_eth_fast_window"},
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
    print(f"candidate pool (7): power_law, {', '.join(CANDIDATE_EXTRA_NAMES)}\n")

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

    def compute_weekly_monthly_rsi_z(p: dict[str, int]) -> list[float | None]:
        return weekly_monthly_rsi_confluence_z(
            date_s, price_s, monthly_length=p["monthly_length"], weekly_length=p["weekly_length"],
        ).to_list()

    def compute_weekly_monthly_macd_z(p: dict[str, int]) -> list[float | None]:
        return weekly_monthly_macd_confluence_z(
            date_s, price_s,
            monthly_fast=p["monthly_fast"], monthly_slow=p["monthly_slow"],
            weekly_fast=p["weekly_fast"], weekly_slow=p["weekly_slow"],
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
        ("weekly_monthly_rsi", WEEKLY_MONTHLY_RSI_CANDIDATES, compute_weekly_monthly_rsi_z),
        ("weekly_monthly_macd", WEEKLY_MONTHLY_MACD_CANDIDATES, compute_weekly_monthly_macd_z),
        ("sma_band", SMA_BAND_CANDIDATES, compute_sma_band_z),
        ("rs_eth", RS_ETH_CANDIDATES, compute_rs_eth_z if eth_available else None),
    ]

    print("=== Stage 2: per-indicator period search (combined objective) ===\n")
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

    print(f"surviving tunable extras after step 2: {surviving}\n")

    # Step 3: recombine surviving indicators (their optimized periods) plus
    # the pass-through extras (m2/dxy, no tunable periods) at equal weight.
    final_power_law_z = compute_power_law_z(best_params["power_law"])
    final_extra_z = dict(base_extra_z)
    compute_by_name = {
        "weekly_monthly_rsi": compute_weekly_monthly_rsi_z,
        "weekly_monthly_macd": compute_weekly_monthly_macd_z,
        "sma_band": compute_sma_band_z,
        "rs_eth": compute_rs_eth_z if eth_available else None,
    }
    for name in surviving:
        final_extra_z[name] = compute_by_name[name](best_params[name])

    search_names = tuple(
        n for n in CANDIDATE_EXTRA_NAMES
        if (n not in PRICE_OSC_TUNABLE) or (n in surviving)
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
