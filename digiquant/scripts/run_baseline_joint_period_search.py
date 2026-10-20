#!/usr/bin/env python3
"""Joint period re-tuning of the validated baseline's 3 indicators.

The validated baseline (``power_law=1.0, m2=0.5, dxy=0.5``, +84.8-84.9% OOS,
2026-09-03) has never actually had its construction periods searched --
``power_law``'s ``trend_window`` and ``m2``/``dxy``'s rolling-z ``window``
(``m2`` additionally has a ``roc_days`` YoY-lookback param) were all left at
code defaults (``trend_window`` unset -> ``power_law_confluence_z``'s own
default of 180, ``m2`` roc_days=365/window=90, ``dxy`` window=90). Every existing
Stage 1 script solos ONE indicator at a time against the others at zero --
never jointly, and never for exactly this 3-indicator baseline mix. This
script grids all three jointly (small grid, weights fixed at the baseline's
1.0/0.5/0.5) against the combined long+medium cycle-overlap objective, to
check whether the current defaults are actually a local optimum for this
specific weight mix or whether a different period combination scores
higher in-sample.

This is a period-tuning check only -- NOT a new indicator, so no Phase B
Stage 2 reweight is needed. If a joint winner clearly beats the current
defaults' combined score, the follow-up is Stage 3 (curve refit) + Stage 4
(OOS walk-forward) on that period combination before it could replace the
validated baseline. Per the standing gate, settings.json/RESEARCH_STATE.md
are untouched regardless of outcome.

Usage:
    uv run python -m scripts.run_baseline_joint_period_search
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import dxy_z, m2_liquidity_z
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Current code defaults (the "as-validated" combination), included in every grid
# so the search always reports a delta against the known baseline.
DEFAULT_TREND_WINDOW = 180  # power_law_confluence_z's own default (_TREND_WINDOW)
DEFAULT_M2_ROC_DAYS = 365
DEFAULT_M2_WINDOW = 90
DEFAULT_DXY_WINDOW = 90

TREND_WINDOW_CANDIDATES = (90, 120, 180, 240, 365, 500)
M2_ROC_DAYS_CANDIDATES = (180, 270, 365, 540)
M2_WINDOW_CANDIDATES = (60, 90, 150, 250)
DXY_WINDOW_CANDIDATES = (60, 90, 150, 250)

BASELINE_WEIGHTS_TUPLE = (1.0, 0.5, 0.5)  # power_law, m2, dxy


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    sources = load_sdca_extra_sources(data_path.parent)
    if sources.m2_dates is None or sources.dxy_dates is None:
        print("Missing m2/dxy sources -- cannot run.")
        return

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

    weights = SdcaCompositeWeights(
        power_law=BASELINE_WEIGHTS_TUPLE[0],
        m2=BASELINE_WEIGHTS_TUPLE[1],
        dxy=BASELINE_WEIGHTS_TUPLE[2],
    )

    def score_for(trend_window: int, m2_roc_days: int, m2_window: int, dxy_window: int) -> float:
        pl_z = power_law_confluence_z(
            date_s, price_s, rails["low"], rails["median"], rails["high"],
            trend_window=trend_window,
        ).to_list()
        m2z = m2_liquidity_z(
            date_s, sources.m2_dates, sources.m2_values,
            roc_days=m2_roc_days, window=m2_window,
        ).to_list()
        dxyz = dxy_z(date_s, sources.dxy_dates, sources.dxy_values, window=dxy_window).to_list()
        risk = risk_from_weighted_z(dates, pl_z, {"m2": m2z, "dxy": dxyz}, weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    default_score = score_for(
        DEFAULT_TREND_WINDOW, DEFAULT_M2_ROC_DAYS, DEFAULT_M2_WINDOW, DEFAULT_DXY_WINDOW
    )
    print(
        f"current defaults: trend_window={DEFAULT_TREND_WINDOW} "
        f"m2_roc_days={DEFAULT_M2_ROC_DAYS} m2_window={DEFAULT_M2_WINDOW} "
        f"dxy_window={DEFAULT_DXY_WINDOW}  ->  combined={default_score:.2f}\n"
    )

    combos = list(
        product(
            TREND_WINDOW_CANDIDATES, M2_ROC_DAYS_CANDIDATES, M2_WINDOW_CANDIDATES, DXY_WINDOW_CANDIDATES
        )
    )
    print(f"grid: {len(combos)} combinations\n")

    results = []
    for tw, roc, mw, dw in combos:
        s = score_for(tw, roc, mw, dw)
        results.append((s, tw, roc, mw, dw))

    results.sort(key=lambda r: -r[0])
    print("top 10:")
    for s, tw, roc, mw, dw in results[:10]:
        print(
            f"  trend_window={tw:>4} m2_roc_days={roc:>4} m2_window={mw:>4} "
            f"dxy_window={dw:>4}  combined={s:.2f}"
        )

    best = results[0]
    delta = best[0] - default_score
    print(f"\nbest vs. default delta: {delta:+.2f} ({default_score:.2f} -> {best[0]:.2f})")
    if delta > 0.5:
        print("RESULT: meaningful in-sample improvement -- worth a Stage 3/4 follow-up.")
    else:
        print("RESULT: current defaults are already ~locally optimal for this weight mix.")


if __name__ == "__main__":
    run()
