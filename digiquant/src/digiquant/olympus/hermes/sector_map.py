"""Asset-class / sector bucketing for the whole book (Pillar 2).

The sizer's concentration control (``max_sector_pct``) and the exposure roll-ups need
to bucket *every* ticker the PM can hold — not just the GICS equity sectors that
``config/sectors.yaml`` covers, but the fixed-income, commodity, crypto, FX,
international, and cash sleeves too. This module unifies both sources:

- Equity single-names + GICS sector ETFs resolve to their sector slug (via
  :func:`~digiquant.olympus.atlas.sectors_config.load_sectors`), coarse class ``EQUITY``.
- Everything else resolves via ``config/asset_classes.yaml``.

**Authority on conflict:** ``sectors.yaml`` drives the *research* fan-out (what Atlas
studies), while ``asset_classes.yaml`` reflects a ticker's *true risk exposure*. The
latter therefore wins when both list a ticker — e.g. ``USO`` is researched under the
Energy sector but is a crude-oil-futures ETF, so for risk bucketing it is ``commodity``;
``QQQ`` is a broad multi-sector index, so it is ``equity-broad`` rather than a pure
Technology bet.

Two granularities are exposed:

- :func:`sector_bucket` — the fine-grained concentration bucket (a GICS slug like
  ``sector-technology`` for equities, or a sleeve slug like ``fixed-income`` /
  ``commodity`` / ``crypto`` / ``fx`` / ``international`` / ``equity-broad`` / ``cash``).
  Fed into ``TickerRisk.sector`` so ``max_sector_pct`` controls concentration.
- :func:`asset_class` — the coarse class (``EQUITY`` / ``INTERNATIONAL`` /
  ``FIXED_INCOME`` / ``COMMODITY`` / ``CRYPTO`` / ``FX`` / ``CASH``) for exposure
  roll-ups.

Both default to ``"unknown"`` / ``"UNKNOWN"`` for unlisted tickers — a conservative
default the sizer treats as its own concentration bucket. Lookups are case-insensitive;
the built map is cached (config is static per process — call ``_bucket_map.cache_clear()``
in tests that patch the YAML).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from digiquant.olympus.atlas.sectors_config import load_sectors

UNKNOWN_BUCKET = "unknown"
UNKNOWN_CLASS = "UNKNOWN"


@dataclass(frozen=True)
class Bucket:
    """Where a ticker sits for concentration (``sector``) and exposure (``asset_class``)."""

    sector: str
    asset_class: str


def _norm(ticker: str) -> str:
    return str(ticker).strip().upper()


def _asset_classes_path() -> Path:
    # this file: …/olympus/hermes/sector_map.py → …/olympus/atlas/config/asset_classes.yaml
    return Path(__file__).resolve().parents[1] / "atlas" / "config" / "asset_classes.yaml"


@lru_cache(maxsize=1)
def _bucket_map() -> dict[str, Bucket]:
    """Build the ticker → :class:`Bucket` map from sectors.yaml + asset_classes.yaml.

    Equity sectors fill first; ``asset_classes.yaml`` is layered on top so it wins on the
    documented overlaps (true-exposure correction), keeping the cross-asset config
    authoritative for risk bucketing.
    """
    out: dict[str, Bucket] = {}
    # 1) GICS equity sectors → sector slug + coarse EQUITY.
    for sector in load_sectors():
        for ticker in (*sector.etfs, *sector.top_tickers):
            out[_norm(ticker)] = Bucket(sector=sector.slug, asset_class="EQUITY")
    # 2) Cross-asset / broad-equity / international / cash sleeves (override on conflict).
    data = yaml.safe_load(_asset_classes_path().read_text(encoding="utf-8")) or {}
    buckets = data.get("asset_classes")
    if not isinstance(buckets, dict) or not buckets:
        raise ValueError(f"{_asset_classes_path()} must declare a non-empty 'asset_classes' map")
    for slug, spec in buckets.items():
        spec = spec or {}
        klass = str(spec.get("asset_class") or UNKNOWN_CLASS)
        for ticker in spec.get("tickers") or []:
            out[_norm(ticker)] = Bucket(sector=str(slug), asset_class=klass)
    return out


def bucket(ticker: str) -> Bucket:
    """Full :class:`Bucket` for ``ticker`` (case-insensitive); UNKNOWN when unlisted."""
    return _bucket_map().get(_norm(ticker), Bucket(UNKNOWN_BUCKET, UNKNOWN_CLASS))


def sector_bucket(ticker: str) -> str:
    """Fine-grained concentration bucket (GICS slug or sleeve slug); ``"unknown"`` default."""
    return bucket(ticker).sector


def asset_class(ticker: str) -> str:
    """Coarse asset class for exposure roll-ups; ``"UNKNOWN"`` default."""
    return bucket(ticker).asset_class


__all__ = [
    "UNKNOWN_BUCKET",
    "UNKNOWN_CLASS",
    "Bucket",
    "asset_class",
    "bucket",
    "sector_bucket",
]
