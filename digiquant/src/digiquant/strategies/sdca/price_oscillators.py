"""Price-based long-horizon SDCA votes: weekly RSI/MACD and SMA-band z.

Weekly oscillators are computed on **completed ISO weeks** (Monday-aligned
``truncate("1w")``, last daily close of that week) and broadcast onto daily
dates with ``join_asof(..., strategy="backward")``. A Wednesday never sees
the in-progress week's Friday/Sunday close.

Sign convention matches ``valuation_z``: cheap / buy = +z, rich / sell = −z,
clipped to ``[-3, 3]``.

``weekly_rsi`` is a **dead-zone** map (mid-cycle 30–80 → z≈0, RSI 85 is
max-sell) fed into an **agreement-scaled confluence** of weekly (long-term)
and daily (medium-term) RSI (``rsi_confluence_z``): a weighted blend of the
two dead-zone z-scores, amplified when the timeframes agree in sign and
damped toward 0 when they conflict. ``mtf_rsi_z`` (weekly/monthly blend)
stays as a diagnostic. Do not affine-map ``(50−RSI)/50`` — that pegs a bull
at the floor.

``weekly_macd`` is the same agreement-scaled pattern applied to log-MACD
(``macd_confluence_z``): a weekly leg (``log10(EMA12)−log10(EMA26)`` on
completed weekly closes) with a sloped diminishing top cap and bottom dead
zone — not 52-week histogram z, which renormalizes a persistent trend to
neutral — blended with a daily leg (``daily_macd_z``) that *is* a rolling
z-score of its own recent lmacd, since a medium-term momentum dip needs to
register against recent normal rather than an absolute, secular-scale
threshold. ``SdcaCompositeWeights`` still defaults both to 0; published
``btc_sdca`` turns them on in ``settings.json``.

``sma_band`` is the same agreement-scaled pattern applied to the Bollinger-
style SMA z (``sma_band_confluence_z``): a slow leg (``sma_band_z`` at the
original 90-day window, long-term) blended with a fast leg (``sma_band_z``
at a shorter window, medium-term). Unlike RSI/MACD, both legs share one
formula — timeframe separation comes purely from window length, since
``sma_band_z`` never aggregates to weekly bars. Still **not** Mayer / 200w
SMA (*r* ≈ 0.84 vs power-law ``valuation_z``). Alpha vs the power-law
median is collinear with ``valuation_z`` and is omitted — see
``btc_richer_composite.json``.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

_RSI_LENGTH = 14
_RSI_DAILY_LENGTH = 14
_RSI_CONFLUENCE_WEEKLY_WEIGHT = 0.5
_RSI_CONFLUENCE_AGREEMENT_BOOST = 0.5
_RSI_CONFLUENCE_DISAGREEMENT_DAMP = 0.5
_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9
_MACD_Z_WINDOW = 52
_MACD_Z_MIN_SAMPLES = 20
_MACD_DAILY_FAST = 12
_MACD_DAILY_SLOW = 26
_MACD_DAILY_Z_WINDOW = 90
_MACD_DAILY_Z_MIN_SAMPLES = 30
_MACD_CONFLUENCE_WEEKLY_WEIGHT = 0.5
_MACD_CONFLUENCE_AGREEMENT_BOOST = 0.5
_MACD_CONFLUENCE_DISAGREEMENT_DAMP = 0.5
_SMA_BAND_WINDOW = 90
_SMA_BAND_MIN_SAMPLES = 30
_SMA_BAND_FAST_WINDOW = 20
_SMA_BAND_FAST_MIN_SAMPLES = 10
_SMA_BAND_CONFLUENCE_SLOW_WEIGHT = 0.5
_SMA_BAND_CONFLUENCE_AGREEMENT_BOOST = 0.5
_SMA_BAND_CONFLUENCE_DISAGREEMENT_DAMP = 0.5
_RS_ETH_WINDOW = 90
_RS_ETH_MIN_SAMPLES = 20
_RS_ETH_FAST_WINDOW = 30
_RS_ETH_FAST_MIN_SAMPLES = 15
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
    90-day SMA-band used on BTC. ``rsi_length`` is the long-term weekly leg
    of the RSI confluence (``rsi_confluence_z``); ``daily_rsi_length`` is
    its medium-term daily leg. Likewise ``macd_fast``/``macd_slow`` are the
    long-term weekly leg of the MACD confluence (``macd_confluence_z``);
    ``macd_daily_fast``/``macd_daily_slow`` are its medium-term daily leg,
    rolling-z-scored over ``macd_daily_z_window`` (``macd_daily_min_samples``
    warmup) instead of the weekly leg's absolute top-cap thresholds.
    ``sma_band_window``/``sma_band_min_samples`` are the long-term slow leg
    of the SMA-band confluence (``sma_band_confluence_z``);
    ``sma_band_fast_window``/``sma_band_fast_min_samples`` are its
    medium-term fast leg — same formula, shorter window.
    ``rs_eth_window``/``rs_eth_min_samples`` and
    ``rs_eth_fast_window``/``rs_eth_fast_min_samples`` configure
    ``rs_eth_confluence_z`` (``indicator_catalog.py``) the same way — BTC/ETH
    relative strength is not a price-oscillator technical, but reuses this
    spec as the one per-indicator-period config object already threaded
    through ``build_extra_indicators``.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    rsi_length: int = Field(_RSI_LENGTH, ge=2)
    daily_rsi_length: int = Field(_RSI_DAILY_LENGTH, ge=2)
    macd_fast: int = Field(_MACD_FAST, ge=2)
    macd_slow: int = Field(_MACD_SLOW, ge=3)
    macd_signal: int = Field(_MACD_SIGNAL, ge=2)
    macd_z_window: int = Field(_MACD_Z_WINDOW, ge=2)
    macd_daily_fast: int = Field(_MACD_DAILY_FAST, ge=2)
    macd_daily_slow: int = Field(_MACD_DAILY_SLOW, ge=3)
    macd_daily_z_window: int = Field(_MACD_DAILY_Z_WINDOW, ge=2)
    macd_daily_min_samples: int = Field(_MACD_DAILY_Z_MIN_SAMPLES, ge=2)
    sma_band_window: int = Field(_SMA_BAND_WINDOW, ge=2)
    sma_band_min_samples: int = Field(_SMA_BAND_MIN_SAMPLES, ge=2)
    sma_band_fast_window: int = Field(_SMA_BAND_FAST_WINDOW, ge=2)
    sma_band_fast_min_samples: int = Field(_SMA_BAND_FAST_MIN_SAMPLES, ge=2)
    rs_eth_window: int = Field(_RS_ETH_WINDOW, ge=2)
    rs_eth_min_samples: int = Field(_RS_ETH_MIN_SAMPLES, ge=2)
    rs_eth_fast_window: int = Field(_RS_ETH_FAST_WINDOW, ge=2)
    rs_eth_fast_min_samples: int = Field(_RS_ETH_FAST_MIN_SAMPLES, ge=2)

    @model_validator(mode="after")
    def _ordered(self) -> SdcaOscillatorSpec:
        if self.macd_slow <= self.macd_fast:
            raise ValueError("macd_slow must be greater than macd_fast")
        if self.macd_daily_slow <= self.macd_daily_fast:
            raise ValueError("macd_daily_slow must be greater than macd_daily_fast")
        if self.macd_daily_min_samples > self.macd_daily_z_window:
            raise ValueError("macd_daily_min_samples must be <= macd_daily_z_window")
        if self.sma_band_min_samples > self.sma_band_window:
            raise ValueError("sma_band_min_samples must be <= sma_band_window")
        if self.sma_band_fast_min_samples > self.sma_band_fast_window:
            raise ValueError("sma_band_fast_min_samples must be <= sma_band_fast_window")
        if self.rs_eth_min_samples > self.rs_eth_window:
            raise ValueError("rs_eth_min_samples must be <= rs_eth_window")
        if self.rs_eth_fast_min_samples > self.rs_eth_fast_window:
            raise ValueError("rs_eth_fast_min_samples must be <= rs_eth_fast_window")
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


def daily_rsi_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    length: int = _RSI_DAILY_LENGTH,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Daily Wilder RSI (medium-term) → dead-zone z. No as-of broadcast needed.

    Wilder's smoothing is already causal on the daily series, unlike the
    weekly/monthly legs which aggregate first and then join-asof onto daily
    dates.
    """
    if dates.len() != close.len():
        raise ValueError("dates and close must be the same length")
    rsi = _wilder_rsi(close, length=length)
    return rsi_deadzone_z(
        rsi,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    ).alias("daily_rsi")


def agreement_scaled_blend(
    long_term_z: pl.Series,
    medium_term_z: pl.Series,
    *,
    long_term_weight: float,
    agreement_boost: float,
    disagreement_damp: float,
    name: str,
) -> pl.Series:
    """Blend two timeframe legs, amplified on sign-agreement, damped on conflict.

    A ``long_term_weight``/``1 - long_term_weight`` blend of the two z-scores
    is the anchor. When both legs share sign, the blend is scaled up toward
    ``1 + agreement_boost`` (more so the closer their magnitudes are — full
    agreement, not just same-sign noise). When they disagree in sign, the
    blend is damped to ``disagreement_damp`` of its value — the timeframes
    are fighting, so the combined vote should say less, not more. Either leg
    sitting at exactly 0 passes the other through unscaled: a silent
    timeframe is not a disagreement. Result stays clipped to ``[-3, 3]``.
    """
    medium_term_weight = 1.0 - long_term_weight
    blended: list[float | None] = []
    for lv, mv in zip(long_term_z.to_list(), medium_term_z.to_list(), strict=True):
        if lv is None and mv is None:
            blended.append(None)
        elif mv is None:
            blended.append(lv)
        elif lv is None:
            blended.append(mv)
        else:
            base = long_term_weight * float(lv) + medium_term_weight * float(mv)
            if lv == 0.0 or mv == 0.0:
                multiplier = 1.0
            elif (lv > 0) == (mv > 0):
                agreement_frac = min(abs(lv), abs(mv)) / max(abs(lv), abs(mv))
                multiplier = 1.0 + agreement_boost * agreement_frac
            else:
                multiplier = disagreement_damp
            blended.append(max(-3.0, min(3.0, base * multiplier)))
    return pl.Series(name, blended, dtype=pl.Float64)


def rsi_confluence_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    weekly_length: int = _RSI_LENGTH,
    daily_length: int = _RSI_DAILY_LENGTH,
    weekly_weight: float = _RSI_CONFLUENCE_WEEKLY_WEIGHT,
    agreement_boost: float = _RSI_CONFLUENCE_AGREEMENT_BOOST,
    disagreement_damp: float = _RSI_CONFLUENCE_DISAGREEMENT_DAMP,
    dead_low: float = _RSI_DEAD_LOW,
    dead_high: float = _RSI_DEAD_HIGH,
    extreme_low: float = _RSI_EXTREME_LOW,
    extreme_high: float = _RSI_EXTREME_HIGH,
) -> pl.Series:
    """Weekly (long-term) + daily (medium-term) RSI, amplified on agreement.

    A ``weekly_weight``/``1 - weekly_weight`` blend of the two dead-zone
    z-scores is the anchor. When both legs share sign, the blend is scaled
    up toward ``1 + agreement_boost`` (more so the closer their magnitudes
    are — full agreement, not just same-sign noise). When they disagree in
    sign, the blend is damped to ``disagreement_damp`` of its value — the
    timeframes are fighting, so the sub-score should say less, not more.
    Either leg sitting at the dead-zone (z == 0) passes the other through
    unscaled: a silent timeframe is not a disagreement. Result stays
    clipped to ``[-3, 3]``.
    """
    weekly = weekly_rsi_z(
        dates,
        close,
        length=weekly_length,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    daily = daily_rsi_z(
        dates,
        close,
        length=daily_length,
        dead_low=dead_low,
        dead_high=dead_high,
        extreme_low=extreme_low,
        extreme_high=extreme_high,
    )
    return agreement_scaled_blend(
        weekly,
        daily,
        long_term_weight=weekly_weight,
        agreement_boost=agreement_boost,
        disagreement_damp=disagreement_damp,
        name="weekly_rsi",
    )


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


def daily_macd_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    fast: int = _MACD_DAILY_FAST,
    slow: int = _MACD_DAILY_SLOW,
    z_window: int = _MACD_DAILY_Z_WINDOW,
    min_samples: int = _MACD_DAILY_Z_MIN_SAMPLES,
) -> pl.Series:
    """Daily log-MACD (medium-term), rolling-z-scored against its own recent history.

    The weekly leg's absolute lmacd thresholds (dead zone + decaying top cap)
    are tuned for the wide, slow-moving weekly amplitude and BTC's secular
    top-decay — reusing them here would misfire, since daily-bar log-MACD has
    a different characteristic scale. A few-months momentum dip needs to
    register relative to *recent* normal instead, so this is a causal rolling
    z-score of the daily lmacd value, sign-flipped (momentum unusually low
    vs its own history = cheap = +z) — the same convention as ``sma_band_z``.
    """
    if dates.len() != close.len():
        raise ValueError("dates and close must be the same length")
    frame = pl.DataFrame({"close": close})
    ema_fast = pl.col("close").ewm_mean(span=fast, adjust=False, min_samples=fast)
    ema_slow = pl.col("close").ewm_mean(span=slow, adjust=False, min_samples=slow)
    with_ema = frame.select(
        ema_fast.clip(lower_bound=_SIGMA_FLOOR).alias("ema_fast"),
        ema_slow.clip(lower_bound=_SIGMA_FLOOR).alias("ema_slow"),
    )
    lmacd = with_ema["ema_fast"].log(10) - with_ema["ema_slow"].log(10)
    return (-_causal_z(lmacd, window=z_window, min_samples=min_samples)).alias("daily_macd")


def macd_confluence_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    weekly_fast: int = _MACD_FAST,
    weekly_slow: int = _MACD_SLOW,
    daily_fast: int = _MACD_DAILY_FAST,
    daily_slow: int = _MACD_DAILY_SLOW,
    daily_z_window: int = _MACD_DAILY_Z_WINDOW,
    daily_min_samples: int = _MACD_DAILY_Z_MIN_SAMPLES,
    weekly_weight: float = _MACD_CONFLUENCE_WEEKLY_WEIGHT,
    agreement_boost: float = _MACD_CONFLUENCE_AGREEMENT_BOOST,
    disagreement_damp: float = _MACD_CONFLUENCE_DISAGREEMENT_DAMP,
) -> pl.Series:
    """Weekly (long-term) + daily (medium-term) log-MACD, amplified on agreement.

    Same agreement-scaled blend as ``rsi_confluence_z``. The weekly leg keeps
    its secular top-cap/dead-zone mapping (``weekly_macd_z``); the daily leg
    is a rolling z-score of its own recent lmacd (``daily_macd_z``), so a
    few-months momentum dip inside an otherwise-rich weekly regime still
    registers instead of being swallowed by the slow-moving weekly leg.
    """
    weekly = weekly_macd_z(dates, close, fast=weekly_fast, slow=weekly_slow)
    daily = daily_macd_z(
        dates,
        close,
        fast=daily_fast,
        slow=daily_slow,
        z_window=daily_z_window,
        min_samples=daily_min_samples,
    )
    return agreement_scaled_blend(
        weekly,
        daily,
        long_term_weight=weekly_weight,
        agreement_boost=agreement_boost,
        disagreement_damp=disagreement_damp,
        name="weekly_macd",
    )


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


def sma_band_confluence_z(
    dates: pl.Series,
    close: pl.Series,
    *,
    slow_window: int = _SMA_BAND_WINDOW,
    slow_min_samples: int = _SMA_BAND_MIN_SAMPLES,
    fast_window: int = _SMA_BAND_FAST_WINDOW,
    fast_min_samples: int = _SMA_BAND_FAST_MIN_SAMPLES,
    slow_weight: float = _SMA_BAND_CONFLUENCE_SLOW_WEIGHT,
    agreement_boost: float = _SMA_BAND_CONFLUENCE_AGREEMENT_BOOST,
    disagreement_damp: float = _SMA_BAND_CONFLUENCE_DISAGREEMENT_DAMP,
) -> pl.Series:
    """Slow (long-term) + fast (medium-term) SMA-band z, amplified on agreement.

    Same agreement-scaled blend as ``rsi_confluence_z``/``macd_confluence_z``.
    Unlike RSI/MACD, both legs are the same daily Bollinger-style z
    (``sma_band_z``) — timeframe separation comes purely from window length,
    since ``sma_band_z`` never aggregates to weekly bars in the first place.
    """
    slow = sma_band_z(dates, close, window=slow_window, min_samples=slow_min_samples)
    fast = sma_band_z(dates, close, window=fast_window, min_samples=fast_min_samples)
    return agreement_scaled_blend(
        slow,
        fast,
        long_term_weight=slow_weight,
        agreement_boost=agreement_boost,
        disagreement_damp=disagreement_damp,
        name="sma_band",
    )


def price_oscillator_z_vectors(
    dates: pl.Series,
    close: pl.Series,
    oscillators: SdcaOscillatorSpec | None = None,
) -> dict[str, list[float | None]]:
    """Causal extra-z for walk-forward slicing. Works on any asset's close."""
    spec = oscillators or SdcaOscillatorSpec()
    return {
        "weekly_rsi": rsi_confluence_z(
            dates,
            close,
            weekly_length=spec.rsi_length,
            daily_length=spec.daily_rsi_length,
        ).to_list(),
        "weekly_macd": macd_confluence_z(
            dates,
            close,
            weekly_fast=spec.macd_fast,
            weekly_slow=spec.macd_slow,
            daily_fast=spec.macd_daily_fast,
            daily_slow=spec.macd_daily_slow,
            daily_z_window=spec.macd_daily_z_window,
            daily_min_samples=spec.macd_daily_min_samples,
        ).to_list(),
        "sma_band": sma_band_confluence_z(
            dates,
            close,
            slow_window=spec.sma_band_window,
            slow_min_samples=spec.sma_band_min_samples,
            fast_window=spec.sma_band_fast_window,
            fast_min_samples=spec.sma_band_fast_min_samples,
        ).to_list(),
    }


__all__ = [
    "SdcaOscillatorSpec",
    "agreement_scaled_blend",
    "completed_monthly_closes",
    "completed_weekly_closes",
    "daily_macd_z",
    "daily_rsi_z",
    "documented_warmup_calendar_days",
    "lmacd_top_cap",
    "macd_confluence_z",
    "monthly_rsi_z",
    "mtf_rsi_z",
    "price_oscillator_z_vectors",
    "rsi_confluence_z",
    "rsi_deadzone_z",
    "sma_band_confluence_z",
    "sma_band_z",
    "weekly_macd_z",
    "weekly_rsi_z",
]
