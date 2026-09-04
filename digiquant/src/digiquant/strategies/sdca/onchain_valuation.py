"""On-chain-enhanced SDCA valuation provider (#1086).

Composes Bitview/BRK ``day1`` series into causal z-scores in ``[-3, 3]``
(cheap = +) that plug into ``compute_composite_risk`` as ``IndicatorWeight``
votes. Local **MVRV-Z** is computed from ``mvrv`` (Bitview has no ``mvrv_z``
series). Companion oscillators: ``asopr_24h``, ``puell_multiple``,
``rhodl_ratio``. NUPL is refused upstream (monotone of MVRV).

**Not published composite votes yet.** The composite null-rule would halt
SDCA on a Bitview gap if these were enabled in ``settings.json``. This
module emits consumable z-series for research / Stage A; keep published
weights at 0 until a skip-missing path exists.

**Coverage / fallback.** BRK on-chain is BTC-rich. When coverage is thin or
the cache is empty, ``resolve_sdca_valuation_tier`` falls back to the basic
``RollingZRiskModel`` (std-dev / %-from-MA style rails).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.onchain.bitview import DEFAULT_SERIES, FORBIDDEN_SERIES
from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.indicator_catalog import align_to_dates
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import DEFAULT_ROLLING_WINDOW, RollingZRiskModel

# Bitview ids ingested for v1 (research note). MVRV-Z is derived, not fetched.
ONCHAIN_SERIES_IDS: tuple[str, ...] = DEFAULT_SERIES
# Indicator names emitted to composite-risk (mvrv → mvrv_z).
ONCHAIN_INDICATOR_NAMES: tuple[str, ...] = (
    "mvrv_z",
    "asopr",
    "puell",
    "rhodl",
)
_SERIES_TO_INDICATOR: dict[str, str] = {
    "mvrv": "mvrv_z",
    "asopr_24h": "asopr",
    "puell_multiple": "puell",
    "rhodl_ratio": "rhodl",
}
_MIN_SAMPLES = 30
_SIGMA_FLOOR = 1e-12
# Expanding window = full history (causal). Cap at a large int for Polars.
_EXPANDING_CAP = 100_000

# BTC-only catalog today. ETH/SOL sparse → basic tier.
_COVERAGE: dict[str, Literal["rich", "sparse", "none"]] = {
    "BTC-USD": "rich",
    "BTC": "rich",
    "XBT-USD": "rich",
    "ETH-USD": "none",
    "ETH": "none",
    "SOL-USD": "none",
    "SOL": "none",
}


class ValuationTier(str, Enum):
    """SDCA valuation ladder (#1086): enhanced on-chain vs basic rolling-z."""

    ONCHAIN_ENHANCED = "onchain_enhanced"
    BASIC = "basic"


class SdcaValuationTierResult(BaseModel):
    """Resolved tier: basic ``RiskModel`` and optional on-chain z votes."""

    model_config = ConfigDict(frozen=True, strict=True, arbitrary_types_allowed=True)

    tier: ValuationTier
    risk_model: RiskModel
    onchain_indicators: tuple[IndicatorWeight, ...] = ()
    reason: str = ""


def asset_onchain_coverage(symbol: str) -> Literal["rich", "sparse", "none"]:
    """Which on-chain metrics exist for ``symbol`` (BRK is BTC-native)."""
    key = symbol.strip().upper()
    if key in _COVERAGE:
        return _COVERAGE[key]
    # Bare tickers like "btc"
    base = key.split("-")[0]
    return _COVERAGE.get(base, "none")


def causal_expanding_z(
    values: pl.Series,
    *,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Causal expanding z-score clipped to ``[-3, 3]``. Null until ``min_samples``."""
    if min_samples < 2:
        raise ValueError(f"min_samples must be >= 2, got {min_samples}")
    n = values.len()
    if n == 0:
        return values
    window = min(max(n, min_samples), _EXPANDING_CAP)
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def mvrv_z_score(
    mvrv: pl.Series,
    *,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Local Glassnode-style MVRV-Z: causal expanding z of ``−MVRV`` (cheap = +)."""
    return (-causal_expanding_z(mvrv, min_samples=min_samples)).alias("mvrv_z")


def onchain_metric_z(
    values: pl.Series,
    *,
    name: str,
    invert: bool = True,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Causal expanding z; ``invert=True`` maps high raw → rich (−z)."""
    z = causal_expanding_z(values, min_samples=min_samples)
    if invert:
        z = -z
    return z.alias(name)


def load_onchain_parquet_frames(
    cache_dir: Path | str,
    series_ids: tuple[str, ...] | list[str] | None = None,
) -> dict[str, pl.DataFrame]:
    """Load ``date``/``value`` parquets written by Bitview ingest. Skip missing."""
    root = Path(cache_dir)
    ids = list(series_ids) if series_ids is not None else list(ONCHAIN_SERIES_IDS)
    out: dict[str, pl.DataFrame] = {}
    for series_id in ids:
        if series_id.lower() in FORBIDDEN_SERIES:
            continue
        path = root / f"{series_id}.parquet"
        if not path.is_file():
            continue
        frame = pl.read_parquet(path)
        if "date" not in frame.columns or "value" not in frame.columns:
            continue
        cleaned = (
            frame.select(
                pl.col("date").cast(pl.Date),
                pl.col("value").cast(pl.Float64),
            )
            .drop_nulls(subset=["date"])
            .unique(subset=["date"], keep="last")
            .sort("date")
        )
        if cleaned.height:
            out[series_id] = cleaned
    return out


def _z_for_series(series_id: str, values: pl.Series) -> pl.Series:
    indicator = _SERIES_TO_INDICATOR.get(series_id, series_id)
    if series_id == "mvrv":
        return mvrv_z_score(values)
    # aSOPR oscillates around 1; Puell/RHODL are high-when-rich.
    return onchain_metric_z(values, name=indicator, invert=True)


def build_onchain_indicator_weights(
    dates: pl.Series,
    series_frames: dict[str, pl.DataFrame],
    *,
    weight: float = 1.0,
    min_samples: int = _MIN_SAMPLES,
) -> list[IndicatorWeight]:
    """Align each available series onto ``dates`` and emit ``IndicatorWeight`` votes.

    Weight defaults to 1.0 so a caller can hand the list straight to
    ``compute_composite_risk``. Published SDCA keeps these **off** (do not add
    to ``SdcaCompositeWeights`` / ``settings.json`` yet).
    """
    if dates.dtype != pl.Date:
        raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
    if weight <= 0:
        raise ValueError(f"weight must be positive, got {weight}")
    indicators: list[IndicatorWeight] = []
    for series_id in ONCHAIN_SERIES_IDS:
        frame = series_frames.get(series_id)
        if frame is None or frame.height == 0:
            continue
        aligned = align_to_dates(dates, frame["date"], frame["value"], forward_fill=False)
        # Recompute min_samples path through helpers that already clip.
        if series_id == "mvrv":
            z = mvrv_z_score(aligned, min_samples=min_samples)
        else:
            z = onchain_metric_z(
                aligned,
                name=_SERIES_TO_INDICATOR[series_id],
                invert=True,
                min_samples=min_samples,
            )
        indicators.append(
            IndicatorWeight(
                name=_SERIES_TO_INDICATOR[series_id],
                z=z,
                weight=weight,
                enabled=True,
            )
        )
    return indicators


def build_onchain_composite_z(
    dates: pl.Series,
    series_frames: dict[str, pl.DataFrame],
    *,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Equal-weight blend of available on-chain z; skip-missing *within* on-chain.

    A day with no on-chain z at all is null. Unlike ``compute_composite_risk``,
    a single missing series does not null the day — that fail-soft is what
    lets research use the blended vote without Bitview gaps killing the book.
    """
    indicators = build_onchain_indicator_weights(
        dates, series_frames, weight=1.0, min_samples=min_samples
    )
    if not indicators:
        return pl.Series("onchain_z", [None] * dates.len(), dtype=pl.Float64)
    df = pl.DataFrame({ind.name: ind.z for ind in indicators})
    # ignore_nulls=True: skip-missing inside the on-chain blend only.
    blended = pl.mean_horizontal(pl.all()).clip(-3.0, 3.0)
    return df.select(blended.alias("onchain_z")).to_series()


class OnChainValuationProvider:
    """Load Bitview cache frames and emit valuation z for composite-risk."""

    def __init__(
        self,
        *,
        cache_dir: Path | str | None = None,
        series_frames: dict[str, pl.DataFrame] | None = None,
        min_samples: int = _MIN_SAMPLES,
    ) -> None:
        if series_frames is not None:
            self._frames = dict(series_frames)
        elif cache_dir is not None:
            self._frames = load_onchain_parquet_frames(cache_dir)
        else:
            self._frames = {}
        self.min_samples = min_samples

    @property
    def series_ids(self) -> tuple[str, ...]:
        return tuple(self._frames.keys())

    def has_data(self) -> bool:
        return any(frame.height > 0 for frame in self._frames.values())

    def indicator_weights(self, dates: pl.Series) -> list[IndicatorWeight]:
        return build_onchain_indicator_weights(dates, self._frames, min_samples=self.min_samples)

    def valuation_z(self, dates: pl.Series) -> pl.Series:
        """Blended on-chain valuation z consumable as one composite vote."""
        return build_onchain_composite_z(dates, self._frames, min_samples=self.min_samples)


def resolve_sdca_valuation_tier(
    symbol: str,
    *,
    dates: pl.Series,
    price: pl.Series,
    cache_dir: Path | str | None = None,
    provider: OnChainValuationProvider | None = None,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
) -> SdcaValuationTierResult:
    """Pick enhanced on-chain votes or fall back to basic ``rolling_z`` rails.

    Enhanced requires BTC-rich coverage **and** at least one cached series.
    Basic tier always returns a ``RollingZRiskModel`` (std-dev bands).
    """
    coverage = asset_onchain_coverage(symbol)
    prov = provider
    if prov is None and cache_dir is not None:
        prov = OnChainValuationProvider(cache_dir=cache_dir)
    if prov is None:
        prov = OnChainValuationProvider(series_frames={})

    basic = RollingZRiskModel(dates, price, window=rolling_window)
    if coverage != "rich" or not prov.has_data():
        reason = f"coverage={coverage}, onchain_series={list(prov.series_ids) or 'none'}"
        return SdcaValuationTierResult(
            tier=ValuationTier.BASIC,
            risk_model=basic,
            onchain_indicators=(),
            reason=f"fallback to basic rolling_z ({reason})",
        )

    indicators = tuple(prov.indicator_weights(dates))
    if not indicators:
        return SdcaValuationTierResult(
            tier=ValuationTier.BASIC,
            risk_model=basic,
            onchain_indicators=(),
            reason="on-chain frames present but no aligned z; basic rolling_z",
        )

    return SdcaValuationTierResult(
        tier=ValuationTier.ONCHAIN_ENHANCED,
        risk_model=basic,  # price rails still available; on-chain is the extra vote
        onchain_indicators=indicators,
        reason=f"on-chain enhanced ({', '.join(i.name for i in indicators)})",
    )


class OnChainCoverageMap(BaseModel):
    """Documented coverage for ARCHITECTURE / operators."""

    model_config = ConfigDict(frozen=True, strict=True)

    rich: tuple[str, ...] = Field(default=("BTC-USD",))
    sparse: tuple[str, ...] = ()
    none: tuple[str, ...] = Field(default=("ETH-USD", "SOL-USD"))
    source: str = "bitview/BRK day1"
    license: str = "BRK MIT; hosted bitview.space no SLA"


__all__ = [
    "ONCHAIN_INDICATOR_NAMES",
    "ONCHAIN_SERIES_IDS",
    "OnChainCoverageMap",
    "OnChainValuationProvider",
    "SdcaValuationTierResult",
    "ValuationTier",
    "asset_onchain_coverage",
    "build_onchain_composite_z",
    "build_onchain_indicator_weights",
    "causal_expanding_z",
    "load_onchain_parquet_frames",
    "mvrv_z_score",
    "onchain_metric_z",
    "resolve_sdca_valuation_tier",
]
