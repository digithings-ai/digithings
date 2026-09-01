"""Price-based long-horizon SDCA votes: weekly RSI/MACD and SMA-band z.

Weekly oscillators are computed on **completed ISO weeks** (Monday-aligned
``truncate("1w")``, last daily close of that week) and broadcast onto daily
dates with ``join_asof(..., strategy="backward")``. A Wednesday never sees
the in-progress week's Friday/Sunday close.

Sign convention matches ``valuation_z``: cheap / buy = +z, rich / sell = −z,
clipped to ``[-3, 3]``.

``weekly_rsi`` is a **dead-zone** map (mid-cycle 30–80 → z≈0, RSI 85 is
max-sell) blended with monthly RSI (``mtf_rsi_z``). Do not affine-map
``(50−RSI)/50`` — that pegs a bull at the floor. ``weekly_macd`` is weekly
**log-MACD** (``log10(EMA12)−log10(EMA26)``) with a sloped diminishing top
cap, not 52-week histogram z (that renormalizes a persistent trend to
neutral). ``SdcaCompositeWeights`` still defaults both to 0; published
``btc_sdca`` turns them on in ``settings.json``.

``sma_band`` stays a 90-day SMA z (Bollinger-style), **not** Mayer / 200w
SMA (*r* ≈ 0.84 vs power-law ``valuation_z``). Alpha vs the power-law
median is collinear with ``valuation_z`` and is omitted — see
``btc_richer_composite.json``.
"""

from __future__ import annotations

from datetime import date

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
_RSI_DEAD_LOW = 30.0
_RSI_DEAD_HIGH = 80.0
_RSI_EXTREME_LOW = 20.0
_RSI_EXTREME_HIGH = 85.0
_LMACD_BOTTOM_DEAD = -0.02
_LMACD_BOTTOM_EXTREME = -0.10
_LMACD_TOP_ANCHOR_YEAR = 2013
_LMACD_TOP_ANCHOR = 0.15
_LMACD_TOP_DECAY_PER_YEAR = 0.005
_LMACD_TOP_FLOOR = 0.09
_LMACD_TOP_CEILING = 0.16
_LMACD_RICH_FRAC = 0.20


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


def documented_warmup_calendar_days(spec: SdcaOscillatorSpec | None = None) -> int:
    """Leading-null budget for generic technicals — not a 2018/2021 cliff.

    Weekly Wilder RSI needs ``rsi_length`` completed ISO weeks, plus the
    first week completing (``(length + 1) * 7`` calendar days). SMA-band
    nulls last ``sma_band_min_samples`` days (default 30), which is shorter.
    Composite extras inherit this short leading gap via the all-nulls rule.
    """
    resolved = spec or SdcaOscillatorSpec()
    rsi_days = (resolved.rsi_length + 1) * 7
    return max(rsi_days, resolved.sma_band_min_samples)


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


def completed_monthly_closes(dates: pl.Series, close: pl.Series) -> pl.DataFrame:
    """Last daily close of each *completed* calendar month. Drops the in-progress month."""
    if dates.len() != close.len():
        raise ValueError("dates and close must be the same length")
    df = pl.DataFrame({"date": dates, "close": close}).sort("date")
    df = df.with_columns(pl.col("date").dt.truncate("1mo").alias("month_start"))
    monthly = (
        df.group_by("month_start")
        .agg(pl.col("date").max().alias("month_end"), pl.col("close").last().alias("close"))
        .sort("month_start")
    )
    last_daily = df["date"].max()
    return monthly.filter(pl.col("month_start").dt.month_end() <= last_daily)


def _asof_to_daily(dates: pl.Series, period_end: pl.Series, values: pl.Series) -> pl.Series:
    daily = pl.DataFrame({"date": dates}).sort("date")
    period = pl.DataFrame({"period_end": period_end, "value": values}).sort("period_end")
    joined = daily.join_asof(period, left_on="date", right_on="period_end", strategy="backward")
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


def rsi_deadzone_z(
    rsi: pl.Series,
    *,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Map RSI onto ``[-3, 3]`` with a mid-cycle dead zone and a capped blow-off."""
    low_span = dead_low - extreme_low
    high_span = extreme_high - dead_high
    rsi_col = pl.col("rsi")
    cheap = ((dead_low - rsi_col) / low_span * 3.0).clip(0.0, 3.0)
    rich = ((dead_high - rsi_col) / high_span * 3.0).clip(-3.0, 0.0)
    mapped = (
        pl.when(rsi_col.is_null())
        .then(None)
        .when(rsi_col < dead_low)
        .then(cheap)
        .when(rsi_col > dead_high)
        .then(rich)
        .otherwise(0.0)
        .alias("rsi_z")
    )
    return pl.DataFrame({"rsi": rsi}).select(mapped)["rsi_z"]


def weekly_rsi_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    length: int = _RSI_LENGTH,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Weekly Wilder RSI → dead-zone z, as-of onto daily dates."""
    weekly = completed_weekly_closes(dates, close)
    rsi = _wilder_rsi(weekly["close"], length=length)
    z = rsi_deadzone_z(
        rsi,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    return _asof_to_daily(dates, weekly["week_end"], z).alias("weekly_rsi")


def monthly_rsi_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    length: int = _RSI_LENGTH,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Monthly Wilder RSI (completed months) → same dead-zone z as weekly."""
    monthly = completed_monthly_closes(dates, close)
    rsi = _wilder_rsi(monthly["close"], length=length)
    z = rsi_deadzone_z(
        rsi,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    return _asof_to_daily(dates, monthly["month_end"], z).alias("monthly_rsi")


def mtf_rsi_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    length: int = _RSI_LENGTH,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Equal blend of weekly + monthly dead-zone RSI. Weekly fills monthly warmup."""
    weekly = weekly_rsi_z(
        dates,
        close,
        length=length,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    monthly = monthly_rsi_z(
        dates,
        close,
        length=length,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    blended: list[float | None] = []
    for week_z, month_z in zip(weekly.to_list(), monthly.to_list(), strict=True):
        if week_z is None and month_z is None:
            blended.append(None)
        elif month_z is None:
            blended.append(week_z)
        elif week_z is None:
            blended.append(month_z)
        else:
            blended.append(0.5 * float(week_z) + 0.5 * float(month_z))
    return pl.Series("weekly_rsi", blended, dtype=pl.Float64)


def lmacd_top_cap(day: date) -> float:
    years = day.year - _LMACD_TOP_ANCHOR_YEAR + (day.timetuple().tm_yday - 1) / 365.25
    raw = _LMACD_TOP_ANCHOR - _LMACD_TOP_DECAY_PER_YEAR * max(years, 0.0)
    return min(_LMACD_TOP_CEILING, max(_LMACD_TOP_FLOOR, raw))


def _lmacd_to_z(lmacd: float | None, top_cap: float) -> float | None:
    if lmacd is None:
        return None
    if lmacd <= _LMACD_BOTTOM_EXTREME:
        return 3.0
    if lmacd < _LMACD_BOTTOM_DEAD:
        span = _LMACD_BOTTOM_DEAD - _LMACD_BOTTOM_EXTREME
        return 3.0 * (_LMACD_BOTTOM_DEAD - lmacd) / span
    rich_start = _LMACD_RICH_FRAC * top_cap
    if lmacd <= rich_start:
        return 0.0
    span = max(top_cap - rich_start, 1e-9)
    return max(-3.0, -3.0 * (lmacd - rich_start) / span)


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
    """Weekly log-MACD with a sloped top cap (not 52-week histogram z)."""
    del signal, z_window, min_samples
    weekly = completed_weekly_closes(dates, close)
    frame = pl.DataFrame({"close": weekly["close"]})
    ema_fast = pl.col("close").ewm_mean(span=fast, adjust=False, min_samples=fast)
    ema_slow = pl.col("close").ewm_mean(span=slow, adjust=False, min_samples=slow)
    with_ema = frame.select(
        ema_fast.clip(lower_bound=_SIGMA_FLOOR).alias("ema_fast"),
        ema_slow.clip(lower_bound=_SIGMA_FLOOR).alias("ema_slow"),
    )
    lmacd = with_ema["ema_fast"].log(10) - with_ema["ema_slow"].log(10)
    week_ends = weekly["week_end"].to_list()
    z_vals = [
        None if v is None else _lmacd_to_z(float(v), lmacd_top_cap(week_end))
        for v, week_end in zip(lmacd.to_list(), week_ends, strict=True)
    ]
    z = pl.Series("weekly_macd", z_vals, dtype=pl.Float64)
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
        "weekly_rsi": mtf_rsi_z(dates, close, length=spec.rsi_length).to_list(),
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
    "completed_monthly_closes",
    "completed_weekly_closes",
    "documented_warmup_calendar_days",
    "lmacd_top_cap",
    "monthly_rsi_z",
    "mtf_rsi_z",
    "price_oscillator_z_vectors",
    "rsi_deadzone_z",
    "sma_band_z",
    "weekly_macd_z",
    "weekly_rsi_z",
]
