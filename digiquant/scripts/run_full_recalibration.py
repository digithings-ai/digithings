#!/usr/bin/env python3
"""Full 11-indicator SDCA recalibration: period search, floor-diversified
reweight, curve optimization, and OOS walk-forward validation.

Chris's brief: build one properly-validated baseline from *every* indicator
currently wired into the catalog (``indicator_catalog.EXTRA_INDICATOR_NAMES``
-- 10 extras + ``power_law`` = 11 total), diversified by a 0.1 weight floor /
1.0 max so no indicator collapses to near-zero, with buy/sell curve
optimization and an OOS walk-forward gate as part of what defines "the
baseline." See ``.claude/plans`` "Full 11-indicator SDCA recalibration
(floor=0.1) + curve optimization baseline."

Four stages, chained:

1. Per-indicator period search (``weight_search.search_oscillator_periods_by_cycle_overlap``)
   over every tunable indicator: power_law, weekly_rsi, weekly_macd,
   sma_band, rs_eth, monthly_rsi, monthly_macd. ``weekly_monthly_rsi``/
   ``weekly_monthly_macd`` have no independent period fields on
   ``SdcaOscillatorSpec`` -- they're fully derived from whichever periods
   weekly_rsi+monthly_rsi (RSI legs) and weekly_macd+monthly_macd (MACD legs)
   already won, so each is checked with a single derived candidate, purely to
   confirm it clears the noise baseline. m2/dxy have no periods and pass
   through unconditionally when their source data is available -- same as
   the existing 9-indicator script's behavior. Any indicator (other than the
   anchor power_law) that doesn't beat the noise baseline is dropped.
2. Aggregate reweight (``stage_a.optimize_stage_a_weights_combined``) over
   every surviving indicator with ``min_weight_floor=0.1`` -- coarse grid
   ``(0.1, 0.55, 1.0)`` first, then a local refinement pass narrowed to
   +/-0.15 in 0.05 steps around each coarse winner (still respecting the 0.1
   floor / 1.0 max). Reports 2:1/3:1/5:1 long:medium sensitivity via
   ``optimize_stage_a_weights_combined_multi_ratio``.
3. Buy/sell curve optimization (``curve_optimize.search_wide_knee_curve``)
   frozen against the Stage 2 winning weights + Stage 1 winning oscillator
   periods -- best ``risk_adjusted_return``, the fast curve_simulator go/no-go
   pass per RESEARCH_STATE.md's standard trial protocol.
4. OOS walk-forward validation (``optimize.run_sdca_walk_forward``) on the
   final (Stage 2 weights + Stage 3 curve) trial. Only if this shows
   ``beats_flat_dca_oos=True`` with a stable sensitivity check, and only on
   Chris's explicit accept, does this become the new baseline.

Diagnostic only. Does not touch ``settings.json`` or ``RESEARCH_STATE.md`` --
report the full table back to Chris for accept/reject.

Usage:
    uv run python scripts/run_full_recalibration.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_SEARCH_BOUNDS,
    load_frozen_index,
    search_wide_knee_curve,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    SdcaCompositeWeights,
    rs_eth_confluence_z,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    macd_confluence_z,
    monthly_macd_confluence_z,
    monthly_rsi_confluence_z,
    rsi_confluence_z,
    sma_band_confluence_z,
    weekly_monthly_macd_confluence_z,
    weekly_monthly_rsi_confluence_z,
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
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Indicators with independent construction periods to search. rs_eth carries
# real period params despite being a MACRO_INDICATOR_NAME; m2/dxy do not and
# are handled separately below.
PERIOD_SEARCHABLE = (
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
    "rs_eth",
    "monthly_rsi",
    "monthly_macd",
)
# Derived from PERIOD_SEARCHABLE's own winners -- no independent grid.
DERIVED_CONFLUENCE = ("weekly_monthly_rsi", "weekly_monthly_macd")
MACRO_PASSTHROUGH = ("m2", "dxy")

# Candidate period grids -- same values already smoke-tested in
# RESEARCH_STATE.md / run_dual_timeframe_composite_search.py.
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
# monthly_rsi's daily leg is its OWN field (monthly_rsi_daily_length), not
# shared with weekly_rsi's daily_rsi_length -- the two are deliberately
# independent per SdcaOscillatorSpec's docstring. monthly_macd's daily leg
# IS shared with weekly_macd's (macd_daily_fast/slow) -- also deliberate.
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
    "monthly_rsi": {"monthly_length": "monthly_rsi_length", "daily_length": "monthly_rsi_daily_length"},
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
    """Objective for a constant-zero indicator -- the bar Stage 1 must clear."""
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


def run(data_path: Path = DEFAULT_DATA_PATH, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
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

    tunable = [
        ("power_law", POWER_LAW_CANDIDATES, compute_power_law_z),
        ("weekly_rsi", WEEKLY_RSI_CANDIDATES, compute_weekly_rsi_z),
        ("weekly_macd", WEEKLY_MACD_CANDIDATES, compute_weekly_macd_z),
        ("sma_band", SMA_BAND_CANDIDATES, compute_sma_band_z),
        ("rs_eth", RS_ETH_CANDIDATES, compute_rs_eth_z if eth_available else None),
        ("monthly_rsi", MONTHLY_RSI_CANDIDATES, compute_monthly_rsi_z),
        ("monthly_macd", MONTHLY_MACD_CANDIDATES, compute_monthly_macd_z),
    ]

    print("=== Stage 1: per-indicator period search (combined objective) ===\n")
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

    # Derived confluence indicators: no independent period fields -- reuse
    # whichever periods their constituent legs already won, and only check
    # that the derived signal itself clears the noise baseline.
    derived_candidates = {
        "weekly_monthly_rsi": (
            {
                "monthly_length": best_params["monthly_rsi"]["monthly_length"],
                "weekly_length": best_params["weekly_rsi"]["weekly_length"],
            },
            compute_weekly_monthly_rsi_z,
        ),
        "weekly_monthly_macd": (
            {
                "monthly_fast": best_params["monthly_macd"]["monthly_fast"],
                "monthly_slow": best_params["monthly_macd"]["monthly_slow"],
                "weekly_fast": best_params["weekly_macd"]["weekly_fast"],
                "weekly_slow": best_params["weekly_macd"]["weekly_slow"],
            },
            compute_weekly_monthly_macd_z,
        ),
    }
    for name, (candidate, compute_fn) in derived_candidates.items():
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=name,
            param_candidates=[candidate],
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
        if beats_noise:
            surviving.append(name)
        status = "OK" if beats_noise else "DROP (<= noise baseline)"
        print(f"[{name}] {status} (derived -- reuses its legs' already-searched periods, no independent grid)")
        print(f"  derived params: {candidate}")
        _print_score("score", result.best.score)
        print()

    # m2/dxy: no tunable periods, pass through unconditionally when their
    # source data is available -- same as the existing 9-indicator script.
    for name in MACRO_PASSTHROUGH:
        if name in base_extra_z:
            surviving.append(name)
            print(f"[{name}] PASSTHROUGH (no periods, no noise check -- source data available)\n")
        else:
            print(f"[{name}] SKIPPED -- no source data available\n")

    print(f"surviving indicators after Stage 1 (excl. power_law): {surviving}\n")

    # Build the final z-series and merged SdcaOscillatorSpec from every
    # surviving indicator's winning periods.
    final_power_law_z = compute_power_law_z(best_params["power_law"])
    compute_by_name = {
        "weekly_rsi": compute_weekly_rsi_z,
        "weekly_macd": compute_weekly_macd_z,
        "sma_band": compute_sma_band_z,
        "rs_eth": compute_rs_eth_z if eth_available else None,
        "monthly_rsi": compute_monthly_rsi_z,
        "monthly_macd": compute_monthly_macd_z,
        "weekly_monthly_rsi": compute_weekly_monthly_rsi_z,
        "weekly_monthly_macd": compute_weekly_monthly_macd_z,
    }
    final_extra_z = dict(base_extra_z)
    for name in surviving:
        if name in compute_by_name:
            final_extra_z[name] = compute_by_name[name](best_params[name])

    spec_fields: dict[str, int] = _spec_fields("power_law", best_params["power_law"])
    for name in PERIOD_SEARCHABLE:
        if name in surviving:
            spec_fields.update(_spec_fields(name, best_params[name]))
    oscillator_spec = SdcaOscillatorSpec(**spec_fields)
    print(f"Stage 1 winning SdcaOscillatorSpec: {oscillator_spec.model_dump()}\n")

    search_names = tuple(n for n in EXTRA_INDICATOR_NAMES if n in surviving)
    print(f"search_names for Stage 2: {search_names}\n")

    # === Stage 2: floor-diversified aggregate reweight ===
    floor, max_weight = 0.1, 1.0
    coarse_grid = (0.1, 0.55, 1.0)
    print("=== Stage 2: aggregate reweight (floor=0.1, coarse grid, 3:1) ===\n")
    coarse_result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=final_power_law_z,
        extra_z=final_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=search_names,
        grid=coarse_grid,
        power_law_grid=coarse_grid,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=floor,
    )
    print(f"  evaluated: {coarse_result.num_evaluations} combinations")
    print(f"  weights: {coarse_result.weights.model_dump()}")
    _print_score("score", coarse_result.score)
    print()

    print("=== Stage 2 refine: budget-bounded shared grid around coarse winners ===\n")
    # optimize_stage_a_weights_combined applies ONE shared grid across every
    # search_names dimension via a full itertools.product -- there is no
    # per-indicator grid. A union of each indicator's own +/-0.15 window
    # (as many as 10 dimensions x up to 15 distinct values) would blow up to
    # ~10^12 evaluations. Instead: narrow the *range* to bracket every coarse
    # winner (still tighter than the full [0.1, 1.0] span), then pick a
    # shared point count that keeps grid_size**(N+1) under budget.
    coarse_weights = coarse_result.weights.model_dump()
    coarse_values = [coarse_weights["power_law"]] + [coarse_weights[name] for name in search_names]
    range_lo = max(floor, min(coarse_values) - 0.15)
    range_hi = min(max_weight, max(coarse_values) + 0.15)
    n_dims = len(search_names) + 1  # + power_law
    # Same order of magnitude as the coarse pass (~177K at n_dims=10) -- this
    # is a narrowing refinement, not a second full-resolution search.
    refine_budget = 250_000
    n_points = max(3, min(5, int(refine_budget ** (1.0 / n_dims))))
    if n_points > 1:
        step = (range_hi - range_lo) / (n_points - 1)
        refine_grid = tuple(sorted({round(range_lo + i * step, 4) for i in range(n_points)} | {max_weight}))
    else:
        refine_grid = (range_lo, max_weight)
    final_result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=final_power_law_z,
        extra_z=final_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=search_names,
        grid=refine_grid,
        power_law_grid=refine_grid,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=floor,
    )
    print(f"  coarse winners bracket: [{range_lo:.2f}, {range_hi:.2f}], n_points={n_points}")
    print(f"  refine grid (shared): {refine_grid}")
    print(f"  evaluated: {final_result.num_evaluations} combinations")
    print(f"  weights: {final_result.weights.model_dump()}")
    _print_score("score", final_result.score)
    print()

    out_of_bounds = [
        (name, w) for name, w in final_result.weights.model_dump().items()
        if name in (*search_names, "power_law") and not (floor - 1e-9 <= w <= max_weight + 1e-9)
    ]
    if out_of_bounds:
        print(f"  WARNING: weights outside [{floor}, {max_weight}]: {out_of_bounds}\n")

    print("=== Stage 2 sensitivity: long:medium ratio (2:1 / 3:1 / 5:1) ===\n")
    ratios = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))
    by_ratio = optimize_stage_a_weights_combined_multi_ratio(
        dates,
        power_law_z=final_power_law_z,
        extra_z=final_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=search_names,
        grid=refine_grid,
        power_law_grid=refine_grid,
        ratios=ratios,
        min_weight_floor=floor,
    )
    for lw, mw in ratios:
        result_lw = by_ratio[(lw, mw)]
        print(f"  ratio {lw:g}:1 -> weights: {result_lw.weights.model_dump()}")
        _print_score("  score", result_lw.score)
        print()

    # === Stage 3: buy/sell curve optimization, frozen against Stage 2 winner ===
    print("=== Stage 3: wide-knee curve search (frozen index, best risk_adjusted_return) ===\n")
    frozen_dates, frozen_prices, frozen_risk, resolved_weights = load_frozen_index(
        cache_dir, weights=final_result.weights, oscillators=oscillator_spec,
    )
    print(f"  frozen index: {frozen_dates[0]}..{frozen_dates[-1]} ({frozen_dates.len()} bars)")
    print(f"  frozen weights (post source-availability drop): {resolved_weights.model_dump()}")
    print(f"  wide-knee search bounds: {WIDE_KNEE_SEARCH_BOUNDS}\n")
    curve_result = search_wide_knee_curve(
        frozen_dates, frozen_prices, frozen_risk,
        initial_cash=1000.0, frozen_weights=resolved_weights,
    )
    winning_shape = curve_result.best.shape
    print(f"  evaluated: {curve_result.num_evaluations} trials ({curve_result.num_feasible} feasible)")
    print(f"  winning shape: {winning_shape.model_dump()}")
    print(f"  risk_adjusted_return: {curve_result.best.risk_adjusted_return:.4f}")
    print(f"  total_return_pct: {curve_result.best.total_return_pct:.2f}%")
    print(f"  max_drawdown_pct: {curve_result.best.max_drawdown_pct:.2f}%")
    print(f"  vs published baseline risk_adjusted_return: {curve_result.baseline.risk_adjusted_return:.4f}\n")

    # === Stage 4: OOS walk-forward validation gate ===
    print("=== Stage 4: OOS walk-forward validation (curve_simulator, single frozen candidate) ===\n")
    wf_extra_z = load_sdca_extra_z(
        dates, prices, data_path=None, data_dir=str(cache_dir), oscillators=oscillator_spec,
    )
    weight_params = {
        WEIGHT_PARAM_BY_NAME[name]: weight
        for name, weight in resolved_weights.model_dump().items()
        if name in WEIGHT_PARAM_BY_NAME
    }
    trial = {**SDCA_SHAPE_DEFAULTS, **winning_shape.model_dump(), **weight_params}
    print(f"  frozen trial weights: {weight_params}")
    print(f"  frozen trial curve: {winning_shape.model_dump()}\n")

    wf_result = run_sdca_walk_forward(
        dates, prices, [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/full_recalibration",
        extra_z=wf_extra_z,
    )
    holdout = wf_result.holdout_metrics.vs_flat_dca_pct if wf_result.holdout_metrics else float("nan")
    print(
        f"  IS {wf_result.mean_is_vs_flat_dca_pct:7.2f} | OOS {wf_result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {wf_result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | "
        f"beats_oos {wf_result.beats_flat_dca_oos}"
    )
    for fs in wf_result.fold_scores:
        oos = fs.out_of_sample
        print(
            f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:6.2f}%"
        )
    if wf_result.holdout_metrics is not None:
        h = wf_result.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:.2f}%  vs_lump={h.vs_lump_pct:.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.2f}%  max_drawdown={h.max_drawdown_pct:.2f}%"
        )
    print(
        f"    sensitivity: stable={wf_result.sensitivity.stable}  "
        f"max_abs_delta_oos={wf_result.sensitivity.max_abs_delta_oos_pct:.2f}pp"
    )

    print("\n=== Summary ===\n")
    print(f"surviving indicators: {list(search_names)} + power_law")
    print(f"Stage 2 weights (floor=0.1, max=1.0): {final_result.weights.model_dump()}")
    print(f"Stage 3 curve shape: {winning_shape.model_dump()}")
    print(
        f"Stage 4 OOS vs-flat-DCA: {wf_result.mean_oos_vs_flat_dca_pct:.2f}%  "
        f"beats_flat_dca_oos={wf_result.beats_flat_dca_oos}  "
        f"sensitivity_stable={wf_result.sensitivity.stable}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
