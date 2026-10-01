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
- on-chain MVRV/SOPR — provider ready (#1086); not published votes yet
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
    mtf_rsi_z,
    price_oscillator_z_vectors,
    sma_band_z,
    weekly_macd_z,
)

MACRO_INDICATOR_NAMES: tuple[str, ...] = (
    "m2",
    "rs_eth",
    "dxy",
    "uup",
    "gvz",
    "walcl",
    "hy_oas",
    "ig_oas",
    "breakeven_5y",
    "nfci",
    "gdx_gld",
    "gld_slv",
    "real_rate",
)
GOLD_MACRO_NAMES: tuple[str, ...] = (
    "gvz",
    "walcl",
    "hy_oas",
    "ig_oas",
    "breakeven_5y",
    "nfci",
    "gdx_gld",
    "gld_slv",
    "uup",
    "real_rate",
)
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
    "uup": "uup_weight",
    "gvz": "gvz_weight",
    "walcl": "walcl_weight",
    "hy_oas": "hy_oas_weight",
    "ig_oas": "ig_oas_weight",
    "breakeven_5y": "breakeven_5y_weight",
    "nfci": "nfci_weight",
    "gdx_gld": "gdx_gld_weight",
    "gld_slv": "gld_slv_weight",
    "real_rate": "real_rate_weight",
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
    "uup": "dollar proxy (UUP)",
    "gvz": "gold volatility (GVZ)",
    "walcl": "Fed balance sheet",
    "hy_oas": "HY credit spread",
    "ig_oas": "IG credit spread",
    "breakeven_5y": "5Y breakeven",
    "nfci": "financial conditions (NFCI)",
    "gdx_gld": "GDX/GLD participation",
    "gld_slv": "gold/silver ratio",
    "real_rate": "real yield (DFII10)",
    "weekly_rsi": "weekly RSI",
    "weekly_macd": "weekly log-MACD",
    "sma_band": "SMA band",
}


_VALUATION_DISPLAY_BY_MODEL: dict[str, str] = {
    "btc_power_law": "power law",
    "generic_valuation": "valuation trend",
    "rolling_z": "mean reversion",
}


def indicator_display_name(name: str, *, model: str | None = None) -> str:
    """Chart/UI label for an indicator code id. `model` selects the valuation-leg label; default preserves BTC wording."""
    if name == "valuation" and model in _VALUATION_DISPLAY_BY_MODEL:
        return _VALUATION_DISPLAY_BY_MODEL[model]
    return INDICATOR_DISPLAY_NAMES.get(name, name.replace("_", " "))


class SdcaCompositeWeights(BaseModel):
    """Non-negative weights. Zero means disabled (not in the blend)."""

    model_config = ConfigDict(frozen=True, strict=True)

    valuation: float = Field(1.0, ge=0.0)
    m2: float = Field(0.0, ge=0.0)
    rs_eth: float = Field(0.0, ge=0.0)
    dxy: float = Field(0.0, ge=0.0)
    uup: float = Field(0.0, ge=0.0)
    gvz: float = Field(0.0, ge=0.0)
    walcl: float = Field(0.0, ge=0.0)
    hy_oas: float = Field(0.0, ge=0.0)
    ig_oas: float = Field(0.0, ge=0.0)
    breakeven_5y: float = Field(0.0, ge=0.0)
    nfci: float = Field(0.0, ge=0.0)
    gdx_gld: float = Field(0.0, ge=0.0)
    gld_slv: float = Field(0.0, ge=0.0)
    real_rate: float = Field(0.0, ge=0.0)
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
            ("uup", self.uup),
            ("gvz", self.gvz),
            ("walcl", self.walcl),
            ("hy_oas", self.hy_oas),
            ("ig_oas", self.ig_oas),
            ("breakeven_5y", self.breakeven_5y),
            ("nfci", self.nfci),
            ("gdx_gld", self.gdx_gld),
            ("gld_slv", self.gld_slv),
            ("real_rate", self.real_rate),
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
    uup_dates: pl.Series | None = None
    uup_close: pl.Series | None = None
    gvz_dates: pl.Series | None = None
    gvz_values: pl.Series | None = None
    walcl_dates: pl.Series | None = None
    walcl_values: pl.Series | None = None
    hy_oas_dates: pl.Series | None = None
    hy_oas_values: pl.Series | None = None
    ig_oas_dates: pl.Series | None = None
    ig_oas_values: pl.Series | None = None
    breakeven_5y_dates: pl.Series | None = None
    breakeven_5y_values: pl.Series | None = None
    nfci_dates: pl.Series | None = None
    nfci_values: pl.Series | None = None
    gdx_dates: pl.Series | None = None
    gdx_close: pl.Series | None = None
    slv_dates: pl.Series | None = None
    slv_close: pl.Series | None = None
    real_rate_dates: pl.Series | None = None
    real_rate_values: pl.Series | None = None


def composite_weights_from_params(params: Mapping[str, float | int | str]) -> SdcaCompositeWeights:
    """Read ``*_weight`` keys used by ``strategy_specs`` / walk-forward."""
    return SdcaCompositeWeights(
        valuation=float(params.get("valuation_weight", 1.0)),
        m2=float(params.get("m2_weight", 0.0)),
        rs_eth=float(params.get("rs_eth_weight", 0.0)),
        dxy=float(params.get("dxy_weight", 0.0)),
        uup=float(params.get("uup_weight", 0.0)),
        gvz=float(params.get("gvz_weight", 0.0)),
        walcl=float(params.get("walcl_weight", 0.0)),
        hy_oas=float(params.get("hy_oas_weight", 0.0)),
        ig_oas=float(params.get("ig_oas_weight", 0.0)),
        breakeven_5y=float(params.get("breakeven_5y_weight", 0.0)),
        nfci=float(params.get("nfci_weight", 0.0)),
        gdx_gld=float(params.get("gdx_gld_weight", 0.0)),
        gld_slv=float(params.get("gld_slv_weight", 0.0)),
        real_rate=float(params.get("real_rate_weight", 0.0)),
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
        uup=float(payload.get("uup", 0.0)),
        gvz=float(payload.get("gvz", 0.0)),
        walcl=float(payload.get("walcl", 0.0)),
        hy_oas=float(payload.get("hy_oas", 0.0)),
        ig_oas=float(payload.get("ig_oas", 0.0)),
        breakeven_5y=float(payload.get("breakeven_5y", 0.0)),
        nfci=float(payload.get("nfci", 0.0)),
        gdx_gld=float(payload.get("gdx_gld", 0.0)),
        gld_slv=float(payload.get("gld_slv", 0.0)),
        real_rate=float(payload.get("real_rate", 0.0)),
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


def uup_z(
    dates: pl.Series,
    uup_dates: pl.Series,
    uup_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """UUP dollar-proxy rolling-z, sign-flipped like DXY: strong dollar → −z.

    UUP↔DXY correlate 0.86/0.88 (levels/63d changes, 4857 joint days) — this
    leg is a refreshability swap for the unstageable DTWEXBGS file, not a new
    independent vote. Parity with dxy, not outperformance, is success.
    """
    aligned = align_to_dates(dates, uup_dates, uup_values, forward_fill=True)
    return (-causal_rolling_z(aligned, window=window, min_samples=min_samples)).alias("uup")


def real_rate_z(
    dates: pl.Series,
    dfii10_dates: pl.Series,
    dfii10_values: pl.Series,
    *,
    window: int = 1260,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """DFII10 real-yield level rolling-z, NOT sign-flipped (washout semantics).

    High real yields = fear washed out = cheap (+z, buy); cratered real yields
    = crowded fear-bid = rich (−z, sell). The uup/dxy headwind flip is
    deliberately absent: this leg buys washes for a long-biased system.
    Window 1260d matches the v5 secular rationale (half-swing).
    """
    aligned = align_to_dates(dates, dfii10_dates, dfii10_values, forward_fill=True)
    return causal_rolling_z(aligned, window=window, min_samples=min_samples).alias("real_rate")


def _macro_level_z(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    name: str,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Level rolling-z for fear-bid macro legs. Rising series → +z (buy gold)."""
    aligned = align_to_dates(dates, src_dates, src_values, forward_fill=True)
    return causal_rolling_z(aligned, window=window, min_samples=min_samples).alias(name)


def gvz_z(
    dates: pl.Series,
    gvz_dates: pl.Series,
    gvz_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Gold implied-vol level z. Spiking GVZ = stress = gold bid → +z (no flip)."""
    return _macro_level_z(
        dates, gvz_dates, gvz_values, "gvz", window=window, min_samples=min_samples
    )


def walcl_liquidity_z(
    dates: pl.Series,
    walcl_dates: pl.Series,
    walcl_values: pl.Series,
    *,
    roc_days: int = 365,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """YoY Fed-balance-sheet growth, rolling-z. Expanding sheet → +z (buy).

    Mirrors ``m2_liquidity_z``: WALCL trends monotonically, so a level-z is
    meaningless and growth is the vote.
    """
    aligned = align_to_dates(dates, walcl_dates, walcl_values, forward_fill=True)
    roc = aligned / aligned.shift(roc_days) - 1.0
    return causal_rolling_z(roc, window=window, min_samples=min_samples).alias("walcl")


def hy_oas_z(
    dates: pl.Series,
    hy_dates: pl.Series,
    hy_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """HY spread level z. Widening = stress = gold bid → +z (no flip)."""
    return _macro_level_z(
        dates, hy_dates, hy_values, "hy_oas", window=window, min_samples=min_samples
    )


def ig_oas_z(
    dates: pl.Series,
    ig_dates: pl.Series,
    ig_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """IG spread level z. Same fear-bid sign convention as ``hy_oas_z``."""
    return _macro_level_z(
        dates, ig_dates, ig_values, "ig_oas", window=window, min_samples=min_samples
    )


def breakeven_5y_z(
    dates: pl.Series,
    be_dates: pl.Series,
    be_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """5Y breakeven level z. Rising inflation compensation → +z (no flip)."""
    return _macro_level_z(
        dates, be_dates, be_values, "breakeven_5y", window=window, min_samples=min_samples
    )


def nfci_z(
    dates: pl.Series,
    nfci_dates: pl.Series,
    nfci_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """NFCI level z. Positive (tight) conditions = stress bid → +z (no flip)."""
    return _macro_level_z(
        dates, nfci_dates, nfci_values, "nfci", window=window, min_samples=min_samples
    )


def gdx_gld_z(
    dates: pl.Series,
    gld_price: pl.Series,
    gdx_dates: pl.Series,
    gdx_close: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """``log(GDX/GLD)`` rolling-z. Miner participation confirms the bid → +z (no flip)."""
    gdx = align_to_dates(dates, gdx_dates, gdx_close, forward_fill=False)
    ratio = (gdx / gld_price).log()
    return causal_rolling_z(ratio, window=window, min_samples=min_samples).alias("gdx_gld")


def gld_slv_z(
    dates: pl.Series,
    gld_price: pl.Series,
    slv_dates: pl.Series,
    slv_close: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """``log(GLD/SLV)`` rolling-z. Silver weak vs gold = stress → +z (no flip)."""
    slv = align_to_dates(dates, slv_dates, slv_close, forward_fill=False)
    ratio = (gld_price / slv).log()
    return causal_rolling_z(ratio, window=window, min_samples=min_samples).alias("gld_slv")


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
    if "uup" in enabled:
        uup_dates = _require_pair(sources.uup_dates, sources.uup_close, "uup")
        extras.append(
            IndicatorWeight(
                name="uup",
                z=uup_z(
                    dates,
                    uup_dates,
                    sources.uup_close,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["uup"],
            )
        )
    if "gvz" in enabled:
        gvz_dates = _require_pair(sources.gvz_dates, sources.gvz_values, "gvz")
        extras.append(
            IndicatorWeight(
                name="gvz",
                z=gvz_z(
                    dates,
                    gvz_dates,
                    sources.gvz_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["gvz"],
            )
        )
    if "walcl" in enabled:
        walcl_dates = _require_pair(sources.walcl_dates, sources.walcl_values, "walcl")
        extras.append(
            IndicatorWeight(
                name="walcl",
                z=walcl_liquidity_z(
                    dates,
                    walcl_dates,
                    sources.walcl_values,  # type: ignore[arg-type]
                    roc_days=roc_days,
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["walcl"],
            )
        )
    if "hy_oas" in enabled:
        hy_oas_dates = _require_pair(sources.hy_oas_dates, sources.hy_oas_values, "hy_oas")
        extras.append(
            IndicatorWeight(
                name="hy_oas",
                z=hy_oas_z(
                    dates,
                    hy_oas_dates,
                    sources.hy_oas_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["hy_oas"],
            )
        )
    if "ig_oas" in enabled:
        ig_oas_dates = _require_pair(sources.ig_oas_dates, sources.ig_oas_values, "ig_oas")
        extras.append(
            IndicatorWeight(
                name="ig_oas",
                z=ig_oas_z(
                    dates,
                    ig_oas_dates,
                    sources.ig_oas_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["ig_oas"],
            )
        )
    if "breakeven_5y" in enabled:
        be_dates = _require_pair(
            sources.breakeven_5y_dates, sources.breakeven_5y_values, "breakeven_5y"
        )
        extras.append(
            IndicatorWeight(
                name="breakeven_5y",
                z=breakeven_5y_z(
                    dates,
                    be_dates,
                    sources.breakeven_5y_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["breakeven_5y"],
            )
        )
    if "nfci" in enabled:
        nfci_dates = _require_pair(sources.nfci_dates, sources.nfci_values, "nfci")
        extras.append(
            IndicatorWeight(
                name="nfci",
                z=nfci_z(
                    dates,
                    nfci_dates,
                    sources.nfci_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["nfci"],
            )
        )
    if "gdx_gld" in enabled:
        gdx_dates = _require_pair(sources.gdx_dates, sources.gdx_close, "gdx_gld")
        extras.append(
            IndicatorWeight(
                name="gdx_gld",
                z=gdx_gld_z(
                    dates,
                    btc_price,
                    gdx_dates,
                    sources.gdx_close,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["gdx_gld"],
            )
        )
    if "gld_slv" in enabled:
        slv_dates = _require_pair(sources.slv_dates, sources.slv_close, "gld_slv")
        extras.append(
            IndicatorWeight(
                name="gld_slv",
                z=gld_slv_z(
                    dates,
                    btc_price,
                    slv_dates,
                    sources.slv_close,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["gld_slv"],
            )
        )
    if "real_rate" in enabled:
        real_rate_dates = _require_pair(
            sources.real_rate_dates, sources.real_rate_values, "real_rate"
        )
        extras.append(
            IndicatorWeight(
                name="real_rate",
                z=real_rate_z(
                    dates,
                    real_rate_dates,
                    sources.real_rate_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["real_rate"],
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
    "GOLD_MACRO_NAMES",
    "MACRO_INDICATOR_NAMES",
    "PRICE_OSCILLATOR_NAMES",
    "WEIGHT_PARAM_BY_NAME",
    "INDICATOR_DISPLAY_NAMES",
    "ExtraIndicatorSources",
    "SdcaCompositeWeights",
    "align_to_dates",
    "build_extra_indicators",
    "breakeven_5y_z",
    "causal_rolling_z",
    "composite_weights_from_params",
    "dxy_z",
    "uup_z",
    "extra_indicators_for_window",
    "extra_z_vectors",
    "gdx_gld_z",
    "gld_slv_z",
    "gvz_z",
    "hy_oas_z",
    "ig_oas_z",
    "indicator_display_name",
    "load_date_value_frame",
    "m2_liquidity_z",
    "missing_extra_names",
    "nfci_z",
    "parse_indicator_weights_json",
    "real_rate_z",
    "rs_eth_z",
    "sources_from_optional_paths",
    "walcl_liquidity_z",
]
