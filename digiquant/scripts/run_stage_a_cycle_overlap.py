#!/usr/bin/env python3
"""Stage A cycle-overlap weight search against the long-term and medium-term
BTC cycle windows (``SdcaCycleWindows.btc_v1()`` / ``.btc_medium_term_v1()``).

``stage_a.py``'s ``cycle_overlap_score()``/``optimize_stage_a_weights()`` is
kept only as a *diagnostic* (``weight_search.py:1-7``) -- the weight-selection
path that actually ships uses in-sample backtest return
(``optimize_stage_a_by_backtest``) instead. This script runs the diagnostic
directly, once per timeframe layer, since it answers a narrower question
literally: "which composite weights make the aggregate risk index's
accumulate/distribute bands best overlap this set of hand-marked cycle
windows." That's Stage 4 of ``DCA_VALUATION_FRAMEWORK.md``'s proposed next
steps -- a medium-term Stage A pass against the new medium-term window set,
run alongside a re-check of the long-term pass against the corrected
2025-10-06 peak pin.

Reconciling this objective against ``weight_search.py``'s backtest-return
objective (framework doc step 2) is still open; this script does not
resolve that, it only reports what each objective prefers for each layer.

Usage:
    python scripts/run_stage_a_cycle_overlap.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import EXTRA_INDICATOR_NAMES
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import optimize_stage_a_weights

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"]
    ).to_list()

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    print(f"extras available: {sorted(extra_z)}\n")

    for label, windows in (
        ("LONG-TERM (btc_v1)", SdcaCycleWindows.btc_v1()),
        ("MEDIUM-TERM (btc_medium_term_v1)", SdcaCycleWindows.btc_medium_term_v1()),
    ):
        print(f"=== {label} ===")
        result = optimize_stage_a_weights(
            dates,
            power_law_z=power_law_z,
            extra_z=extra_z,
            windows=windows,
            search_names=EXTRA_INDICATOR_NAMES,
            grid=(0.0, 0.5, 1.0),
            power_law_grid=(0.0, 0.5, 1.0),
        )
        print(f"  evaluated: {result.num_evaluations} combinations")
        print(f"  weights:   {result.weights.model_dump()}")
        print(f"  score:     {result.score.model_dump()}")
        print()


if __name__ == "__main__":
    run()
