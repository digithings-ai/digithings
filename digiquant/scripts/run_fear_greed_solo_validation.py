#!/usr/bin/env python3
"""Phase B Stage 1: solo-validate ``fear_greed`` against the combined objective.

Fear & Greed has no period-search dimension in the RSI/MACD sense (it's a
fixed daily 0-100 series from alternative.me, not a tunable-lookback
oscillator) -- its only free parameter is ``fear_greed_z``'s rolling-z
``window``, the same role ``window`` plays for ``dxy``/``onchain_mvrv``/etc.
This mirrors how the existing solo-validation shape
(``weight_search.search_oscillator_periods_by_cycle_overlap``) is used for
tunable-period indicators, treating ``window`` as fear_greed's one
grid-searchable knob, then compares the best window's score against the
noise-baseline objective (constant-zero indicator) that
``run_dual_timeframe_composite_search.py`` already establishes.

Per the Phase B playbook (``.claude/plans`` "Full 11-indicator SDCA
recalibration"): if this clears the noise baseline, `fear_greed` proceeds to
Stage 2 (aggregate reweight with the floor). If not, it's dropped here and
never reaches settings.json/RESEARCH_STATE.md, per the standing gate.

Usage:
    python scripts/run_fear_greed_solo_validation.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, fear_greed_z
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.stage_a import (
    combined_cycle_overlap_score,
    risk_from_weighted_z,
)
from digiquant.strategies.sdca.weight_search import search_oscillator_periods_by_cycle_overlap

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

WINDOW_CANDIDATES = [{"window": w} for w in (30, 45, 60, 90, 120, 150, 180, 250)]


def _noise_baseline_objective(
    dates: list,
    long_windows: SdcaCycleWindows,
    medium_windows: SdcaCycleWindows,
    *,
    long_weight: float,
    medium_weight: float,
) -> float:
    zeros = [0.0] * len(dates)
    dummy_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)
    risk = risk_from_weighted_z(dates, zeros, {"m2": zeros}, dummy_weights)
    return combined_cycle_overlap_score(
        dates, risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    ).objective


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)

    sources = load_sdca_extra_sources(data_path.parent)
    if sources.fear_greed_dates is None:
        print("fear_greed source NOT found -- run fetch_fear_greed() to cache it first.")
        return
    print(
        f"fear_greed source: {len(sources.fear_greed_dates)} rows, "
        f"{sources.fear_greed_dates[0]}..{sources.fear_greed_dates[-1]}\n"
    )

    base_extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    base_extra_z.pop("fear_greed", None)  # solo-search adds its own candidate z
    default_power_law_z = [None] * len(dates)

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    def compute_fear_greed_z(p: dict[str, int]) -> list[float | None]:
        return fear_greed_z(
            date_s,
            sources.fear_greed_dates,
            sources.fear_greed_values,
            window=p["window"],
        ).to_list()

    print("=== Stage 1: fear_greed solo-validation (window search) ===\n")
    result = search_oscillator_periods_by_cycle_overlap(
        dates,
        indicator_name="fear_greed",
        param_candidates=WINDOW_CANDIDATES,
        compute_indicator_z=compute_fear_greed_z,
        base_power_law_z=default_power_law_z,
        base_extra_z=base_extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        long_weight=long_weight,
        medium_weight=medium_weight,
    )
    beats_noise = result.best.score.objective > noise_objective
    print(f"best window: {result.best.params}")
    print(
        f"  long={result.best.score.long.objective:.2f} "
        f"medium={result.best.score.medium.objective:.2f} "
        f"combined={result.best.score.objective:.2f}"
    )
    print(f"  noise baseline: {noise_objective:.2f}")
    print(f"  RESULT: {'PASS -- clears noise baseline' if beats_noise else 'FAIL -- at/below noise baseline'}\n")

    print("all candidates:")
    for s in sorted(result.all_scores, key=lambda s: -s.score.objective):
        print(f"  window={s.params['window']:>4}  combined={s.score.objective:.2f}")


if __name__ == "__main__":
    run()
