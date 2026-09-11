#!/usr/bin/env python3
"""Stage 1 of the Phase B indicator-addition playbook: solo-validate every
Bitview/BRK on-chain series (``onchain_mvrv``, ``onchain_asopr``,
``onchain_puell``, ``onchain_rhodl``).

Per ``RESEARCH_STATE.md``'s Phase B procedure, before a new indicator is
allowed to affect the aggregate composite it must clear a solo-validation
gate: soloed (weight=1, every other indicator at 0) and scored against the
same combined long+medium cycle-overlap objective the rest of the composite
is tuned against (``stage_a.combined_cycle_overlap_score`` via
``weight_search.search_oscillator_periods_by_cycle_overlap``), it must beat
a constant-zero noise baseline.

This generalizes ``run_onchain_mvrv_solo_search.py`` (which only covered
``onchain_mvrv``) to all 4 series now wired into ``indicator_catalog.py``,
since they share the same single-window-parameter shape and the same
``_log_ratio_sign_flipped_z`` transform.

This produces a go/no-go signal only, per series. It does not touch
settings.json, RESEARCH_STATE.md, or any other indicator's weight -- per the
playbook, that requires re-running Stage 2 (floor-diversified reweight) with
the surviving candidates added and Chris's explicit accept.

Usage:
    python scripts/run_onchain_solo_search.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.stage_a import (
    CombinedCycleOverlapScore,
    combined_cycle_overlap_score,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# All 4 Bitview on-chain ratios track multi-year halving cycles, not
# weekly/monthly price swings, so the grid skews longer than the
# price-oscillator searches (60d-4y).
WINDOW_CANDIDATES = [
    {"window": w} for w in (60, 90, 120, 180, 270, 365, 545, 730, 1095, 1460)
]


class OnchainSeriesSpec(NamedTuple):
    name: str
    z_fn: Callable[..., pl.Series]
    dates_attr: str
    values_attr: str


SERIES_SPECS = [
    OnchainSeriesSpec("onchain_mvrv", onchain_mvrv_z, "onchain_mvrv_dates", "onchain_mvrv_values"),
    OnchainSeriesSpec("onchain_asopr", onchain_asopr_z, "onchain_asopr_dates", "onchain_asopr_values"),
    OnchainSeriesSpec("onchain_puell", onchain_puell_z, "onchain_puell_dates", "onchain_puell_values"),
    OnchainSeriesSpec("onchain_rhodl", onchain_rhodl_z, "onchain_rhodl_dates", "onchain_rhodl_values"),
]


def _noise_baseline_objective(
    dates: list,
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float,
    medium_weight: float,
) -> float:
    """Objective for a constant-zero indicator -- the bar this search must clear."""
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

    sources = load_sdca_extra_sources(data_path.parent)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    default_power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    print(f"extras available: {sorted(base_extra_z)}\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    results: dict[str, bool] = {}

    for spec in SERIES_SPECS:
        src_dates = getattr(sources, spec.dates_attr)
        src_values = getattr(sources, spec.values_attr)
        if src_dates is None:
            print(f"=== Stage 1: {spec.name} -- SKIPPED (no source found) ===\n")
            continue

        print(
            f"{spec.name} source: {src_dates[0]}..{src_dates[-1]} "
            f"({len(src_dates)} points)\n"
        )

        def compute_z(p: dict[str, int], spec: OnchainSeriesSpec = spec, src_dates=src_dates, src_values=src_values) -> list[float | None]:
            return spec.z_fn(date_s, src_dates, src_values, window=p["window"]).to_list()

        print(f"=== Stage 1: {spec.name} solo period search (combined objective) ===\n")
        result = search_oscillator_periods_by_cycle_overlap(
            dates,
            indicator_name=spec.name,
            param_candidates=WINDOW_CANDIDATES,
            compute_indicator_z=compute_z,
            base_power_law_z=default_power_law_z,
            base_extra_z=base_extra_z,
            long_windows=long_windows,
            medium_windows=medium_windows,
            long_weight=long_weight,
            medium_weight=medium_weight,
        )
        beats_noise = result.best.score.objective > noise_objective
        results[spec.name] = beats_noise
        status = "OK -- clears noise baseline" if beats_noise else "DROP (<= noise baseline)"
        print(f"[{spec.name}] {status}")
        print(f"  best params: {result.best.params}")
        _print_score("score", result.best.score)
        print(f"  noise baseline: {noise_objective:.2f}\n")

        print("all candidates:")
        for candidate in sorted(result.all_scores, key=lambda s: s.score.objective, reverse=True):
            marker = " <-- best" if candidate.params == result.best.params else ""
            print(
                f"  window={candidate.params['window']:>5}  "
                f"objective={candidate.score.objective:>7.2f}{marker}"
            )
        print()

    print("=== Stage 1 summary ===")
    for name, beats_noise in results.items():
        print(f"  {name}: {'PASS' if beats_noise else 'DROP'}")


if __name__ == "__main__":
    run()
