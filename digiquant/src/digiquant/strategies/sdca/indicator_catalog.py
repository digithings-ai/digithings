"""Named extra indicators for the SDCA composite-risk vote.

The engine already blends ``Σ(zᵢ·wᵢ)/Σ(wᵢ)`` then
``risk = 50 − z×50/3`` (``composite_risk.py``). Extras are either **macro**
(independent of BTC close: M2, BTC/ETH, DXY) or **price oscillators**
(weekly RSI / weekly log-MACD / 90d SMA-band z). Oscillators are
long-horizon votes; they are **not** Mayer / 200w SMA (near-duplicate of
``power_law_z``).

``rs_eth`` is the same agreement-scaled multi-timeframe pattern used by the
price oscillators (``price_oscillators.py``), applied to the BTC/ETH log
ratio: ``rs_eth_confluence_z`` blends a slow leg (``rs_eth_z`` at a 90-day
window, long-term rotation) with a fast leg (30-day, medium-term rotation).
``m2``/``dxy`` stay single-window — they track slow macro regimes without a
comparably fast rotation to confluence against.

``SdcaCompositeWeights`` defaults ``power_law=1``, extras ``0`` (disabled,
excluded from the blend). Published ``btc_sdca`` in ``settings.json`` turns
on M2, DXY, weekly log-MACD, and MTF weekly/monthly RSI — see
``btc_richer_composite.json``. Model defaults stay extras-off so a missing
macro row cannot null an unpublished path.

Omitted on purpose (see ARCHITECTURE.md):
- Mayer / 200w SMA — *r* ≈ 0.84 vs ``power_law_z`` (research PR #3232)
- a second power-law residual ("alpha") — collinear with ``power_law_z``
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

from digiquant.strategies.sdca.composite_risk import IndicatorWeight, causal_rolling_z
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    agreement_scaled_blend,
    macd_confluence_z,
    monthly_macd_confluence_z,
    monthly_rsi_confluence_z,
    price_oscillator_z_vectors,
    rsi_confluence_z,
    sma_band_confluence_z,
)

MACRO_INDICATOR_NAMES: tuple[str, ...] = ("m2", "rs_eth", "dxy")
PRICE_OSCILLATOR_NAMES: tuple[str, ...] = (
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
    "monthly_rsi",
    "monthly_macd",
)
GENERIC_TECHNICAL_NAMES: tuple[str, ...] = PRICE_OSCILLATOR_NAMES
BTC_PLUGIN_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES
EXTRA_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES + PRICE_OSCILLATOR_NAMES
DEFAULT_ROLLING_WINDOW = 90
_MIN_SAMPLES = 20
_RS_ETH_CONFLUENCE_SLOW_WEIGHT = 0.5
_RS_ETH_CONFLUENCE_AGREEMENT_BOOST = 0.5
_RS_ETH_CONFLUENCE_DISAGREEMENT_DAMP = 0.5
WEIGHT_PARAM_BY_NAME: dict[str, str] = {
    "power_law": "power_law_weight",
    "m2": "m2_weight",
    "rs_eth": "rs_eth_weight",
    "dxy": "dxy_weight",
    "weekly_rsi": "weekly_rsi_weight",
    "weekly_macd": "weekly_macd_weight",
    "sma_band": "sma_band_weight",
    "monthly_rsi": "monthly_rsi_weight",
    "monthly_macd": "monthly_macd_weight",
}

# User-facing labels. The fallback (``name.replace("_", " ")``) covers every
# id here; this dict only overrides ids where that fallback reads wrong.
INDICATOR_DISPLAY_NAMES: dict[str, str] = {
    "m2": "M2 liquidity",
    "rs_eth": "BTC/ETH relative strength",
    "dxy": "DXY",
    "weekly_rsi": "weekly RSI",
    "weekly_macd": "weekly log-MACD",
    "sma_band": "SMA band",
    "monthly_rsi": "monthly RSI",
    "monthly_macd": "monthly log-MACD",
}


def indicator_display_name(name: str) -> str:
    """Chart/UI label for an indicator code id (``power_law`` → ``power law``)."""
    return INDICATOR_DISPLAY_NAMES.get(name, name.replace("_", " "))


class SdcaCompositeWeights(BaseModel):
    """Non-negative weights. Zero means disabled (not in the blend)."""

    model_config = ConfigDict(frozen=True, strict=True)

    power_law: float = Field(1.0, ge=0.0)
    m2: float = Field(0.0, ge=0.0)
    rs_eth: float = Field(0.0, ge=0.0)
    dxy: float = Field(0.0, ge=0.0)
    weekly_rsi: float = Field(0.0, ge=0.0)
    weekly_macd: float = Field(0.0, ge=0.0)
    sma_band: float = Field(0.0, ge=0.0)
    # Monthly-cadence siblings of weekly_rsi/weekly_macd
    # (price_oscillators.monthly_rsi_confluence_z / monthly_macd_confluence_z).
    # Wired into build_extra_indicators below; earned production status via
    # the all-9 floor-diversified aggregate search in
    # scripts/run_dual_timeframe_composite_search.py (RESEARCH_STATE.md).
    monthly_rsi: float = Field(0.0, ge=0.0)
    monthly_macd: float = Field(0.0, ge=0.0)

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
            ("monthly_rsi", self.monthly_rsi),
            ("monthly_macd", self.monthly_macd),
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
        power_law=float(params.get("power_law_weight", 1.0)),
        m2=float(params.get("m2_weight", 0.0)),
        rs_eth=float(params.get("rs_eth_weight", 0.0)),
        dxy=float(params.get("dxy_weight", 0.0)),
        weekly_rsi=float(params.get("weekly_rsi_weight", 0.0)),
        weekly_macd=float(params.get("weekly_macd_weight", 0.0)),
        sma_band=float(params.get("sma_band_weight", 0.0)),
        monthly_rsi=float(params.get("monthly_rsi_weight", 0.0)),
        monthly_macd=float(params.get("monthly_macd_weight", 0.0)),
    )


def parse_indicator_weights_json(raw: str) -> SdcaCompositeWeights:
    """MCP/settings JSON object. Empty → power-law-only default."""
    text = raw.strip() if raw else ""
    payload: object = json.loads(text) if text else {}
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("indicator_weights must be a JSON object")
    return SdcaCompositeWeights(
        power_law=float(payload.get("power_law", 1.0)),
        m2=float(payload.get("m2", 0.0)),
        rs_eth=float(payload.get("rs_eth", 0.0)),
        dxy=float(payload.get("dxy", 0.0)),
        weekly_rsi=float(payload.get("weekly_rsi", 0.0)),
        weekly_macd=float(payload.get("weekly_macd", 0.0)),
        sma_band=float(payload.get("sma_band", 0.0)),
        monthly_rsi=float(payload.get("monthly_rsi", 0.0)),
        monthly_macd=float(payload.get("monthly_macd", 0.0)),
    )


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


def m2_liquidity_z(
    dates: pl.Series,
    m2_dates: pl.Series,
    m2_values: pl.Series,
    *,
    roc_days: int = 365,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """YoY (or ``roc_days``) M2 growth, rolling-z. Expanding liquidity → +z (buy)."""
    aligned = align_to_dates(dates, m2_dates, m2_values, forward_fill=True)
    roc = aligned / aligned.shift(roc_days) - 1.0
    return causal_rolling_z(roc, window=window, min_samples=min_samples)


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


def rs_eth_confluence_z(
    dates: pl.Series,
    btc_price: pl.Series,
    eth_dates: pl.Series,
    eth_close: pl.Series,
    *,
    slow_window: int = DEFAULT_ROLLING_WINDOW,
    slow_min_samples: int = _MIN_SAMPLES,
    fast_window: int = 30,
    fast_min_samples: int = 15,
    slow_weight: float = _RS_ETH_CONFLUENCE_SLOW_WEIGHT,
    agreement_boost: float = _RS_ETH_CONFLUENCE_AGREEMENT_BOOST,
    disagreement_damp: float = _RS_ETH_CONFLUENCE_DISAGREEMENT_DAMP,
) -> pl.Series:
    """Slow (long-term) + fast (medium-term) BTC/ETH relative-strength z.

    Same agreement-scaled blend as the price-oscillator confluences
    (``rsi_confluence_z`` / ``macd_confluence_z`` / ``sma_band_confluence_z``
    in ``price_oscillators.py``). Like ``sma_band_confluence_z``, both legs
    share one formula — ``rs_eth_z``'s rolling z of the BTC/ETH log ratio —
    so timeframe separation is window length, not bar-aggregation. BTC/ETH
    rotation has both a slow, multi-quarter cycle and faster swings, so a
    two-timeframe read fits the ratio the same way it fits a price band.
    """
    slow = rs_eth_z(
        dates, btc_price, eth_dates, eth_close, window=slow_window, min_samples=slow_min_samples
    )
    fast = rs_eth_z(
        dates, btc_price, eth_dates, eth_close, window=fast_window, min_samples=fast_min_samples
    )
    return agreement_scaled_blend(
        slow,
        fast,
        long_term_weight=slow_weight,
        agreement_boost=agreement_boost,
        disagreement_damp=disagreement_damp,
        name="rs_eth",
    )


def dxy_z(
    dates: pl.Series,
    dxy_dates: pl.Series,
    dxy_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Dollar index rolling-z, sign-flipped: strong dollar → −z (headwind)."""
    aligned = align_to_dates(dates, dxy_dates, dxy_values, forward_fill=True)
    return (-causal_rolling_z(aligned, window=window, min_samples=min_samples)).alias("dxy")


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
    """Materialize enabled extras, plus the always-on price oscillators for display.

    M2 and DXY are only materialized at weight > 0 (a zero weight omits them
    entirely, so a missing macro row never nulls the blend). Everything else
    — the price oscillators (``weekly_rsi`` / ``weekly_macd`` / ``sma_band``)
    plus ``rs_eth`` when its ETH source series is available — is allowlist-
    gated only, not weight-gated: always materialized with ``enabled=False``
    when its weight is 0, so ``build_risk_index`` can still write its
    z-series into the risk parquet for the frontend Indicators tab, while
    ``compute_composite_risk`` (which filters on ``ind.enabled``, not
    weight) excludes it from the actual composite risk / trading signal
    exactly as before. ``rs_eth`` still requires its ETH source pair when
    its weight is positive (``_require_pair`` raises if missing); at weight
    0 with no ETH source loaded it's simply omitted, same as before.

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
    rs_eth_allowed = allowlist is None or "rs_eth" in allowlist
    rs_eth_has_source = sources.eth_dates is not None and sources.eth_close is not None
    if rs_eth_allowed and (weights.rs_eth > 0.0 or rs_eth_has_source):
        eth_dates = _require_pair(sources.eth_dates, sources.eth_close, "rs_eth")
        extras.append(
            IndicatorWeight(
                name="rs_eth",
                z=rs_eth_confluence_z(
                    dates,
                    btc_price,
                    eth_dates,
                    sources.eth_close,  # type: ignore[arg-type]
                    slow_window=spec.rs_eth_window,
                    slow_min_samples=spec.rs_eth_min_samples,
                    fast_window=spec.rs_eth_fast_window,
                    fast_min_samples=spec.rs_eth_fast_min_samples,
                ),
                weight=weights.rs_eth,
                enabled=weights.rs_eth > 0.0,
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
    if allowlist is None or "weekly_rsi" in allowlist:
        extras.append(
            IndicatorWeight(
                name="weekly_rsi",
                z=rsi_confluence_z(
                    dates,
                    btc_price,
                    weekly_length=spec.rsi_length,
                    daily_length=spec.daily_rsi_length,
                ),
                weight=weights.weekly_rsi,
                enabled=weights.weekly_rsi > 0.0,
            )
        )
    if allowlist is None or "weekly_macd" in allowlist:
        extras.append(
            IndicatorWeight(
                name="weekly_macd",
                z=macd_confluence_z(
                    dates,
                    btc_price,
                    weekly_fast=spec.macd_fast,
                    weekly_slow=spec.macd_slow,
                    daily_fast=spec.macd_daily_fast,
                    daily_slow=spec.macd_daily_slow,
                    daily_z_window=spec.macd_daily_z_window,
                    daily_min_samples=spec.macd_daily_min_samples,
                ),
                weight=weights.weekly_macd,
                enabled=weights.weekly_macd > 0.0,
            )
        )
    if allowlist is None or "sma_band" in allowlist:
        extras.append(
            IndicatorWeight(
                name="sma_band",
                z=sma_band_confluence_z(
                    dates,
                    btc_price,
                    slow_window=spec.sma_band_window,
                    slow_min_samples=spec.sma_band_min_samples,
                    fast_window=spec.sma_band_fast_window,
                    fast_min_samples=spec.sma_band_fast_min_samples,
                ),
                weight=weights.sma_band,
                enabled=weights.sma_band > 0.0,
            )
        )
    if allowlist is None or "monthly_rsi" in allowlist:
        extras.append(
            IndicatorWeight(
                name="monthly_rsi",
                z=monthly_rsi_confluence_z(
                    dates,
                    btc_price,
                    monthly_length=spec.monthly_rsi_length,
                    daily_length=spec.monthly_rsi_daily_length,
                ),
                weight=weights.monthly_rsi,
                enabled=weights.monthly_rsi > 0.0,
            )
        )
    if allowlist is None or "monthly_macd" in allowlist:
        extras.append(
            IndicatorWeight(
                name="monthly_macd",
                z=monthly_macd_confluence_z(
                    dates,
                    btc_price,
                    monthly_fast=spec.monthly_macd_fast,
                    monthly_slow=spec.monthly_macd_slow,
                    daily_fast=spec.macd_daily_fast,
                    daily_slow=spec.macd_daily_slow,
                    daily_z_window=spec.macd_daily_z_window,
                    daily_min_samples=spec.macd_daily_min_samples,
                ),
                weight=weights.monthly_macd,
                enabled=weights.monthly_macd > 0.0,
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
    "rs_eth_confluence_z",
    "rs_eth_z",
    "sources_from_optional_paths",
]
