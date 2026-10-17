"""Per-asset SDCA profile: rails selector, oscillator windows, cycle pins.

The reusable core is the same for every asset: generic technicals from that
asset's OHLCV → composite risk → Stage A weights on that asset's cycle
windows → Stage B curve → regularize. Asset-specific series (BTC on-chain
SOPR/MVRV, gold GVZ / GLD-SLV / real rates, later equity put/call) are plugins
on the extra-indicators allowlist, not this shared path.

Profiles are registered by name (``register_profile`` / ``get_profile``), so a
new asset is data rather than a code edit: declare its cycle pins in
``cycle_windows``, then register an ``SdcaAssetProfile``. The allowlist says
what an asset MAY search; the calibrated subset it DOES use lives in the
``settings.json`` presets, not here.

Do not add a published ``settings.json`` entry until a calibrated backtest
for that asset looks comfortable. ``eth_research_v1()`` is research-only.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.lab.cycle_windows import SdcaCycleWindows
from digiquant.strategies.lab.indicator_catalog import (
    BTC_PLUGIN_INDICATOR_NAMES,
    EXTRA_INDICATOR_NAMES,
    GENERIC_TECHNICAL_NAMES,
    MACRO_INDICATOR_NAMES,
    SdcaCompositeWeights,
)
from digiquant.strategies.lab.price_oscillators import (
    SdcaOscillatorSpec,
    price_oscillator_z_vectors,
)
from digiquant.strategies.lab.providers import SdcaRiskModelName

# Every extra an allowlist may name, across all assets. Built from the catalogue
# itself so a new plugin family is legal without editing this module.
_KNOWN_EXTRAS: frozenset[str] = frozenset(EXTRA_INDICATOR_NAMES)


class SdcaAssetProfile(BaseModel):
    """One asset's rails, oscillator calibration, cycle pins, and extra allowlist."""

    model_config = ConfigDict(frozen=True, strict=True)

    symbol: str = Field(min_length=1)
    risk_model: SdcaRiskModelName
    oscillators: SdcaOscillatorSpec = Field(default_factory=SdcaOscillatorSpec)
    cycle_windows: SdcaCycleWindows
    extra_indicators: tuple[str, ...] = GENERIC_TECHNICAL_NAMES
    signal_delay_days: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _known_extras(self) -> SdcaAssetProfile:
        unknown = [name for name in self.extra_indicators if name not in _KNOWN_EXTRAS]
        if unknown:
            raise ValueError(f"unknown extra_indicators: {unknown}")
        return self

    def generic_technicals(self) -> tuple[str, ...]:
        return tuple(n for n in self.extra_indicators if n in GENERIC_TECHNICAL_NAMES)

    def plugin_extras(self) -> tuple[str, ...]:
        return tuple(n for n in self.extra_indicators if n in MACRO_INDICATOR_NAMES)

    def ensure_extras_allowed(self, weights: SdcaCompositeWeights) -> None:
        """Raise if an enabled extra is not on this asset's allowlist."""
        forbidden = [name for name in weights.enabled_extras() if name not in self.extra_indicators]
        if forbidden:
            raise ValueError(f"{forbidden} not in extra_indicators allowlist for {self.symbol}")

    @classmethod
    def btc_v1(cls) -> SdcaAssetProfile:
        """Checked-in BTC profile: power-law rails, weekly RSI(14)/90d SMA-band."""
        return cls(
            symbol="BTC-USD",
            risk_model="btc_power_law",
            oscillators=SdcaOscillatorSpec(),
            cycle_windows=SdcaCycleWindows.btc_v1(),
            extra_indicators=GENERIC_TECHNICAL_NAMES + BTC_PLUGIN_INDICATOR_NAMES,
            signal_delay_days=0,
        )

    @classmethod
    def eth_research_v1(cls) -> SdcaAssetProfile:
        """Research ETH profile. Not published. No MVRV, no M2, no rs_eth.

        Uses ``generic_valuation`` + weekly RSI/SMA-band. Cycle pins are
        research extrema, not a comfortable calibrated backtest. Add ETH
        OHLCV to ``history_cache`` then run Stage A → B → regularize before
        considering ``settings.json``.
        """
        return cls(
            symbol="ETH-USD",
            risk_model="generic_valuation",
            oscillators=SdcaOscillatorSpec(),
            cycle_windows=SdcaCycleWindows.eth_research_v1(),
            extra_indicators=GENERIC_TECHNICAL_NAMES,
            signal_delay_days=0,
        )

    @classmethod
    def gold_v1(cls) -> SdcaAssetProfile:
        """Checked-in gold profile: rolling-z rails, gold macro family + technicals.

        ``rolling_z`` (90d) is what the live ``gold_sdca`` preset in
        ``settings.json`` (``gold_reselect``) selects. Cycle pins come from
        ``SdcaCycleWindows.gold_v1()``. The allowlist is the full extra
        catalogue, because the calibrated subset actually used (valuation, m2,
        uup, oscillators) belongs to the preset — a macro leg can be
        re-weighted there without editing this module.
        """
        return cls(
            symbol="GLD-USD",
            risk_model="rolling_z",
            oscillators=SdcaOscillatorSpec(),
            cycle_windows=SdcaCycleWindows.gold_v1(),
            extra_indicators=GENERIC_TECHNICAL_NAMES + MACRO_INDICATOR_NAMES,
            signal_delay_days=0,
        )


def daily_closes_from_ohlcv(frame: pl.DataFrame) -> tuple[pl.Series, pl.Series]:
    """Date/close series from a history-cache OHLCV frame (any ticker)."""
    if "timestamp" not in frame.columns or "close" not in frame.columns:
        raise ValueError(f"OHLCV frame needs timestamp and close columns, got {frame.columns}")
    dates = frame["timestamp"]
    if dates.dtype != pl.Date:
        if isinstance(dates.dtype, pl.Datetime):
            dates = dates.cast(pl.Date)
        else:
            dates = dates.str.to_datetime(strict=False).cast(pl.Date)
    cleaned = (
        pl.DataFrame({"date": dates, "close": frame["close"].cast(pl.Float64)})
        .drop_nulls()
        .unique(subset=["date"], keep="last")
        .sort("date")
    )
    if cleaned.is_empty():
        raise ValueError("OHLCV frame has no dated close rows")
    return cleaned["date"], cleaned["close"]


def daily_closes_from_cache(ticker: str, cache_dir: Path | str) -> tuple[pl.Series, pl.Series]:
    """Load one ticker from ``history_cache`` and return dated closes."""
    frame = load_cached(ticker, cache_dir)
    if frame is None or frame.is_empty():
        raise ValueError(f"no cached price history for {ticker!r}")
    return daily_closes_from_ohlcv(frame)


def union_date_range(*date_series: pl.Series) -> tuple[date, date]:
    """Shared x-axis span across assets — union, not an inner join.

    Overlay plots must not clip BTC (Coinbase 2015-07-20) to ETH's shorter
    overlap. Each series keeps its own rows; only the axis limits are shared.
    """
    if not date_series:
        raise ValueError("union_date_range requires at least one date series")
    starts: list[date] = []
    ends: list[date] = []
    for series in date_series:
        if series.len() == 0:
            raise ValueError("union_date_range requires non-empty date series")
        starts.append(series[0])
        ends.append(series[-1])
    return min(starts), max(ends)


def technicals_from_ohlcv(
    dates: pl.Series,
    close: pl.Series,
    oscillators: SdcaOscillatorSpec | None = None,
) -> dict[str, list[float | None]]:
    """Generic RSI/MACD/SMA-band z from any asset's daily close (causal ISO-week)."""
    return price_oscillator_z_vectors(dates, close, oscillators=oscillators)


def stage_a_search_names(profile: SdcaAssetProfile) -> tuple[str, ...]:
    """Stage A searches every extra on the profile allowlist (plugins included)."""
    names = tuple(profile.extra_indicators)
    return names if names else GENERIC_TECHNICAL_NAMES


ProfileFactory = Callable[[], SdcaAssetProfile]

_PROFILES: dict[str, ProfileFactory] = {}


def register_profile(name: str, factory: ProfileFactory) -> None:
    """Register an asset profile factory under ``name`` (later calls overwrite)."""
    _PROFILES[name] = factory


def get_profile(name: str) -> SdcaAssetProfile:
    """Build the registered profile ``name`` (e.g. ``"btc"``, ``"gold"``)."""
    factory = _PROFILES.get(name)
    if factory is None:
        raise ValueError(f"Unknown asset profile: {name}. Registered: {list(_PROFILES.keys())}.")
    return factory()


def list_profiles() -> list[dict[str, Any]]:
    """List registered profiles with symbol, risk model and cycle-window count."""
    rows: list[dict[str, Any]] = []
    for name, factory in _PROFILES.items():
        profile = factory()
        rows.append(
            {
                "name": name,
                "symbol": profile.symbol,
                "risk_model": profile.risk_model,
                "cycle_windows": len(profile.cycle_windows.windows),
                "extras": len(profile.extra_indicators),
            }
        )
    return rows


register_profile("btc", SdcaAssetProfile.btc_v1)
register_profile("eth", SdcaAssetProfile.eth_research_v1)
register_profile("gold", SdcaAssetProfile.gold_v1)


__all__ = [
    "BTC_PLUGIN_INDICATOR_NAMES",
    "EXTRA_INDICATOR_NAMES",
    "GENERIC_TECHNICAL_NAMES",
    "MACRO_INDICATOR_NAMES",
    "ProfileFactory",
    "SdcaAssetProfile",
    "daily_closes_from_cache",
    "daily_closes_from_ohlcv",
    "get_profile",
    "list_profiles",
    "register_profile",
    "stage_a_search_names",
    "technicals_from_ohlcv",
    "union_date_range",
]
