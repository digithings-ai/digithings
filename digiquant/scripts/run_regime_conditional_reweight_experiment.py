#!/usr/bin/env python3
"""Structural-redesign feasibility probe: does a regime-conditional weight
switch beat the single fixed weighted-average baseline?

Context (see project memory, "session-wide conclusion after 5 candidates in
a row rejected, 2026-09-18"): every one-off indicator added on top of the
fixed baseline (power_law=1.0, m2=0.5, dxy=0.5) fails at Stage 2, because
``compute_composite_risk`` blends indicators as a weighted AVERAGE for the
*entire* backtest at once -- a new indicator dilutes the strong existing
blend unless it correlates with the objective even better than that blend
does, which is a very high bar. A structural fix would let the weight mix
vary by market regime instead of staying fixed across all ~11 years of
history. Before investing in a full regime-detection architecture, this
script runs the simplest possible version of that idea and checks whether
it has ANY edge at all over the fixed baseline.

Design (deliberately minimal, causal, no lookahead):
  1. Regime signal: trailing 90-day realized volatility of daily log
     returns, split at its own trailing-expanding median into "high-vol"
     / "low-vol" per day. Purely price-derived, no new data source.
  2. Two fixed weight vectors are pre-registered (not fit per regime --
     fitting per regime on the same objective this script evaluates would
     be circular):
       - BASELINE = power_law=1.0, m2=0.5, dxy=0.5 (the validated blend)
       - HIGH_VOL_ALT = several hand-picked alternatives that shift mass
         toward the macro/DXY legs during high-vol regimes, on the
         hypothesis that macro conditions matter more when price is
         thrashing.
  3. For each HIGH_VOL_ALT candidate, splice per-day risk: BASELINE's risk
     on low-vol days, the candidate's risk on high-vol days. Score the
     spliced series with the same combined long+medium cycle-overlap
     objective used everywhere else in this project and compare to the
     fixed-baseline-only objective (137.66, established in
     ``run_halving_cycle_stage2_fixed_baseline.py``).

This is a go/no-go probe for the *mechanism* (does switching ever help at
all), not a proposal to ship regime-switching. Diagnostic only -- never
touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_regime_conditional_reweight_experiment
"""

from __future__ import annotations

import math
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score, risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

VOL_WINDOW = 90
BASELINE = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)

# Hand-picked alternatives for the high-vol regime only. Each shifts mass
# toward macro (m2/dxy) and away from power_law, on the hypothesis that a
# thrashing market makes the slow-moving power-law rail less reliable and
# macro liquidity/dollar-strength conditions more informative.
HIGH_VOL_CANDIDATES = {
    "macro_heavy": SdcaCompositeWeights(power_law=0.5, m2=1.0, dxy=1.0),
    "macro_only": SdcaCompositeWeights(power_law=0.0, m2=1.0, dxy=1.0),
    "dxy_heavy": SdcaCompositeWeights(power_law=0.5, m2=0.5, dxy=1.5),
    "m2_heavy": SdcaCompositeWeights(power_law=0.5, m2=1.5, dxy=0.5),
    "power_law_only": SdcaCompositeWeights(power_law=1.5, m2=0.0, dxy=0.0),
}


def trailing_realized_vol(prices: list[float], window: int) -> list[float | None]:
    """Trailing std-dev of daily log returns, causal (no lookahead)."""
    log_returns: list[float] = [math.nan] * len(prices)
    for i in range(1, len(prices)):
        log_returns[i] = math.log(prices[i] / prices[i - 1])
    out: list[float | None] = [None] * len(prices)
    for i in range(len(prices)):
        start = max(1, i - window + 1)
        if i - start + 1 < window // 2:
            continue
        sample = [r for r in log_returns[start : i + 1] if not math.isnan(r)]
        if len(sample) < 2:
            continue
        mean = sum(sample) / len(sample)
        var = sum((r - mean) ** 2 for r in sample) / (len(sample) - 1)
        out[i] = math.sqrt(var)
    return out


def causal_expanding_median_split(values: list[float | None]) -> list[bool]:
    """True = "high vol" (>= trailing-expanding median seen so far)."""
    seen: list[float] = []
    out: list[bool] = []
    for v in values:
        if v is None:
            out.append(False)
            continue
        seen.append(v)
        sorted_seen = sorted(seen)
        n = len(sorted_seen)
        median = (
            sorted_seen[n // 2]
            if n % 2 == 1
            else (sorted_seen[n // 2 - 1] + sorted_seen[n // 2]) / 2.0
        )
        out.append(v >= median)
    return out


def splice(low_vol_risk: list[float | None], high_vol_risk: list[float | None], is_high_vol: list[bool]) -> list[float | None]:
    return [hv if flag else lv for lv, hv, flag in zip(low_vol_risk, high_vol_risk, is_high_vol, strict=True)]


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    missing = [name for name in ("m2", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(date_s, price_s, rails["low"], rails["median"], rails["high"]).to_list()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_weight, medium_weight = 3.0, 1.0

    def score(risk: list[float | None]) -> float:
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    baseline_risk = risk_from_weighted_z(dates, power_law_z, extra_z, BASELINE)
    baseline_objective = score(baseline_risk)
    print(f"fixed baseline (power_law=1.0, m2=0.5, dxy=0.5), no switching: objective={baseline_objective:.2f}\n")

    vol = trailing_realized_vol(prices, VOL_WINDOW)
    is_high_vol = causal_expanding_median_split(vol)
    high_vol_days = sum(is_high_vol)
    print(f"regime split (trailing {VOL_WINDOW}d realized vol, causal expanding median): "
          f"{high_vol_days} high-vol days / {len(dates) - high_vol_days} low-vol days\n")

    print("=== regime-conditional splice: baseline on low-vol days, candidate on high-vol days ===")
    results = []
    for name, candidate_weights in HIGH_VOL_CANDIDATES.items():
        candidate_risk = risk_from_weighted_z(dates, power_law_z, extra_z, candidate_weights)
        spliced = splice(baseline_risk, candidate_risk, is_high_vol)
        obj = score(spliced)
        results.append((name, obj))
    results.sort(key=lambda r: -r[1])
    for name, obj in results:
        delta = obj - baseline_objective
        print(f"  {name:<16}  objective={obj:.2f}  delta_vs_fixed_baseline={delta:+.2f}")

    best_name, best_obj = results[0]
    print(
        f"\n  best: {best_name} "
        f"({'IMPROVES on fixed baseline -- switching mechanism has signal, worth a real design' if best_obj > baseline_objective else 'no improvement -- switching alone (with these candidates) does not beat the fixed blend'})"
    )

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
