#!/usr/bin/env python3
"""Phase B Stage 1: solo-validate a halving-cycle-position indicator,
``halving_cycle``.

Genuinely different signal class from every candidate tried so far (all
21 prior dead ends, plus the validated baseline itself, are derived from
price, volume, or a price-linked macro/on-chain series and then causal
z-scored). This one is purely calendar-derived: a deterministic function
of the date relative to BTC's known halving schedule, encoding "how far
through the ~4-year halving cycle are we" as a cyclical prior. No
z-scoring makes sense for a bounded, non-stationary-noise signal like
this -- it is used directly on a [-1, 1] scale (cosine phase), peaking
at 1.0 right after a halving (historically the pre-rally trough/base) and
at -1.0 at the cycle midpoint (historically pre-blowoff-top proximity is
disputed, but the phase itself is the hypothesis under test, not asserted
truth).

Indicator definition: days_since_last_halving / cycle_length_days, mapped
through cos(2*pi*phase) so the signal is smooth and periodic across
halving-date uncertainty (using calendar halving dates, not on-chain block
height, since BTC-USD.csv doesn't carry block height).

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_halving_cycle_solo_validation
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

HALVING_DATES = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
]
# Average observed inter-halving gap in days (~4 years), used to project
# cycle length for the post-2024 tail where the next halving isn't known yet.
AVG_CYCLE_DAYS = sum(
    (HALVING_DATES[i + 1] - HALVING_DATES[i]).days for i in range(len(HALVING_DATES) - 1)
) / (len(HALVING_DATES) - 1)

CYCLE_LENGTH_GRID = (AVG_CYCLE_DAYS * f for f in (0.9, 0.95, 1.0, 1.05, 1.1))
PHASE_SHIFT_GRID = (0.0, 0.1, 0.2, 0.3, 0.4, 0.45, -0.1, -0.2, -0.3, -0.4)  # fraction of cycle, explores lead/lag


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


def compute_halving_cycle(dates: list[date], cycle_length_days: float, phase_shift: float) -> list[float]:
    import math

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
    print(f"avg observed inter-halving gap: {AVG_CYCLE_DAYS:.1f} days\n")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    solo_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)

    def score_series(series: list[float]) -> float:
        risk = risk_from_weighted_z(dates, [0.0] * len(dates), {"m2": series}, solo_weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    print("=== Stage 1: halving_cycle solo-validation (cycle-length x phase-shift search) ===\n")
    scored = []
    for cycle_len in CYCLE_LENGTH_GRID:
        for shift in PHASE_SHIFT_GRID:
            series = compute_halving_cycle(dates, cycle_len, shift)
            scored.append(((cycle_len, shift), score_series(series)))
    scored.sort(key=lambda s: -s[1])
    (best_cycle, best_shift), best_objective = scored[0]
    beats_noise = best_objective > noise_objective
    print(f"best: cycle_length={best_cycle:.1f}d  phase_shift={best_shift:+.2f}  combined={best_objective:.2f}")
    print(f"  noise baseline: {noise_objective:.2f}")
    print(f"  RESULT: {'PASS -- clears noise baseline' if beats_noise else 'FAIL -- at/below noise baseline'}\n")

    print("top 10 candidates:")
    for (cl, sh), objective in scored[:10]:
        print(f"  cycle_length={cl:>7.1f}d  phase_shift={sh:+.2f}  combined={objective:.2f}")


if __name__ == "__main__":
    run()
