#!/usr/bin/env python3
"""Phase B Stage 2: reweight the validated baseline with fear_greed added.

Stage 1 (``run_fear_greed_solo_validation.py``) passed: fear_greed at
window=250 scores combined=21.06 vs. a noise baseline of 0.00 (long=-3.31,
medium=30.99 -- a medium-term signal, weak on the long cycle).

This step re-runs the floor-diversified aggregate reweight
(``stage_a.optimize_stage_a_weights_combined``, floor=0.1/max=1.0) over the
validated baseline's indicators (power_law, m2, dxy) plus fear_greed. Per
the Phase B playbook, fear_greed only survives to Stage 3 if it earns a
weight strictly above the 0.1 floor -- a floor-pinned weight means it's
contributing no signal beyond what the floor forces.

Usage:
    python scripts/run_fear_greed_stage2_reweight.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import fear_greed_z
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import optimize_stage_a_weights_combined

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

FEAR_GREED_WINDOW = 250  # Stage 1 winner


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    sources = load_sdca_extra_sources(data_path.parent)
    if sources.fear_greed_dates is None or sources.m2_dates is None or sources.dxy_dates is None:
        print("Missing one of fear_greed/m2/dxy sources -- cannot run Stage 2.")
        return

    fg_z = fear_greed_z(
        date_s, sources.fear_greed_dates, sources.fear_greed_values, window=FEAR_GREED_WINDOW
    ).to_list()

    from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, extra_z_vectors

    price_s = pl.Series("price", prices, dtype=pl.Float64)
    base_weights = SdcaCompositeWeights(power_law=1.0, m2=1.0, dxy=1.0)
    all_extra_z = extra_z_vectors(date_s, price_s, base_weights, sources)
    extra_z = {"m2": all_extra_z["m2"], "dxy": all_extra_z["dxy"], "fear_greed": fg_z}

    # power_law_z: recompute directly (not part of extra_z_vectors' output).
    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z_series = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"]
    ).to_list()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0
    grid = (0.1, 0.55, 1.0)
    floor = 0.1

    search_names = ("m2", "dxy", "fear_greed")
    print("=== Stage 2: aggregate reweight (floor=0.1/max=1.0, coarse grid) ===\n")
    result = optimize_stage_a_weights_combined(
        dates,
        power_law_z=power_law_z_series,
        extra_z=extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=search_names,
        grid=grid,
        power_law_grid=grid,
        long_weight=long_weight,
        medium_weight=medium_weight,
        min_weight_floor=floor,
    )
    print(f"  evaluated: {result.num_evaluations} combinations")
    print(f"  weights: {result.weights.model_dump()}")
    print(
        f"  long={result.score.long.objective:.2f} medium={result.score.medium.objective:.2f} "
        f"combined={result.score.objective:.2f}"
    )
    fg_weight = result.weights.fear_greed
    print(f"\n  fear_greed weight: {fg_weight}")
    print(
        f"  RESULT: {'PASS -- above floor' if fg_weight > floor + 1e-9 else 'FAIL -- pinned at floor'}"
    )

    print("\n=== Baseline comparison (power_law=1.0, m2=0.5, dxy=0.5, no fear_greed) ===\n")
    from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

    baseline_weights = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
    baseline_risk = risk_from_weighted_z(
        dates, power_law_z_series, {"m2": extra_z["m2"], "dxy": extra_z["dxy"]}, baseline_weights
    )
    baseline_score = combined_cycle_overlap_score(
        dates, baseline_risk, long_windows, medium_windows,
        long_weight=long_weight, medium_weight=medium_weight,
    )
    print(
        f"  long={baseline_score.long.objective:.2f} medium={baseline_score.medium.objective:.2f} "
        f"combined={baseline_score.objective:.2f}"
    )


if __name__ == "__main__":
    run()
