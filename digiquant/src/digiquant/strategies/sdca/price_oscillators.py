"""Price-based long-horizon SDCA votes: weekly RSI/MACD and SMA-band z.

Weekly oscillators are computed on **completed ISO weeks** (Monday-aligned
``truncate("1w")``, last daily close of that week) and broadcast onto daily
dates with ``join_asof(..., strategy="backward")``. A Wednesday never sees
the in-progress week's Friday/Sunday close.

Sign convention matches ``valuation_z``: cheap / buy = +z, rich / sell = −z,
clipped to ``[-3, 3]``.

``weekly_macd`` is *not* a second equal vote with ``weekly_rsi`` (research
*r* ≈ 0.65). Default its composite weight to 0; Stage A may turn it on.
``sma_band`` is close vs a 90-day SMA in σ units (Bollinger-style), **not**
raw realized vol (unsigned) and **not** Mayer / 200w SMA (*r* ≈ 0.84 vs
power-law ``valuation_z``).

Alpha vs the power-law median is collinear with ``valuation_z`` and is
omitted — see ARCHITECTURE.md.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

_RSI_LENGTH = 14
_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9
_MACD_Z_WINDOW = 52
_MACD_Z_MIN_SAMPLES = 20
_SMA_BAND_WINDOW = 90
_SMA_BAND_MIN_SAMPLES = 30
_SIGMA_FLOOR = 1e-12
_WEEK_DAYS = 6  # Monday start + 6 days → Sunday (ISO week complete)


class SdcaOscillatorSpec(BaseModel):
    """Per-asset RSI / MACD / SMA-band windows. BTC v1 is the default.

    Calibrate to that asset's cycle (long-term, or medium-term if it
    persistently trends up). These are generic technicals — they are not
    BTC-only. Defaults match the original weekly RSI(14) / MACD(12,26,9) /
    90-day SMA-band used on BTC.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    rsi_length: int = Field(_RSI_LENGTH, ge=2)
    macd_fast: int = Field(_MACD_FAST, ge=2)
    macd_slow: int = Field(_MACD_SLOW, ge=3)
    macd_signal: int = Field(_MACD_SIGNAL, ge=2)
    macd_z_window: int = Field(_MACD_Z_WINDOW, ge=2)
    sma_band_window: int = Field(_SMA_BAND_WINDOW, ge=2)
    sma_band_min_samples: int = Field(_SMA_BAND_MIN_SAMPLES, ge=2)

    @model_validator(mode="after")
    def _ordered(self) -> SdcaOscillatorSpec:
        if self.macd_slow <= self.macd_fast:
            raise ValueError("macd_slow must be greater than macd_fast")
        if self.sma_band_min_samples > self.sma_band_window:
            raise ValueError("sma_band_min_samples must be <= sma_band_window")
        return self


def completed_weekly_closes(dates: pl.Series, close: pl.Series) -> pl.DataFrame:
    """Last daily close of each *completed* ISO week. Drops the in-progress week."""
    if dates.len() != close.len():
        raise ValueError("dates and close must be the same length")
    df = pl.DataFrame({"date": dates, "close": close}).sort("date")
    df = df.with_columns(pl.col("date").dt.truncate("1w").alias("week_start"))
    weekly = (
        df.group_by("week_start")
        .agg(pl.col("date").max().alias("week_end"), pl.col("close").last().alias("close"))
        .sort("week_start")
    )
    last_daily = df["date"].max()
    return weekly.filter(pl.col("week_start") + pl.duration(days=_WEEK_DAYS) <= last_daily)


def _asof_to_daily(dates: pl.Series, week_end: pl.Series, values: pl.Series) -> pl.Series:
    daily = pl.DataFrame({"date": dates}).sort("date")
    weekly = pl.DataFrame({"week_end": week_end, "value": values}).sort("week_end")
    joined = daily.join_asof(weekly, left_on="date", right_on="week_end", strategy="backward")
    return joined["value"]


def _wilder_rsi(close: pl.Series, length: int = _RSI_LENGTH) -> pl.Series:
    frame = pl.DataFrame({"close": close})
    delta = pl.col("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)
    avg_loss = loss.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return frame.select(rsi.alias("rsi"))["rsi"]


def _causal_z(values: pl.Series, *, window: int, min_samples: int) -> pl.Series:
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def weekly_rsi_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    length: int = _RSI_LENGTH,
) -> pl.Series:
    """Weekly Wilder RSI → ``(50 − RSI) / 50 × 3``, as-of onto daily dates."""
    weekly = completed_weekly_closes(dates, close)
    rsi = _wilder_rsi(weekly["close"], length=length)
    z = ((50.0 - rsi) / 50.0 * 3.0).clip(-3.0, 3.0)
    return _asof_to_daily(dates, weekly["week_end"], z).alias("weekly_rsi")


def weekly_macd_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    fast: int = _MACD_FAST,
    slow: int = _MACD_SLOW,
    signal: int = _MACD_SIGNAL,
    z_window: int = _MACD_Z_WINDOW,
    min_samples: int = _MACD_Z_MIN_SAMPLES,
) -> pl.Series:
    """Weekly MACD histogram rolling-z of ``−hist`` (bullish hist → rich → −z)."""
    weekly = completed_weekly_closes(dates, close)
    frame = pl.DataFrame({"close": weekly["close"]})
    ema_fast = pl.col("close").ewm_mean(span=fast, adjust=False, min_periods=fast)
    ema_slow = pl.col("close").ewm_mean(span=slow, adjust=False, min_periods=slow)
    macd = ema_fast - ema_slow
    with_macd = frame.select(macd.alias("macd"))
    signal_line = with_macd.select(
        pl.col("macd").ewm_mean(span=signal, adjust=False, min_periods=signal)
    )["macd"]
    hist = with_macd["macd"] - signal_line
    z = _causal_z(-hist, window=z_window, min_samples=min_samples)
    return _asof_to_daily(dates, weekly["week_end"], z).alias("weekly_macd")


def sma_band_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    window: int = _SMA_BAND_WINDOW,
    min_samples: int = _SMA_BAND_MIN_SAMPLES,
) -> pl.Series:
    """Close vs slow SMA in σ units, sign-flipped: below the band is cheap (+z).

    Raw realized vol has no valuation sign (high vol ≠ cheap). This is a
    90-day Bollinger-style z, not Mayer / 200-week SMA.
    """
    if dates.len() != close.len():
        raise ValueError("dates and close must be the same length")
    mu = close.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = close.rolling_std(window_size=window, min_samples=min_samples)
    raw = (close - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)
    return (-raw).clip(-3.0, 3.0).alias("sma_band")


def price_oscillator_z_vectors(
    dates: pl.Series,
    close: pl.Series,
    oscillators: SdcaOscillatorSpec | None = None,
) -> dict[str, list[float | None]]:
    """Causal extra-z for walk-forward slicing. Works on any asset's close."""
    spec = oscillators or SdcaOscillatorSpec()
    return {
        "weekly_rsi": weekly_rsi_z(dates, close, length=spec.rsi_length).to_list(),
        "weekly_macd": weekly_macd_z(
            dates,
            close,
            fast=spec.macd_fast,
            slow=spec.macd_slow,
            signal=spec.macd_signal,
            z_window=spec.macd_z_window,
        ).to_list(),
        "sma_band": sma_band_z(
            dates,
            close,
            window=spec.sma_band_window,
            min_samples=spec.sma_band_min_samples,
        ).to_list(),
    }


__all__ = [
    "SdcaOscillatorSpec",
    "completed_weekly_closes",
    "price_oscillator_z_vectors",
    "sma_band_z",
    "weekly_macd_z",
    "weekly_rsi_z",
]
