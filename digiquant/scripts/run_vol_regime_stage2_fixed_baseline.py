#!/usr/bin/env python3
"""Phase B Stage 2 (fixed-baseline framing): does ``vol_regime`` add signal
on top of the validated baseline?

``vol_regime`` cleared Stage 1 (``run_vol_regime_solo_validation.py``, best
short=60/long=180, combined=71.11 vs. 0.00 noise baseline) -- a genuinely
new signal class (volatility-regime compression/expansion, distinct from
``fast_crash_vol``'s short-window crash detection and ``sma_band``'s
price-deviation read). Per the lesson learned from ADX/Stochastic (Stage 1
pass, but the floor-forced 4-way Stage 2 framing was ambiguous until a
fixed-baseline re-test gave a clean, unconfounded answer), this goes
straight to the fixed-baseline framing: fix the validated baseline
(power_law=1.0, m2=0.5, dxy=0.5) and grid-search only ``vol_regime``'s
weight on top of it, with the winning Stage 1 window pair (short=60,
long=180).

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_vol_regime_stage2_fixed_baseline
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.composite_risk import causal_rolling_z
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

VOL_REGIME_SHORT = 60
VOL_REGIME_LONG = 180
Z_WINDOW = 365

BASELINE_POWER_LAW = 1.0
BASELINE_M2 = 0.5
BASELINE_DXY = 0.5

CANDIDATE_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)


def compute_vol_regime(close: pl.Series, w_short: int, w_long: int) -> pl.Series:
    log_ret = close.log().diff()
    short_vol = log_ret.rolling_std(window_size=w_short, min_samples=w_short)
    long_vol = log_ret.rolling_std(window_size=w_long, min_samples=w_long)
    return (short_vol / long_vol).log()


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    missing = [name for name in ("m2", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    close = pl.Series("close", prices, dtype=pl.Float64)
    extra_z["vol_regime"] = causal_rolling_z(
        compute_vol_regime(close, VOL_REGIME_SHORT, VOL_REGIME_LONG),
        window=Z_WINDOW,
        min_samples=max(20, Z_WINDOW // 2),
    ).to_list()

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"]
    ).to_list()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    def score_for(vol_regime_w: float) -> float:
        weights = SdcaCompositeWeights(
            power_law=BASELINE_POWER_LAW,
            m2=BASELINE_M2,
            dxy=BASELINE_DXY,
            vol_regime=vol_regime_w,
        )
        risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    baseline_objective = score_for(0.0)
    print(f"fixed baseline (power_law=1.0, m2=0.5, dxy=0.5) objective: {baseline_objective:.2f}\n")

    print(f"=== vol_regime (short={VOL_REGIME_SHORT}, long={VOL_REGIME_LONG}), grid-searched on top of fixed baseline ===")
    scored = [(w, score_for(w)) for w in CANDIDATE_GRID if w > 0.0]
    scored.sort(key=lambda s: -s[1])
    for w, obj in scored:
        delta = obj - baseline_objective
        print(f"  vol_regime={w:.2f}  objective={obj:.2f}  delta_vs_baseline={delta:+.2f}")
    best_w, best_obj = scored[0]
    print(
        f"\n  best: vol_regime={best_w:.2f} "
        f"({'IMPROVES on baseline' if best_obj > baseline_objective else 'no improvement'})"
    )

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
