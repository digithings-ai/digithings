#!/usr/bin/env python3
"""Phase B Stage 2 (fixed-baseline framing): does ``halving_cycle`` add
signal on top of the validated baseline?

``halving_cycle`` cleared Stage 1 decisively
(``run_halving_cycle_solo_validation.py``, best cycle_length=1317.6d,
phase_shift=+0.30, combined=140.42 vs. 0.00 noise baseline -- confirmed not
an edge-of-grid artifact by widening the phase-shift grid) and is a
genuinely different signal class from every prior candidate (calendar-
derived, no price/volume/on-chain input at all). Per the established
pattern from ADX/Stochastic/vol_regime, this goes straight to the
fixed-baseline framing: fix the validated baseline (power_law=1.0, m2=0.5,
dxy=0.5) and grid-search only ``halving_cycle``'s weight on top of it, at
its winning Stage 1 (cycle_length, phase_shift).

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_halving_cycle_stage2_fixed_baseline
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

HALVING_DATES = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
]
CYCLE_LENGTH_DAYS = 1317.6
PHASE_SHIFT = 0.30

BASELINE_POWER_LAW = 1.0
BASELINE_M2 = 0.5
BASELINE_DXY = 0.5

CANDIDATE_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)


def compute_halving_cycle(dates: list[date], cycle_length_days: float, phase_shift: float) -> list[float]:
    out = []
    for d in dates:
        last_halving = max((h for h in HALVING_DATES if h <= d), default=HALVING_DATES[0])
        days_since = (d - last_halving).days
        phase = (days_since / cycle_length_days + phase_shift) % 1.0
        out.append(math.cos(2 * math.pi * phase))
    return out


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    missing = [name for name in ("m2", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    extra_z["halving_cycle"] = compute_halving_cycle(dates, CYCLE_LENGTH_DAYS, PHASE_SHIFT)

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

    def score_for(halving_w: float) -> float:
        weights = SdcaCompositeWeights(
            power_law=BASELINE_POWER_LAW,
            m2=BASELINE_M2,
            dxy=BASELINE_DXY,
            halving_cycle=halving_w,
        )
        risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    baseline_objective = score_for(0.0)
    print(f"fixed baseline (power_law=1.0, m2=0.5, dxy=0.5) objective: {baseline_objective:.2f}\n")

    print(f"=== halving_cycle (cycle_length={CYCLE_LENGTH_DAYS}, phase_shift={PHASE_SHIFT:+.2f}), grid-searched on top of fixed baseline ===")
    scored = [(w, score_for(w)) for w in CANDIDATE_GRID if w > 0.0]
    scored.sort(key=lambda s: -s[1])
    for w, obj in scored:
        delta = obj - baseline_objective
        print(f"  halving_cycle={w:.2f}  objective={obj:.2f}  delta_vs_baseline={delta:+.2f}")
    best_w, best_obj = scored[0]
    print(
        f"\n  best: halving_cycle={best_w:.2f} "
        f"({'IMPROVES on baseline' if best_obj > baseline_objective else 'no improvement'})"
    )

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
