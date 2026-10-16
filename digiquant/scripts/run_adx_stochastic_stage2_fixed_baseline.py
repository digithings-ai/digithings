#!/usr/bin/env python3
"""Phase B Stage 2, alternative framing: does ADX/Stochastic add signal
*on top of* the validated baseline, rather than competing with m2/dxy for
share of a floor-forced 4-way mix?

``run_adx_stochastic_stage2_reweight.py`` floored all four of
m2/dxy/adx/stochastic together and found every one pinned at the 0.1 floor
-- logged as a tentative reject, but flagged with a framing caveat: a
3-point coarse grid floor-forcing four names to split weight may starve
any new candidate of headroom regardless of real signal, independent of
whether it actually helps.

This script tests the fairer alternative: **fix** the already-validated
baseline (power_law=1.0, m2=0.5, dxy=0.5, the published +84.8-84.9% OOS
config) and grid-search *only* adx/stochastic's weights on top of it, with
the 0.1 floor applied to the two new candidates alone. If neither earns
weight above the floor even with the baseline held constant and full grid
headroom, that is a cleaner, unconfounded rejection.

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_adx_stochastic_stage2_fixed_baseline
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

ADX_PERIOD = 40
STOCHASTIC_PERIOD = 9
Z_WINDOW = 365

# The validated, published baseline -- held fixed throughout this script.
BASELINE_POWER_LAW = 1.0
BASELINE_M2 = 0.5
BASELINE_DXY = 0.5

# Full headroom grid for the two candidates alone (not sharing with m2/dxy).
CANDIDATE_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
FLOOR = 0.1


def _wilder_ema(s: pl.Series, length: int) -> pl.Series:
    return s.ewm_mean(alpha=1.0 / length, adjust=False, min_samples=length)


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


def load_ohlc(data_path: Path, dates: list) -> tuple[pl.Series, pl.Series, pl.Series]:
    raw = pl.read_csv(data_path)
    ts = raw["timestamp"]
    if ts.dtype != pl.Date:
        ts = ts.str.to_datetime().dt.date()
    raw = raw.with_columns(ts.alias("timestamp")).sort("timestamp")
    by_date = {d: i for i, d in enumerate(raw["timestamp"].to_list())}
    idx = [by_date[d] for d in dates]
    high = raw["high"].cast(pl.Float64)[idx]
    low = raw["low"].cast(pl.Float64)[idx]
    close = raw["close"].cast(pl.Float64)[idx]
    return high, low, close


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    missing = [name for name in ("m2", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    high, low, close = load_ohlc(data_path, dates)
    extra_z["adx"] = causal_rolling_z(
        compute_adx(high, low, close, ADX_PERIOD), window=Z_WINDOW, min_samples=max(20, Z_WINDOW // 2)
    ).to_list()
    extra_z["stochastic"] = causal_rolling_z(
        compute_stochastic_k(high, low, close, STOCHASTIC_PERIOD),
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

    def score_for(adx_w: float, stoch_w: float) -> float:
        weights = SdcaCompositeWeights(
            power_law=BASELINE_POWER_LAW,
            m2=BASELINE_M2,
            dxy=BASELINE_DXY,
            adx=adx_w,
            stochastic=stoch_w,
        )
        risk = risk_from_weighted_z(dates, power_law_z, extra_z, weights)
        return combined_cycle_overlap_score(
            dates, risk, long_windows, medium_windows,
            long_weight=long_weight, medium_weight=medium_weight,
        ).objective

    baseline_objective = score_for(0.0, 0.0)
    print(f"fixed baseline (power_law=1.0, m2=0.5, dxy=0.5) objective: {baseline_objective:.2f}\n")

    print("=== adx alone (stochastic=0.0), grid-searched on top of fixed baseline ===")
    adx_scored = [(w, score_for(w, 0.0)) for w in CANDIDATE_GRID if w > 0.0]
    adx_scored.sort(key=lambda s: -s[1])
    for w, obj in adx_scored:
        delta = obj - baseline_objective
        print(f"  adx={w:.2f}  objective={obj:.2f}  delta_vs_baseline={delta:+.2f}")
    best_adx_w, best_adx_obj = adx_scored[0]
    print(
        f"  best: adx={best_adx_w:.2f} "
        f"({'IMPROVES on baseline' if best_adx_obj > baseline_objective else 'no improvement'})\n"
    )

    print("=== stochastic alone (adx=0.0), grid-searched on top of fixed baseline ===")
    stoch_scored = [(w, score_for(0.0, w)) for w in CANDIDATE_GRID if w > 0.0]
    stoch_scored.sort(key=lambda s: -s[1])
    for w, obj in stoch_scored:
        delta = obj - baseline_objective
        print(f"  stochastic={w:.2f}  objective={obj:.2f}  delta_vs_baseline={delta:+.2f}")
    best_stoch_w, best_stoch_obj = stoch_scored[0]
    print(
        f"  best: stochastic={best_stoch_w:.2f} "
        f"({'IMPROVES on baseline' if best_stoch_obj > baseline_objective else 'no improvement'})\n"
    )

    print("=== both together, joint grid on top of fixed baseline ===")
    joint_scored = []
    for aw in CANDIDATE_GRID:
        for sw in CANDIDATE_GRID:
            joint_scored.append((aw, sw, score_for(aw, sw)))
    joint_scored.sort(key=lambda s: -s[2])
    best_aw, best_sw, best_obj = joint_scored[0]
    print(f"  best: adx={best_aw:.2f}  stochastic={best_sw:.2f}  objective={best_obj:.2f}")
    print(
        f"  vs fixed baseline ({baseline_objective:.2f}): "
        f"{'IMPROVES' if best_obj > baseline_objective else 'no improvement'} "
        f"(delta={best_obj - baseline_objective:+.2f})\n"
    )
    print("top 5 joint combos:")
    for aw, sw, obj in joint_scored[:5]:
        print(f"  adx={aw:.2f}  stochastic={sw:.2f}  objective={obj:.2f}  delta={obj - baseline_objective:+.2f}")

    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
