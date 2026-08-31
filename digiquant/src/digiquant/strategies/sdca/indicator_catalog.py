"""Named extra indicators for the SDCA composite-risk vote.

The engine already blends ``Σ(zᵢ·wᵢ)/Σ(wᵢ)`` then
``risk = 50 − z×50/3`` (``composite_risk.py``). Extras are either **macro**
(independent of BTC close: M2, BTC/ETH, DXY) or **price oscillators**
(weekly RSI / weekly MACD / 90d SMA-band z). Oscillators are user-requested
long-horizon votes; they are **not** Mayer / 200w SMA (near-duplicate of
power-law ``valuation_z``). Weekly MACD defaults to weight 0 because it
correlates ~0.65 with weekly RSI — do not equal-weight the pair.

Default weights keep published BTC charts unchanged: ``valuation=1``, extras
``0`` (disabled, excluded from the blend, so a missing macro row cannot null
the day). Positive weights are searched by Stage A / walk-forward.

Omitted on purpose (see ARCHITECTURE.md):
- Mayer / 200w SMA — *r* ≈ 0.84 vs ``valuation_z`` (research PR #3232)
- a second power-law residual ("alpha") — collinear with ``valuation_z``
- on-chain MVRV/NUPL — #1086, no in-repo history
- equity CAPE / Buffett / ERP — #3176 forbade equity RiskModel in v1
- RS rotation pool — #1084; this module only uses ETH from the Coinbase cache
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    price_oscillator_z_vectors,
    sma_band_z,
    weekly_macd_z,
    weekly_rsi_z,
)

MACRO_INDICATOR_NAMES: tuple[str, ...] = ("m2", "rs_eth", "dxy")
PRICE_OSCILLATOR_NAMES: tuple[str, ...] = ("weekly_rsi", "weekly_macd", "sma_band")
GENERIC_TECHNICAL_NAMES: tuple[str, ...] = PRICE_OSCILLATOR_NAMES
BTC_PLUGIN_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES
EXTRA_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES + PRICE_OSCILLATOR_NAMES
DEFAULT_ROLLING_WINDOW = 90
_MIN_SAMPLES = 20
_SIGMA_FLOOR = 1e-12
WEIGHT_PARAM_BY_NAME: dict[str, str] = {
    "valuation": "valuation_weight",
    "m2": "m2_weight",
    "rs_eth": "rs_eth_weight",
    "dxy": "dxy_weight",
    "weekly_rsi": "weekly_rsi_weight",
    "weekly_macd": "weekly_macd_weight",
    "sma_band": "sma_band_weight",
}

# User-facing labels. Code ids stay ``valuation``; charts must say "power law".
INDICATOR_DISPLAY_NAMES: dict[str, str] = {
    "valuation": "power law",
    "m2": "M2 liquidity",
    "rs_eth": "BTC/ETH relative strength",
    "dxy": "DXY",
    "weekly_rsi": "weekly RSI",
    "weekly_macd": "weekly MACD",
    "sma_band": "SMA band",
}


def indicator_display_name(name: str) -> str:
    """Chart/UI label for an indicator code id (``valuation`` → ``power law``)."""
    return INDICATOR_DISPLAY_NAMES.get(name, name.replace("_", " "))


class SdcaCompositeWeights(BaseModel):
    """Non-negative weights. Zero means disabled (not in the blend)."""

    model_config = ConfigDict(frozen=True, strict=True)

    valuation: float = Field(1.0, ge=0.0)
    m2: float = Field(0.0, ge=0.0)
    rs_eth: float = Field(0.0, ge=0.0)
    dxy: float = Field(0.0, ge=0.0)
    weekly_rsi: float = Field(0.0, ge=0.0)
    weekly_macd: float = Field(0.0, ge=0.0)
    sma_band: float = Field(0.0, ge=0.0)

    @model_validator(mode="after")
    def _at_least_one_positive(self) -> SdcaCompositeWeights:
        if sum(self.model_dump().values()) <= 0.0:
            raise ValueError("at least one indicator weight must be positive")
        return self

    def extra_items(self) -> tuple[tuple[str, float], ...]:
        return (
            ("m2", self.m2),
            ("rs_eth", self.rs_eth),
            ("dxy", self.dxy),
            ("weekly_rsi", self.weekly_rsi),
            ("weekly_macd", self.weekly_macd),
            ("sma_band", self.sma_band),
        )

    def enabled_extras(self) -> dict[str, float]:
        return {name: weight for name, weight in self.extra_items() if weight > 0.0}

    def normalized(self) -> SdcaCompositeWeights:
        payload = self.model_dump()
        total = sum(payload.values())
        return SdcaCompositeWeights(**{name: value / total for name, value in payload.items()})


class ExtraIndicatorSources(BaseModel):
    """Optional aligned series. Missing sources are fine while the weight is 0."""

    model_config = ConfigDict(frozen=True, strict=True, arbitrary_types_allowed=True)

    m2_dates: pl.Series | None = None
    m2_values: pl.Series | None = None
    eth_dates: pl.Series | None = None
    eth_close: pl.Series | None = None
    dxy_dates: pl.Series | None = None
    dxy_values: pl.Series | None = None


def composite_weights_from_params(params: Mapping[str, float | int | str]) -> SdcaCompositeWeights:
    """Read ``*_weight`` keys used by ``strategy_specs`` / walk-forward."""
    return SdcaCompositeWeights(
        valuation=float(params.get("valuation_weight", 1.0)),
        m2=float(params.get("m2_weight", 0.0)),
        rs_eth=float(params.get("rs_eth_weight", 0.0)),
        dxy=float(params.get("dxy_weight", 0.0)),
        weekly_rsi=float(params.get("weekly_rsi_weight", 0.0)),
        weekly_macd=float(params.get("weekly_macd_weight", 0.0)),
        sma_band=float(params.get("sma_band_weight", 0.0)),
    )


def parse_indicator_weights_json(raw: str) -> SdcaCompositeWeights:
    """MCP/settings JSON object. Empty → valuation-only default."""
    text = raw.strip() if raw else ""
    payload: object = json.loads(text) if text else {}
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("indicator_weights must be a JSON object")
    return SdcaCompositeWeights(
        valuation=float(payload.get("valuation", 1.0)),
        m2=float(payload.get("m2", 0.0)),
        rs_eth=float(payload.get("rs_eth", 0.0)),
        dxy=float(payload.get("dxy", 0.0)),
        weekly_rsi=float(payload.get("weekly_rsi", 0.0)),
        weekly_macd=float(payload.get("weekly_macd", 0.0)),
        sma_band=float(payload.get("sma_band", 0.0)),
    )


def causal_rolling_z(
    values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Rolling z in ``[-3, 3]``. Each day uses only that day and prior window."""
    if window < 2:
        raise ValueError(f"rolling window must be >= 2, got {window}")
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def align_to_dates(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    forward_fill: bool,
) -> pl.Series:
    """Left-join ``src`` onto ``dates``. Macro series typically forward-fill."""
    if dates.dtype != pl.Date:
        raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
    src = (
        pl.DataFrame({"date": src_dates, "value": src_values})
        .unique(subset=["date"], keep="last")
        .sort("date")
    )
    joined = pl.DataFrame({"date": dates}).join(src, on="date", how="left")
    if forward_fill:
        joined = joined.with_columns(pl.col("value").forward_fill())
    return joined["value"]


def _full_calendar_values(
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    until: date,
) -> tuple[pl.Series, pl.Series]:
    """Dense daily calendar from the first source obs through ``until``.

    Macro YoY / rolling-z warmup belongs on this calendar, not on the BTC
    window after an inner join (that amputates leading Coinbase years).
    """
    native = (
        pl.DataFrame({"date": src_dates, "value": src_values})
        .drop_nulls()
        .unique(subset=["date"], keep="last")
        .sort("date")
    )
    if native.is_empty():
        return (
            pl.Series("date", [], dtype=pl.Date),
            pl.Series("value", [], dtype=pl.Float64),
        )
    start = native["date"][0]
    last_src = native["date"][-1]
    end = until if until >= last_src else last_src
    if end < start:
        end = start
    calendar = pl.select(pl.date_range(start, end, interval="1d", eager=True).alias("date"))
    dense = calendar.join(native, on="date", how="left").with_columns(
        pl.col("value").forward_fill()
    )
    return dense["date"], dense["value"]


def m2_liquidity_z(
    dates: pl.Series,
    m2_dates: pl.Series,
    m2_values: pl.Series,
    *,
    roc_days: int = 365,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """YoY (or ``roc_days``) M2 growth, rolling-z. Expanding liquidity → +z (buy).

    YoY and rolling-z run on the **full** FRED series (dense daily from the
    first observation), then the z is aligned onto ``dates``. Shifting after
    joining onto Coinbase BTC days would null the first year even when M2SL
    exists back to 1959.
    """
    if dates.dtype != pl.Date:
        raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
    until = dates.max()
    cal_dates, cal_values = _full_calendar_values(m2_dates, m2_values, until=until)
    if cal_dates.len() == 0:
        return pl.Series([None] * dates.len(), dtype=pl.Float64)
    roc = cal_values / cal_values.shift(roc_days) - 1.0
    z_full = causal_rolling_z(roc, window=window, min_samples=min_samples)
    return align_to_dates(dates, cal_dates, z_full, forward_fill=True)


def rs_eth_z(
    dates: pl.Series,
    btc_price: pl.Series,
    eth_dates: pl.Series,
    eth_close: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """``log(BTC/ETH)`` rolling-z, sign-flipped: BTC cheap vs ETH → +z."""
    eth = align_to_dates(dates, eth_dates, eth_close, forward_fill=False)
    ratio = (btc_price / eth).log()
    return (-causal_rolling_z(ratio, window=window, min_samples=min_samples)).alias("rs_eth")


def dxy_z(
    dates: pl.Series,
    dxy_dates: pl.Series,
    dxy_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Dollar index rolling-z, sign-flipped: strong dollar → −z (headwind).

    Rolling-z runs on the full DXY calendar, then aligns onto ``dates``, so
    Coinbase-era BTC days are not charged the 90-day warmup a second time.
    """
    if dates.dtype != pl.Date:
        raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
    until = dates.max()
    cal_dates, cal_values = _full_calendar_values(dxy_dates, dxy_values, until=until)
    if cal_dates.len() == 0:
        return pl.Series([None] * dates.len(), dtype=pl.Float64).alias("dxy")
    z_full = causal_rolling_z(cal_values, window=window, min_samples=min_samples)
    aligned = align_to_dates(dates, cal_dates, z_full, forward_fill=True)
    return (-aligned).alias("dxy")


def build_extra_indicators(
    dates: pl.Series,
    btc_price: pl.Series,
    weights: SdcaCompositeWeights,
    sources: ExtraIndicatorSources,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
    roc_days: int = 365,
    oscillators: SdcaOscillatorSpec | None = None,
    allowlist: Sequence[str] | None = None,
) -> list[IndicatorWeight]:
    """Materialize enabled extras. Weight 0 is omitted (does not null the blend).

    ``btc_price`` is the *asset* close (BTC, ETH, or another series). Macro
    extras (M2 / rs_eth / DXY) are BTC-oriented plugins; pass ``allowlist``
    from ``SdcaAssetProfile.extra_indicators`` so a second asset cannot
    silently vote with BTC-only series.
    """
    spec = oscillators or SdcaOscillatorSpec()
    enabled = weights.enabled_extras()
    if allowlist is not None:
        forbidden = [name for name in enabled if name not in allowlist]
        if forbidden:
            raise ValueError(f"{forbidden} not in extra_indicators allowlist")
    extras: list[IndicatorWeight] = []
    if "m2" in enabled:
        m2_dates = _require_pair(sources.m2_dates, sources.m2_values, "m2")
        extras.append(
            IndicatorWeight(
                name="m2",
                z=m2_liquidity_z(
                    dates,
                    m2_dates,
                    sources.m2_values,  # type: ignore[arg-type]
                    roc_days=roc_days,
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["m2"],
            )
        )
    if "rs_eth" in enabled:
        eth_dates = _require_pair(sources.eth_dates, sources.eth_close, "rs_eth")
        extras.append(
            IndicatorWeight(
                name="rs_eth",
                z=rs_eth_z(
                    dates,
                    btc_price,
                    eth_dates,
                    sources.eth_close,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["rs_eth"],
            )
        )
    if "dxy" in enabled:
        dxy_dates = _require_pair(sources.dxy_dates, sources.dxy_values, "dxy")
        extras.append(
            IndicatorWeight(
                name="dxy",
                z=dxy_z(
                    dates,
                    dxy_dates,
                    sources.dxy_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["dxy"],
            )
        )
    if "weekly_rsi" in enabled:
        extras.append(
            IndicatorWeight(
                name="weekly_rsi",
                z=weekly_rsi_z(dates, btc_price, length=spec.rsi_length),
                weight=enabled["weekly_rsi"],
            )
        )
    if "weekly_macd" in enabled:
        extras.append(
            IndicatorWeight(
                name="weekly_macd",
                z=weekly_macd_z(
                    dates,
                    btc_price,
                    fast=spec.macd_fast,
                    slow=spec.macd_slow,
                    signal=spec.macd_signal,
                    z_window=spec.macd_z_window,
                ),
                weight=enabled["weekly_macd"],
            )
        )
    if "sma_band" in enabled:
        extras.append(
            IndicatorWeight(
                name="sma_band",
                z=sma_band_z(
                    dates,
                    btc_price,
                    window=spec.sma_band_window,
                    min_samples=spec.sma_band_min_samples,
                ),
                weight=enabled["sma_band"],
            )
        )
    return extras


def missing_extra_names(
    weights: SdcaCompositeWeights,
    extra_z: Mapping[str, Sequence[float | None]] | None,
) -> tuple[str, ...]:
    """Enabled extras that have no precomputed z series."""
    have = set(extra_z or {})
    return tuple(name for name in weights.enabled_extras() if name not in have)


def extra_indicators_for_window(
    window_dates: Sequence[date],
    all_dates: Sequence[date],
    extra_z: Mapping[str, Sequence[float | None]],
    weights: SdcaCompositeWeights,
) -> list[IndicatorWeight]:
    """Slice precomputed causal extra-z onto a walk-forward window (no refit)."""
    index = {d: i for i, d in enumerate(all_dates)}
    extras: list[IndicatorWeight] = []
    for name, weight in weights.enabled_extras().items():
        series = extra_z.get(name)
        if series is None:
            raise ValueError(f"positive weight for {name!r} but no extra_z series")
        if len(series) != len(all_dates):
            raise ValueError(
                f"extra_z[{name!r}] length {len(series)} != dates length {len(all_dates)}"
            )
        z_vals = [series[index[d]] for d in window_dates]
        extras.append(
            IndicatorWeight(name=name, z=pl.Series(z_vals, dtype=pl.Float64), weight=weight)
        )
    return extras


def extra_z_vectors(
    dates: pl.Series,
    btc_price: pl.Series,
    weights: SdcaCompositeWeights,
    sources: ExtraIndicatorSources,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
    roc_days: int = 365,
    oscillators: SdcaOscillatorSpec | None = None,
    allowlist: Sequence[str] | None = None,
) -> dict[str, list[float | None]]:
    """Full-calendar extra-z for walk-forward slicing (causal; no OOS leak)."""
    extras = build_extra_indicators(
        dates,
        btc_price,
        weights,
        sources,
        window=window,
        min_samples=min_samples,
        roc_days=roc_days,
        oscillators=oscillators,
        allowlist=allowlist,
    )
    vectors = {ind.name: ind.z.to_list() for ind in extras}
    # Always precompute oscillators from close so a later trial can enable them.
    vectors.update(price_oscillator_z_vectors(dates, btc_price, oscillators=oscillators))
    return vectors


def sources_from_optional_paths(
    *,
    m2_path: Path | str | None = None,
    dxy_path: Path | str | None = None,
    eth_dates: pl.Series | None = None,
    eth_close: pl.Series | None = None,
) -> ExtraIndicatorSources:
    """Build sources from optional on-disk macro files plus an ETH close series."""
    m2_dates = m2_values = None
    if m2_path is not None:
        m2_dates, m2_values = load_date_value_frame(m2_path)
    dxy_dates = dxy_values = None
    if dxy_path is not None:
        dxy_dates, dxy_values = load_date_value_frame(dxy_path)
    return ExtraIndicatorSources(
        m2_dates=m2_dates,
        m2_values=m2_values,
        eth_dates=eth_dates,
        eth_close=eth_close,
        dxy_dates=dxy_dates,
        dxy_values=dxy_values,
    )


def load_date_value_frame(path: Path | str) -> tuple[pl.Series, pl.Series]:
    """CSV/parquet with a date column and a value column.

    Accepts ``date`` / ``timestamp`` / ``observation_date`` (FRED fredgraph.csv)
    plus ``value`` / ``close`` or the remaining numeric series column.
    """
    dest = Path(path)
    if not dest.exists():
        raise ValueError(f"macro/extra series file not found: {dest}")
    frame = pl.read_parquet(dest) if dest.suffix.lower() == ".parquet" else pl.read_csv(dest)
    date_col = next(
        (c for c in ("date", "timestamp", "observation_date", "DATE") if c in frame.columns),
        None,
    )
    if date_col is None:
        raise ValueError(
            f"{dest} needs a date/timestamp/observation_date column, got {frame.columns}"
        )
    value_col = next((c for c in ("value", "close") if c in frame.columns), None)
    if value_col is None:
        numeric = [c for c in frame.columns if c != date_col and frame.schema[c].is_numeric()]
        if len(numeric) != 1:
            raise ValueError(f"{dest} needs a value or close column, got {frame.columns}")
        value_col = numeric[0]
    dates = frame[date_col]
    if dates.dtype != pl.Date:
        if isinstance(dates.dtype, pl.Datetime):
            dates = dates.cast(pl.Date)
        else:
            dates = dates.str.to_datetime(strict=False).cast(pl.Date)
    values = frame[value_col].cast(pl.Float64)
    cleaned = (
        pl.DataFrame({"date": dates, "value": values})
        .drop_nulls()
        .unique(subset=["date"], keep="last")
    )
    return cleaned["date"], cleaned["value"]


def _require_pair(dates: pl.Series | None, values: pl.Series | None, name: str) -> pl.Series:
    if dates is None or values is None:
        raise ValueError(f"positive weight for {name!r} but no source series")
    return dates


__all__ = [
    "BTC_PLUGIN_INDICATOR_NAMES",
    "DEFAULT_ROLLING_WINDOW",
    "EXTRA_INDICATOR_NAMES",
    "GENERIC_TECHNICAL_NAMES",
    "MACRO_INDICATOR_NAMES",
    "PRICE_OSCILLATOR_NAMES",
    "WEIGHT_PARAM_BY_NAME",
    "INDICATOR_DISPLAY_NAMES",
    "ExtraIndicatorSources",
    "SdcaCompositeWeights",
    "align_to_dates",
    "build_extra_indicators",
    "causal_rolling_z",
    "composite_weights_from_params",
    "dxy_z",
    "extra_indicators_for_window",
    "extra_z_vectors",
    "indicator_display_name",
    "load_date_value_frame",
    "m2_liquidity_z",
    "missing_extra_names",
    "parse_indicator_weights_json",
    "rs_eth_z",
    "sources_from_optional_paths",
]
