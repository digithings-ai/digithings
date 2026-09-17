#!/usr/bin/env python3
"""Phase B Stage 2: floor-diversified aggregate reweight of the validated
power_law/m2/dxy baseline plus the two Stage-1 winners, ``adx`` and
``stochastic`` (see ``run_adx_stochastic_solo_validation.py`` -- both
cleared Stage 1 on 2026-09-17: ADX(40) combined=53.21, Stochastic(9)
combined=34.30, vs. a 0.00 noise baseline).

``adx``/``stochastic`` are now declared ``SdcaCompositeWeights`` fields
(indicator_catalog.py), which is all ``optimize_stage_a_weights_combined``
needs to include them in the grid search -- it builds
``SdcaCompositeWeights(power_law=..., **{name: weight, ...})`` per
candidate and only requires the resulting weights object to validate and
every enabled name to have a precomputed ``extra_z`` entry. Neither is yet
wired into ``build_extra_indicators``/``ExtraIndicatorSources`` (that needs
high/low OHLC plumbing no current source-loading path carries) -- this
script sidesteps that gap the same way the Stage 1 script did, by computing
the two z-series directly from ``BTC-USD.csv``'s OHLC columns and handing
them to the optimizer's ``extra_z`` dict alongside ``m2``/``dxy`` loaded the
normal way via ``load_sdca_extra_z``. That gap must close before any
Stage 3/4 candidate built from this reweight can run through the standard
``build_risk_index``/``run_sdca_walk_forward`` production path -- tracked as
a follow-up, not attempted here.

Per the Phase B acceptance rule: a candidate earns a real place in the mix
only if its optimized weight lands strictly above the 0.1 floor -- pinned
at the floor means the floor forced it in, not that it added signal.

Never touches settings.json/RESEARCH_STATE.md per the standing gate.

Usage:
    uv run python -m scripts.run_adx_stochastic_stage2_reweight
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.composite_risk import causal_rolling_z
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import optimize_stage_a_weights_combined_multi_ratio

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"

# Stage 1 winners (run_adx_stochastic_solo_validation.py, 2026-09-17).
ADX_PERIOD = 40
STOCHASTIC_PERIOD = 9
Z_WINDOW = 365

SEARCH_NAMES = ["m2", "dxy", "adx", "stochastic"]
GRID = (0.1, 0.55, 1.0)
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
    adx_series = compute_adx(high, low, close, ADX_PERIOD)
    stoch_series = compute_stochastic_k(high, low, close, STOCHASTIC_PERIOD)
    extra_z["adx"] = causal_rolling_z(
        adx_series, window=Z_WINDOW, min_samples=max(20, Z_WINDOW // 2)
    ).to_list()
    extra_z["stochastic"] = causal_rolling_z(
        stoch_series, window=Z_WINDOW, min_samples=max(20, Z_WINDOW // 2)
    ).to_list()

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"]
    ).to_list()

    print(f"=== Stage 2: floor-diversified reweight ({SEARCH_NAMES}, floor={FLOOR}) ===\n")
    results = optimize_stage_a_weights_combined_multi_ratio(
        dates,
        power_law_z=power_law_z,
        extra_z=extra_z,
        long_windows=long_windows,
        medium_windows=medium_windows,
        search_names=SEARCH_NAMES,
        grid=GRID,
        power_law_grid=GRID,
        ratios=((2.0, 1.0), (3.0, 1.0), (5.0, 1.0)),
        min_weight_floor=FLOOR,
    )

    for ratio, result in results.items():
        w = result.weights
        print(f"ratio {ratio[0]:.0f}:{ratio[1]:.0f} -- objective={result.score.objective:.2f}")
        print(f"  weights: {w.model_dump()}")
        for name in SEARCH_NAMES:
            val = getattr(w, name)
            status = "ABOVE FLOOR (real signal)" if val > FLOOR else (
                "at floor (no added signal)" if val > 0.0 else "disabled"
            )
            print(f"    {name:>12}: {val:.2f}  {status}")
        print()

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
