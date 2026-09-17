#!/usr/bin/env python3
"""Phase B Stage 1: solo-validate a volatility-regime indicator, ``vol_regime``.

Distinct from the two existing volatility-flavored signals: ``fast_crash_vol``
is a short-window (days) realized-vol crash detector wired as an independent
circuit-breaker override, not a composite cycle-timing input; ``sma_band``
measures price's *deviation* from its moving average in std-dev units, not
volatility magnitude itself. Neither measures "is realized volatility
expanding or contracting relative to its own longer-run history" -- a
regime-compression/expansion signal, the classic volatility-cycle idea (vol
compresses before major trend moves, cycle tops/bottoms often coincide with
vol regime shifts) untried anywhere in the current 20-indicator catalog.

Indicator definition (new, close-only, no new data source): the ratio of a
short realized-vol window to a long realized-vol window,
``short_vol(w_short) / long_vol(w_long)``, log-transformed then causal
z-scored -- "is short-term volatility unusually compressed or expanded
relative to the longer-run baseline". Grid-searched over (w_short, w_long)
pairs with w_short < w_long.

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_vol_regime_solo_validation
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.composite_risk import causal_rolling_z
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

WINDOW_PAIRS = [
    (7, 30), (7, 60), (7, 90),
    (14, 60), (14, 90), (14, 180),
    (30, 90), (30, 180), (30, 365),
    (60, 180), (60, 365),
]
Z_WINDOW = 365


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


def compute_vol_regime(close: pl.Series, w_short: int, w_long: int) -> pl.Series:
    log_ret = close.log().diff()
    short_vol = log_ret.rolling_std(window_size=w_short, min_samples=w_short)
    long_vol = log_ret.rolling_std(window_size=w_long, min_samples=w_long)
    ratio = short_vol / long_vol
    return ratio.log()


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    close = pl.Series("close", prices, dtype=pl.Float64)

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    solo_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)

    def score_series(series: pl.Series) -> float:
        z = causal_rolling_z(series, window=Z_WINDOW, min_samples=max(20, Z_WINDOW // 2)).to_list()
        risk = risk_from_weighted_z(dates, [0.0] * len(dates), {"m2": z}, solo_weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    print("=== Stage 1: vol_regime solo-validation (window-pair search) ===\n")
    scored = []
    for w_short, w_long in WINDOW_PAIRS:
        series = compute_vol_regime(close, w_short, w_long)
        scored.append(((w_short, w_long), score_series(series)))
    scored.sort(key=lambda s: -s[1])
    best_pair, best_objective = scored[0]
    beats_noise = best_objective > noise_objective
    print(f"best pair: short={best_pair[0]} long={best_pair[1]}  combined={best_objective:.2f}")
    print(f"  noise baseline: {noise_objective:.2f}")
    print(f"  RESULT: {'PASS -- clears noise baseline' if beats_noise else 'FAIL -- at/below noise baseline'}\n")

    print("all candidates:")
    for (ws, wl), objective in scored:
        print(f"  short={ws:>4} long={wl:>4}  combined={objective:.2f}")


if __name__ == "__main__":
    run()
