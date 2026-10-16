#!/usr/bin/env python3
"""Phase B Stage 1: solo-validate a volume-derived indicator, ``volume_turnover``.

None of the 11 currently-tried ``EXTRA_INDICATOR_NAMES`` (power_law, m2, rs_eth,
dxy, weekly/monthly rsi/macd, sma_band, fear_greed, fast_crash_vol, the five
on-chain series) use trade volume at all -- every one of them is derived from
price, macro series, or on-chain valuation. ``BTC-USD.csv`` (the same cached
history used everywhere else in this project) already carries a ``volume``
column with full history back to 2014-09-17, so this is a genuinely untried
input dimension, not a rehash of anything in the 17-18 already-rejected leads.

Indicator definition (new, built here -- no existing SDCA indicator uses
volume): a causal rolling z-score of log dollar-turnover (``close * volume``),
i.e. "is today's turnover unusually heavy vs. its own trailing history".
Mirrors the volume-derived ETF-flow PROXY already used elsewhere in this repo
(``digiquant/src/digiquant/data/prices/etf_flows.py``'s dollar-volume z-score
leg) but reimplemented directly against the SDCA indicator shape
(``causal_rolling_z``, a single tunable ``window``) rather than importing that
module, since ``etf_flows.py`` is built for the Atlas per-ticker proxy shape
and its leave-one-out baseline convention, not SDCA's walk-forward pipeline.

Per the Phase B playbook: if this clears the noise baseline (same check
``run_fear_greed_solo_validation.py`` uses), it proceeds to Stage 2 (aggregate
reweight with the floor) -- which requires actually wiring a new
``volume_turnover`` field into ``SdcaCompositeWeights``/``build_extra_indicators``,
not attempted here. This script only needs the objective-scoring path, so it
sidesteps that wiring gap: ``search_oscillator_periods_by_cycle_overlap``
insists ``indicator_name`` be a real ``SdcaCompositeWeights`` field (it builds
``SdcaCompositeWeights(power_law=0.0, **{indicator_name: 1.0})``), which a
brand new indicator name is not -- confirmed by an initial run of this script
that failed with ``pydantic_core.ValidationError`` on exactly that call. So
this drives ``combined_cycle_overlap_score``/``risk_from_weighted_z`` directly
per candidate window instead, borrowing the existing ``m2`` weight slot to
carry the volume z-series (same trick ``_noise_baseline_objective`` below
already uses for its own zero-indicator baseline) -- purely a scoring
convenience, no production code or model changes.

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    python scripts/run_volume_turnover_solo_validation.py
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

WINDOW_CANDIDATES = [{"window": w} for w in (30, 45, 60, 90, 120, 180, 250, 365)]


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

    raw = pl.read_csv(data_path)
    if "timestamp" not in raw.columns or "volume" not in raw.columns:
        print(f"{data_path} is missing timestamp/volume columns -- cannot run.")
        return
    ts = raw["timestamp"]
    if ts.dtype != pl.Date:
        ts = ts.str.to_datetime().dt.date()
    volume_by_date = dict(zip(ts.to_list(), raw["volume"].to_list(), strict=True))
    price_by_date = dict(zip(dates, prices, strict=True))
    missing = [d for d in dates if d not in volume_by_date]
    if missing:
        print(f"{len(missing)} dates missing volume (first: {missing[0]}) -- cannot run cleanly.")
        return

    dollar_turnover = [price_by_date[d] * float(volume_by_date[d]) for d in dates]
    log_turnover = pl.Series("log_turnover", dollar_turnover, dtype=pl.Float64).log()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    noise_objective = _noise_baseline_objective(
        dates, long_windows, medium_windows, long_weight=long_weight, medium_weight=medium_weight
    )
    print(f"noise baseline objective: {noise_objective:.2f}\n")

    solo_weights = SdcaCompositeWeights(power_law=0.0, m2=1.0)

    def score_for_window(window: int) -> float:
        z = causal_rolling_z(log_turnover, window=window, min_samples=max(20, window // 2)).to_list()
        risk = risk_from_weighted_z(dates, [0.0] * len(dates), {"m2": z}, solo_weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    print("=== Stage 1: volume_turnover solo-validation (window search) ===\n")
    scored = [(c["window"], score_for_window(c["window"])) for c in WINDOW_CANDIDATES]
    scored.sort(key=lambda s: -s[1])
    best_window, best_objective = scored[0]
    beats_noise = best_objective > noise_objective
    print(f"best window: {best_window}  combined={best_objective:.2f}")
    print(f"  noise baseline: {noise_objective:.2f}")
    print(f"  RESULT: {'PASS -- clears noise baseline' if beats_noise else 'FAIL -- at/below noise baseline'}\n")

    print("all candidates:")
    for window, objective in scored:
        print(f"  window={window:>4}  combined={objective:.2f}")


if __name__ == "__main__":
    run()
