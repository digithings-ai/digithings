#!/usr/bin/env python3
"""Phase B Stage 1: solo-validate two OHLC-derived indicators, ``adx`` and ``stochastic``.

Found by the 2026-09-17 wider data-source scan: ``digiquant/src/digiquant/data/prices/technicals.py``
(the Atlas pure-Polars technicals module) computes ADX/+DI/-DI (trend strength) and
Stochastic %K/%D (mean-reversion), neither of which any current SDCA extra uses --
SDCA's own oscillator family only covers RSI/MACD/SMA-band, all derived from
``close`` alone. ADX and Stochastic both need ``high``/``low``, which
``BTC-USD.csv`` already carries with full history (2014-09-17 onward) -- unlike
every recent dead-end/watch candidate, this needs no new data source at all,
just columns of the same cached file nothing else has touched yet.

Indicator definitions (reimplemented standalone here, same math as
``technicals.compute_indicators``, not imported directly since that function
computes a much larger fixed column set for the Atlas pipeline):

- ``adx``: Wilder-smoothed(14) directional movement index, ADX = Wilder-EMA(DX, 14)
  where DX = 100*|+DI - -DI|/(+DI + -DI). Bounded [0, 100]; causal z-scored like
  every other SDCA extra so period search stays comparable.
- ``stochastic``: raw %K = (close - lowest_low(n)) / (highest_high(n) - lowest_low(n)) * 100,
  smoothed by a 3-period SMA (the standard %K line). Bounded [0, 100]; z-scored.

Both cleared for Stage 1 the same way ``run_volume_turnover_solo_validation.py``
was: soloed via ``risk_from_weighted_z``/``combined_cycle_overlap_score`` against
the long+medium cycle-overlap objective, borrowing the ``m2`` weight slot since
neither is (yet) a declared ``SdcaCompositeWeights`` field. See that script's
docstring for why this bypasses ``search_oscillator_periods_by_cycle_overlap``.

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    python scripts/run_adx_stochastic_solo_validation.py
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

ADX_PERIOD_CANDIDATES = [{"period": p} for p in (7, 10, 14, 21, 28, 40)]
STOCH_PERIOD_CANDIDATES = [{"period": p} for p in (5, 9, 14, 21, 28, 40)]

Z_WINDOW = 365


def _wilder_ema(s: pl.Series, length: int) -> pl.Series:
    return s.ewm_mean(alpha=1.0 / length, adjust=False, min_samples=length)


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


def compute_adx(high: pl.Series, low: pl.Series, close: pl.Series, period: int) -> pl.Series:
    df = pl.DataFrame({"high": high, "low": low, "close": close})
    up = pl.col("high").diff()
    down = -pl.col("low").diff()
    prev_close = pl.col("close").shift(1)
    df = df.with_columns(
        pl.when((up > down) & (up > 0)).then(up).otherwise(0.0).alias("plus_dm"),
        pl.when((down > up) & (down > 0)).then(down).otherwise(0.0).alias("minus_dm"),
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - prev_close).abs(),
            (pl.col("low") - prev_close).abs(),
        ).alias("tr"),
    )
    plus_dm_s = _wilder_ema(df["plus_dm"], period)
    minus_dm_s = _wilder_ema(df["minus_dm"], period)
    tr_s = _wilder_ema(df["tr"], period)

    dmi_plus = plus_dm_s / tr_s * 100.0
    dmi_minus = minus_dm_s / tr_s * 100.0
    dx = (dmi_plus - dmi_minus).abs() / (dmi_plus + dmi_minus) * 100.0
    return _wilder_ema(dx, period)


def compute_stochastic_k(high: pl.Series, low: pl.Series, close: pl.Series, period: int) -> pl.Series:
    lowest_low = low.rolling_min(window_size=period, min_samples=period)
    highest_high = high.rolling_max(window_size=period, min_samples=period)
    raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100.0
    return raw_k.rolling_mean(window_size=3, min_samples=3)


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    raw = pl.read_csv(data_path)
    required = {"timestamp", "high", "low", "close"}
    if not required.issubset(raw.columns):
        print(f"{data_path} is missing one of {required} -- cannot run.")
        return
    ts = raw["timestamp"]
    if ts.dtype != pl.Date:
        ts = ts.str.to_datetime().dt.date()
    raw = raw.with_columns(ts.alias("timestamp")).sort("timestamp")

    by_date = {d: i for i, d in enumerate(raw["timestamp"].to_list())}
    missing = [d for d in dates if d not in by_date]
    if missing:
        print(f"{len(missing)} dates missing from OHLC rows (first: {missing[0]}) -- cannot run cleanly.")
        return
    idx = [by_date[d] for d in dates]
    high = raw["high"].cast(pl.Float64)[idx]
    low = raw["low"].cast(pl.Float64)[idx]
    close = raw["close"].cast(pl.Float64)[idx]

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

    def report(name: str, candidates: list[dict[str, int]], compute) -> None:
        print(f"=== Stage 1: {name} solo-validation (period search) ===\n")
        scored = []
        for c in candidates:
            series = compute(c["period"])
            scored.append((c["period"], score_series(series)))
        scored.sort(key=lambda s: -s[1])
        best_period, best_objective = scored[0]
        beats_noise = best_objective > noise_objective
        print(f"best period: {best_period}  combined={best_objective:.2f}")
        print(f"  noise baseline: {noise_objective:.2f}")
        print(f"  RESULT: {'PASS -- clears noise baseline' if beats_noise else 'FAIL -- at/below noise baseline'}\n")
        print("all candidates:")
        for period, objective in scored:
            print(f"  period={period:>4}  combined={objective:.2f}")
        print()

    report("adx", ADX_PERIOD_CANDIDATES, lambda p: compute_adx(high, low, close, p))
    report("stochastic", STOCH_PERIOD_CANDIDATES, lambda p: compute_stochastic_k(high, low, close, p))


if __name__ == "__main__":
    run()
