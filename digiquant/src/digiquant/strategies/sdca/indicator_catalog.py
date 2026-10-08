"""Named extra indicators for the SDCA composite-risk vote.

The engine already blends ``Σ(zᵢ·wᵢ)/Σ(wᵢ)`` then
``risk = 50 − z×50/3`` (``composite_risk.py``). Extras are either **macro**
(independent of BTC close: M2, BTC/ETH, DXY) or **price oscillators**
(weekly RSI / weekly log-MACD / 90d SMA-band z). Oscillators are
long-horizon votes; they are **not** Mayer / 200w SMA (near-duplicate of
power-law ``valuation_z``).

``SdcaCompositeWeights`` defaults ``valuation=1``, extras ``0`` (disabled,
excluded from the blend). Published ``btc_sdca`` in ``settings.json`` turns
on M2, DXY, weekly log-MACD, and MTF weekly/monthly RSI — see
``btc_richer_composite.json``. Model defaults stay extras-off so a missing
macro row cannot null an unpublished path.

Omitted on purpose (see ARCHITECTURE.md):
- Mayer / 200w SMA — *r* ≈ 0.84 vs ``valuation_z`` (research PR #3232)
- a second power-law residual ("alpha") — collinear with ``valuation_z``
- equity CAPE / Buffett / ERP — #3176 forbade equity RiskModel in v1
- RS rotation pool — #1084; this module only uses ETH from the Coinbase cache

Research-only families (ported from ``claude/sdca-develop-sync`` in DIG-1597)
------------------------------------------------------------------
Seven weights were added with the branch: ``onchain_mvrv`` / ``onchain_asopr``
/ ``onchain_puell`` / ``onchain_rhodl`` (Bitview/BRK), ``onchain_addr_ratio``
(CoinMetrics ``AdrActCnt``), ``fear_greed`` (alternative.me) and
``fast_crash_vol``. All default to ``0.0`` and none of their ids are in
``MACRO_INDICATOR_NAMES`` / ``EXTRA_INDICATOR_NAMES``, so they are **dormant**:
nothing published changes, and Stage A / weight search do not widen their
default scope. They are reachable only by setting a weight and supplying a
source. Two reasons for keeping them out of the published tuples: those tuples
drive the BTC asset-profile allowlist (``asset_profile.py``) and the chart
layout (``chart_series.py``), so widening them is a behaviour change rather
than a port; and the branch's own docstrings call these unvalidated pending a
solo-validation gate.

- **On-chain ratios** (MVRV, aSOPR, Puell, RHODL) share one core,
  ``_log_ratio_sign_flipped_z``: each is a strictly-positive, right-skewed
  multiplicative ratio, so it is log-transformed before the rolling z (a
  bull-market spike would otherwise dominate a level-based rolling std), then
  sign-flipped like ``dxy_z`` — an elevated ratio (overheated/euphoric) is
  sell-favorable (−z), a depressed one (capitulation) is buy-favorable (+z).
  Provider ready since #1086.
- ``onchain_addr_ratio`` is a network-usage read, not a price-derived
  transform: ``btc_price / active_addresses`` (NVT/Metcalfe-style). It is
  computed here rather than fetched pre-derived, because CoinMetrics ships the
  raw daily ``AdrActCnt`` (free, no auth, full history to 2010). Pre-adoption
  days report 0 addresses, so the divide must be guarded.
- ``fear_greed`` is pure **sentiment** — the one extra not derived from price
  or the chain. Read contrarian (extreme fear near lows, greed near highs) and
  therefore sign-flipped like ``dxy_z``: elevated ("greed") → −z. Single-window
  like ``m2``/``dxy``; there is no comparably fast sentiment rotation to
  confluence against.
- ``fast_crash_vol`` is the opposite design choice: every extra above is a
  slow structural read that lags a sharp move by construction, so this one is
  deliberately fast — a 14-day realized volatility of daily log returns (vs
  ``DEFAULT_ROLLING_WINDOW``'s 90), rolling-z-scored against its own trailing
  history, then sign-flipped so a vol spike reads sell/de-risk-favorable.
  Tracking return *magnitude* means it decays back toward 0 once swings shrink,
  instead of staying pinned negative for as long as price sits below a recent
  high, so it stops fighting a slower indicator's "cheap, buy" read once a
  crash has bottomed.
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
    agreement_scaled_blend,
    mtf_rsi_z,
    price_oscillator_z_vectors,
    sma_band_z,
    weekly_macd_z,
)

MACRO_INDICATOR_NAMES: tuple[str, ...] = ("m2", "rs_eth", "dxy")
PRICE_OSCILLATOR_NAMES: tuple[str, ...] = ("weekly_rsi", "weekly_macd", "sma_band")
GENERIC_TECHNICAL_NAMES: tuple[str, ...] = PRICE_OSCILLATOR_NAMES
BTC_PLUGIN_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES
EXTRA_INDICATOR_NAMES: tuple[str, ...] = MACRO_INDICATOR_NAMES + PRICE_OSCILLATOR_NAMES
DEFAULT_ROLLING_WINDOW = 90
_MIN_SAMPLES = 20
_SIGMA_FLOOR = 1e-12
# fast_crash_vol's raw realized-vol lookback -- short on purpose, see the module
# docstring. The z-score window stays DEFAULT_ROLLING_WINDOW.
_FAST_CRASH_VOL_WINDOW = 14
_FAST_CRASH_VOL_MIN_SAMPLES = 7
_RS_ETH_CONFLUENCE_SLOW_WEIGHT = 0.5
_RS_ETH_CONFLUENCE_AGREEMENT_BOOST = 0.5
_RS_ETH_CONFLUENCE_DISAGREEMENT_DAMP = 0.5
WEIGHT_PARAM_BY_NAME: dict[str, str] = {
    "valuation": "valuation_weight",
    "m2": "m2_weight",
    "rs_eth": "rs_eth_weight",
    "dxy": "dxy_weight",
    "onchain_mvrv": "onchain_mvrv_weight",
    "onchain_asopr": "onchain_asopr_weight",
    "onchain_puell": "onchain_puell_weight",
    "onchain_rhodl": "onchain_rhodl_weight",
    "onchain_addr_ratio": "onchain_addr_ratio_weight",
    "fear_greed": "fear_greed_weight",
    "weekly_rsi": "weekly_rsi_weight",
    "weekly_macd": "weekly_macd_weight",
    "sma_band": "sma_band_weight",
    "fast_crash_vol": "fast_crash_vol_weight",
}

# User-facing labels. Code ids stay ``valuation``; charts must say "power law".
INDICATOR_DISPLAY_NAMES: dict[str, str] = {
    "valuation": "power law",
    "m2": "M2 liquidity",
    "rs_eth": "BTC/ETH relative strength",
    "dxy": "DXY",
    "onchain_mvrv": "on-chain MVRV",
    "onchain_asopr": "on-chain aSOPR",
    "onchain_puell": "on-chain Puell Multiple",
    "onchain_rhodl": "on-chain RHODL Ratio",
    "onchain_addr_ratio": "on-chain price/active-address ratio",
    "fear_greed": "Fear & Greed Index",
    "weekly_rsi": "weekly RSI",
    "weekly_macd": "weekly log-MACD",
    "sma_band": "SMA band",
    "fast_crash_vol": "fast-crash volatility",
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
    # Research-only families (DIG-1597). Dormant at 0.0 and absent from the
    # published name tuples -- see the module docstring. Each needs an
    # ExtraIndicatorSources pair before it can be enabled at all.
    onchain_mvrv: float = Field(0.0, ge=0.0)
    onchain_asopr: float = Field(0.0, ge=0.0)
    onchain_puell: float = Field(0.0, ge=0.0)
    onchain_rhodl: float = Field(0.0, ge=0.0)
    onchain_addr_ratio: float = Field(0.0, ge=0.0)
    fear_greed: float = Field(0.0, ge=0.0)
    weekly_rsi: float = Field(0.0, ge=0.0)
    weekly_macd: float = Field(0.0, ge=0.0)
    sma_band: float = Field(0.0, ge=0.0)
    # Fast crash-detection vote. Unlike the six above this one reads only BTC
    # close, so it has no source pair -- build_extra_indicators materializes it
    # from ``btc_price`` alone.
    fast_crash_vol: float = Field(0.0, ge=0.0)

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
            ("onchain_mvrv", self.onchain_mvrv),
            ("onchain_asopr", self.onchain_asopr),
            ("onchain_puell", self.onchain_puell),
            ("onchain_rhodl", self.onchain_rhodl),
            ("onchain_addr_ratio", self.onchain_addr_ratio),
            ("fear_greed", self.fear_greed),
            ("weekly_rsi", self.weekly_rsi),
            ("weekly_macd", self.weekly_macd),
            ("sma_band", self.sma_band),
            ("fast_crash_vol", self.fast_crash_vol),
        )

    def enabled_extras(self) -> dict[str, float]:
        return {name: weight for name, weight in self.extra_items() if weight > 0.0}

    def normalized(self) -> SdcaCompositeWeights:
        payload = self.model_dump()
        total = sum(payload.values())
        return SdcaCompositeWeights(**{name: value / total for name, value in payload.items()})


class ExtraIndicatorSources(BaseModel):
    """Optional aligned series. Missing sources are fine while the weight is 0.

    The research-only families each need a ``*_dates`` / ``*_values`` pair
    (``fast_crash_vol`` needs none -- it is derived from ``btc_price``).
    """

    model_config = ConfigDict(frozen=True, strict=True, arbitrary_types_allowed=True)

    m2_dates: pl.Series | None = None
    m2_values: pl.Series | None = None
    eth_dates: pl.Series | None = None
    eth_close: pl.Series | None = None
    dxy_dates: pl.Series | None = None
    dxy_values: pl.Series | None = None
    onchain_mvrv_dates: pl.Series | None = None
    onchain_mvrv_values: pl.Series | None = None
    onchain_asopr_dates: pl.Series | None = None
    onchain_asopr_values: pl.Series | None = None
    onchain_puell_dates: pl.Series | None = None
    onchain_puell_values: pl.Series | None = None
    onchain_rhodl_dates: pl.Series | None = None
    onchain_rhodl_values: pl.Series | None = None
    onchain_addr_ratio_dates: pl.Series | None = None
    onchain_addr_ratio_values: pl.Series | None = None
    fear_greed_dates: pl.Series | None = None
    fear_greed_values: pl.Series | None = None


def composite_weights_from_params(params: Mapping[str, float | int | str]) -> SdcaCompositeWeights:
    """Read ``*_weight`` keys used by ``strategy_specs`` / walk-forward."""
    return SdcaCompositeWeights(
        valuation=float(params.get("valuation_weight", 1.0)),
        m2=float(params.get("m2_weight", 0.0)),
        rs_eth=float(params.get("rs_eth_weight", 0.0)),
        dxy=float(params.get("dxy_weight", 0.0)),
        onchain_mvrv=float(params.get("onchain_mvrv_weight", 0.0)),
        onchain_asopr=float(params.get("onchain_asopr_weight", 0.0)),
        onchain_puell=float(params.get("onchain_puell_weight", 0.0)),
        onchain_rhodl=float(params.get("onchain_rhodl_weight", 0.0)),
        onchain_addr_ratio=float(params.get("onchain_addr_ratio_weight", 0.0)),
        fear_greed=float(params.get("fear_greed_weight", 0.0)),
        weekly_rsi=float(params.get("weekly_rsi_weight", 0.0)),
        weekly_macd=float(params.get("weekly_macd_weight", 0.0)),
        sma_band=float(params.get("sma_band_weight", 0.0)),
        fast_crash_vol=float(params.get("fast_crash_vol_weight", 0.0)),
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
        onchain_mvrv=float(payload.get("onchain_mvrv", 0.0)),
        onchain_asopr=float(payload.get("onchain_asopr", 0.0)),
        onchain_puell=float(payload.get("onchain_puell", 0.0)),
        onchain_rhodl=float(payload.get("onchain_rhodl", 0.0)),
        onchain_addr_ratio=float(payload.get("onchain_addr_ratio", 0.0)),
        fear_greed=float(payload.get("fear_greed", 0.0)),
        weekly_rsi=float(payload.get("weekly_rsi", 0.0)),
        weekly_macd=float(payload.get("weekly_macd", 0.0)),
        sma_band=float(payload.get("sma_band", 0.0)),
        fast_crash_vol=float(payload.get("fast_crash_vol", 0.0)),
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
    mu = values.rolling_mean(window_size=window, min_samples=1)
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


def _log_ratio_sign_flipped_z(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    window: int,
    min_samples: int,
    name: str,
) -> pl.Series:
    """Shared core for the Bitview/BRK on-chain ratio indicators (MVRV,
    aSOPR, Puell Multiple, RHODL Ratio). See the module docstring.

    Log-transformed first since each is a strictly-positive, right-skewed
    multiplicative ratio (a bull-market spike would otherwise dominate a
    level-based rolling std), then sign-flipped like ``dxy_z``: an elevated
    ratio (overheated/euphoric) is sell-favorable (−z) and a depressed one
    (capitulation) is buy-favorable (+z).

    A handful of pre-history warmup days report ``0.0`` (not enough chain
    history yet to compute the ratio). Those are nulled *before* the log so
    ``align_to_dates``'s forward-fill treats them as an ordinary coverage gap
    instead of producing ``-inf``.
    """
    frame = pl.DataFrame({"value": src_values})
    positive_values = frame.select(
        pl.when(pl.col("value") > 0).then(pl.col("value")).otherwise(None)
    )["value"]
    aligned = align_to_dates(dates, src_dates, positive_values, forward_fill=True)
    log_values = aligned.log()
    return (-causal_rolling_z(log_values, window=window, min_samples=min_samples)).alias(name)


def onchain_mvrv_z(
    dates: pl.Series,
    mvrv_dates: pl.Series,
    mvrv_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Bitview/BRK MVRV — see ``_log_ratio_sign_flipped_z``."""
    return _log_ratio_sign_flipped_z(
        dates,
        mvrv_dates,
        mvrv_values,
        window=window,
        min_samples=min_samples,
        name="onchain_mvrv",
    )


def onchain_asopr_z(
    dates: pl.Series,
    asopr_dates: pl.Series,
    asopr_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Bitview/BRK adjusted SOPR (24h) — see ``_log_ratio_sign_flipped_z``."""
    return _log_ratio_sign_flipped_z(
        dates,
        asopr_dates,
        asopr_values,
        window=window,
        min_samples=min_samples,
        name="onchain_asopr",
    )


def onchain_puell_z(
    dates: pl.Series,
    puell_dates: pl.Series,
    puell_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Bitview/BRK Puell Multiple — see ``_log_ratio_sign_flipped_z``."""
    return _log_ratio_sign_flipped_z(
        dates,
        puell_dates,
        puell_values,
        window=window,
        min_samples=min_samples,
        name="onchain_puell",
    )


def onchain_rhodl_z(
    dates: pl.Series,
    rhodl_dates: pl.Series,
    rhodl_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Bitview/BRK RHODL Ratio — see ``_log_ratio_sign_flipped_z``."""
    return _log_ratio_sign_flipped_z(
        dates,
        rhodl_dates,
        rhodl_values,
        window=window,
        min_samples=min_samples,
        name="onchain_rhodl",
    )


def onchain_addr_ratio_z(
    dates: pl.Series,
    btc_price: pl.Series,
    addr_dates: pl.Series,
    addr_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Price-per-active-address ratio (NVT/Metcalfe-style) — see ``_log_ratio_sign_flipped_z``.

    Unlike the four series above, this ratio is not fetched pre-derived:
    ``addr_values`` is CoinMetrics' raw daily active-address count
    (``AdrActCnt``), so the ratio is computed here. Pre-adoption days report 0
    addresses; those are nulled *before* the divide (not just the resulting
    ratio) so a zero denominator cannot produce ``inf`` before the core ever
    sees it.
    """
    addr_aligned = align_to_dates(dates, addr_dates, addr_values, forward_fill=True)
    positive_addr = pl.DataFrame({"value": addr_aligned}).select(
        pl.when(pl.col("value") > 0).then(pl.col("value")).otherwise(None)
    )["value"]
    ratio = (btc_price / positive_addr).alias("value")
    return _log_ratio_sign_flipped_z(
        dates, dates, ratio, window=window, min_samples=min_samples, name="onchain_addr_ratio"
    )


def fear_greed_z(
    dates: pl.Series,
    fear_greed_dates: pl.Series,
    fear_greed_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """alternative.me Fear & Greed (0-100), rolling-z, sign-flipped.

    Same shape as ``dxy_z`` — a *level* series, so no log transform — but read
    contrarian: elevated ("greed") is sell-favorable (−z), depressed ("fear")
    is buy-favorable (+z). The source publishes weekly, so the forward-fill in
    ``align_to_dates`` matters here.
    """
    aligned = align_to_dates(dates, fear_greed_dates, fear_greed_values, forward_fill=True)
    return (-causal_rolling_z(aligned, window=window, min_samples=min_samples)).alias("fear_greed")


def fast_crash_vol_z(
    dates: pl.Series,
    btc_price: pl.Series,
    *,
    window: int = _FAST_CRASH_VOL_WINDOW,
    min_samples: int = _FAST_CRASH_VOL_MIN_SAMPLES,
    z_window: int = DEFAULT_ROLLING_WINDOW,
    z_min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Short-window realized volatility of daily log returns, sign-flipped z.

    See the module docstring. ``window``/``min_samples`` control the raw
    realized-vol lookback — deliberately short (14d vs. the 90d default), since
    the fast reaction to a crash *is* the signal. The resulting series is then
    rolling-z-scored against its own trailing history (``causal_rolling_z``, as
    everywhere else here) and sign-flipped so an unusual vol spike reads
    sell/de-risk-favorable.
    """
    if dates.len() != btc_price.len():
        raise ValueError("dates and btc_price must be the same length")
    log_ret = btc_price.log() - btc_price.shift(1).log()
    realized_vol = log_ret.rolling_std(window_size=window, min_samples=min_samples)
    z = causal_rolling_z(realized_vol, window=z_window, min_samples=z_min_samples)
    return (-z).alias("fast_crash_vol")


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

    The same agreement-scaled blend as the price-oscillator confluences
    (``rsi_confluence_z`` / ``macd_confluence_z`` / ``sma_band_confluence_z`` in
    ``price_oscillators.py``). As in ``sma_band_confluence_z``, both legs share
    one formula — ``rs_eth_z``'s rolling z of the BTC/ETH log ratio — so the
    timeframe separation is window length, not bar aggregation. BTC/ETH rotation
    has both a slow multi-quarter cycle and faster swings, so a two-timeframe
    read fits the ratio the same way it fits a price band.

    Not wired into ``build_extra_indicators`` in this leaf: ``rs_eth`` still
    resolves to plain ``rs_eth_z`` there, and switching it over is a measured
    behaviour change tracked as its own leaf.
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
    if "onchain_mvrv" in enabled:
        mvrv_dates = _require_pair(
            sources.onchain_mvrv_dates, sources.onchain_mvrv_values, "onchain_mvrv"
        )
        extras.append(
            IndicatorWeight(
                name="onchain_mvrv",
                z=onchain_mvrv_z(
                    dates,
                    mvrv_dates,
                    sources.onchain_mvrv_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["onchain_mvrv"],
            )
        )
    if "onchain_asopr" in enabled:
        asopr_dates = _require_pair(
            sources.onchain_asopr_dates, sources.onchain_asopr_values, "onchain_asopr"
        )
        extras.append(
            IndicatorWeight(
                name="onchain_asopr",
                z=onchain_asopr_z(
                    dates,
                    asopr_dates,
                    sources.onchain_asopr_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["onchain_asopr"],
            )
        )
    if "onchain_puell" in enabled:
        puell_dates = _require_pair(
            sources.onchain_puell_dates, sources.onchain_puell_values, "onchain_puell"
        )
        extras.append(
            IndicatorWeight(
                name="onchain_puell",
                z=onchain_puell_z(
                    dates,
                    puell_dates,
                    sources.onchain_puell_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["onchain_puell"],
            )
        )
    if "onchain_rhodl" in enabled:
        rhodl_dates = _require_pair(
            sources.onchain_rhodl_dates, sources.onchain_rhodl_values, "onchain_rhodl"
        )
        extras.append(
            IndicatorWeight(
                name="onchain_rhodl",
                z=onchain_rhodl_z(
                    dates,
                    rhodl_dates,
                    sources.onchain_rhodl_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["onchain_rhodl"],
            )
        )
    if "onchain_addr_ratio" in enabled:
        addr_dates = _require_pair(
            sources.onchain_addr_ratio_dates,
            sources.onchain_addr_ratio_values,
            "onchain_addr_ratio",
        )
        extras.append(
            IndicatorWeight(
                name="onchain_addr_ratio",
                z=onchain_addr_ratio_z(
                    dates,
                    btc_price,
                    addr_dates,
                    sources.onchain_addr_ratio_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["onchain_addr_ratio"],
            )
        )
    if "fear_greed" in enabled:
        fg_dates = _require_pair(sources.fear_greed_dates, sources.fear_greed_values, "fear_greed")
        extras.append(
            IndicatorWeight(
                name="fear_greed",
                z=fear_greed_z(
                    dates,
                    fg_dates,
                    sources.fear_greed_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["fear_greed"],
            )
        )
    if "weekly_rsi" in enabled:
        extras.append(
            IndicatorWeight(
                name="weekly_rsi",
                z=mtf_rsi_z(dates, btc_price, length=spec.rsi_length),
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
    if "fast_crash_vol" in enabled:
        # No source pair: derived from btc_price alone.
        extras.append(
            IndicatorWeight(
                name="fast_crash_vol",
                z=fast_crash_vol_z(dates, btc_price),
                weight=enabled["fast_crash_vol"],
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
    onchain_mvrv_path: Path | str | None = None,
    onchain_asopr_path: Path | str | None = None,
    onchain_puell_path: Path | str | None = None,
    onchain_rhodl_path: Path | str | None = None,
    fear_greed_path: Path | str | None = None,
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
    onchain_mvrv_dates = onchain_mvrv_values = None
    if onchain_mvrv_path is not None:
        onchain_mvrv_dates, onchain_mvrv_values = load_date_value_frame(onchain_mvrv_path)
    onchain_asopr_dates = onchain_asopr_values = None
    if onchain_asopr_path is not None:
        onchain_asopr_dates, onchain_asopr_values = load_date_value_frame(onchain_asopr_path)
    onchain_puell_dates = onchain_puell_values = None
    if onchain_puell_path is not None:
        onchain_puell_dates, onchain_puell_values = load_date_value_frame(onchain_puell_path)
    onchain_rhodl_dates = onchain_rhodl_values = None
    if onchain_rhodl_path is not None:
        onchain_rhodl_dates, onchain_rhodl_values = load_date_value_frame(onchain_rhodl_path)
    fear_greed_dates = fear_greed_values = None
    if fear_greed_path is not None:
        fear_greed_dates, fear_greed_values = load_date_value_frame(fear_greed_path)
    return ExtraIndicatorSources(
        m2_dates=m2_dates,
        m2_values=m2_values,
        eth_dates=eth_dates,
        eth_close=eth_close,
        dxy_dates=dxy_dates,
        dxy_values=dxy_values,
        onchain_mvrv_dates=onchain_mvrv_dates,
        onchain_mvrv_values=onchain_mvrv_values,
        onchain_asopr_dates=onchain_asopr_dates,
        onchain_asopr_values=onchain_asopr_values,
        onchain_puell_dates=onchain_puell_dates,
        onchain_puell_values=onchain_puell_values,
        onchain_rhodl_dates=onchain_rhodl_dates,
        onchain_rhodl_values=onchain_rhodl_values,
        onchain_addr_ratio_dates=None,
        onchain_addr_ratio_values=None,
        fear_greed_dates=fear_greed_dates,
        fear_greed_values=fear_greed_values,
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
    "fast_crash_vol_z",
    "fear_greed_z",
    "indicator_display_name",
    "load_date_value_frame",
    "m2_liquidity_z",
    "missing_extra_names",
    "onchain_addr_ratio_z",
    "onchain_asopr_z",
    "onchain_mvrv_z",
    "onchain_puell_z",
    "onchain_rhodl_z",
    "parse_indicator_weights_json",
    "rs_eth_confluence_z",
    "rs_eth_z",
    "sources_from_optional_paths",
]
