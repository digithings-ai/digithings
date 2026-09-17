#!/usr/bin/env python3
"""Search ``compute_composite_risk``'s rolling/smoothing knobs on the validated baseline.

``build_risk_index``/``compute_composite_risk`` support two optional
post-processing knobs on the composite z-score, both defaulting to off
(``None``) and never yet searched for this strategy: ``rolling_window``
(re-normalizes the weighted blend against its own trailing distribution, so
long-horizon legs like ``power_law`` stay stationary as history accumulates)
and ``smoothing_window`` (a plain causal rolling mean over the final
composite, applied after any rolling re-normalization, for day-to-day noise
reduction). Flagged as the next untried lead after both the indicator-hunt
and period-re-tuning threads closed (dead ends #14/#15).

This is a Stage-1-style solo search: freeze the validated baseline's weights
(``power_law=1.0, m2=0.5, dxy=0.5``) and construction periods (code
defaults) exactly as-is, and grid only the two composite-risk knobs against
the combined long+medium cycle-overlap objective, to check whether smoothing
or rolling re-normalization noticeably changes the index's quality before
spending a Stage 3/4 walk-forward on it.

Usage:
    uv run python -m scripts.run_baseline_composite_smoothing_search
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# NB: compute_composite_risk derives a default min_samples of
# max(_ROLLING_MIN_SAMPLES_FLOOR=20, window // 2) whenever an explicit
# min_samples isn't passed, and polars' rolling_mean rejects min_samples >
# window_size -- so any window below 40 blows up with the defaults used
# here. Candidates are floored at 40 to stay inside that constraint (a real,
# if minor, gap in compute_composite_risk's default derivation for small
# windows -- worth a one-line fix later, not touched here since it's out of
# scope for a read-only search script).
ROLLING_WINDOW_CANDIDATES = (None, 90, 180, 365)
SMOOTHING_WINDOW_CANDIDATES = (None, 40, 60, 90, 120)


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    sources = load_sdca_extra_sources(data_path.parent)
    if sources.m2_dates is None or sources.dxy_dates is None:
        print("Missing m2/dxy sources -- cannot run.")
        return

    from digiquant.strategies.sdca.indicator_catalog import dxy_z, m2_liquidity_z

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(date_s, price_s, rails["low"], rails["median"], rails["high"])
    m2_z = m2_liquidity_z(date_s, sources.m2_dates, sources.m2_values)
    dxy_z_series = dxy_z(date_s, sources.dxy_dates, sources.dxy_values)

    indicators = [
        IndicatorWeight(name="power_law", z=power_law_z, weight=1.0),
        IndicatorWeight(name="m2", z=m2_z, weight=0.5),
        IndicatorWeight(name="dxy", z=dxy_z_series, weight=0.5),
    ]

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    def score_for(rolling_window: int | None, smoothing_window: int | None) -> float:
        composite = compute_composite_risk(
            indicators, rolling_window=rolling_window, smoothing_window=smoothing_window
        )
        return combined_cycle_overlap_score(
            dates, composite["risk"].to_list(), long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    default_score = score_for(None, None)
    print(f"current defaults (no rolling/smoothing): combined={default_score:.2f}\n")

    combos = list(product(ROLLING_WINDOW_CANDIDATES, SMOOTHING_WINDOW_CANDIDATES))
    print(f"grid: {len(combos)} combinations\n")

    results = []
    for rw, sw in combos:
        s = score_for(rw, sw)
        results.append((s, rw, sw))

    results.sort(key=lambda r: -r[0])
    print("top 10:")
    for s, rw, sw in results[:10]:
        print(f"  rolling_window={str(rw):>5} smoothing_window={str(sw):>5}  combined={s:.2f}")

    best = results[0]
    delta = best[0] - default_score
    print(f"\nbest vs. default delta: {delta:+.2f} ({default_score:.2f} -> {best[0]:.2f})")
    if delta > 0.5:
        print("RESULT: meaningful in-sample improvement -- worth a Stage 3/4 follow-up.")
    else:
        print("RESULT: no meaningful improvement -- rolling/smoothing knobs don't help here.")


if __name__ == "__main__":
    run()
