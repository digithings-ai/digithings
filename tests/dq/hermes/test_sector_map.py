"""Asset-class / sector bucketing (Pillar 2).

``sector_map`` buckets every holdable ticker for concentration control + exposure
roll-ups, unifying the GICS equity sectors (sectors.yaml) with the cross-asset sleeves
(asset_classes.yaml). asset_classes.yaml is authoritative on conflict (true risk
exposure beats research fan-out): USO is a commodity, QQQ is broad equity.
"""

from __future__ import annotations

import pytest

from digiquant.olympus.atlas.sectors_config import load_sectors
from digiquant.olympus.hermes import sector_map
from digiquant.olympus.hermes.sector_map import (
    UNKNOWN_BUCKET,
    UNKNOWN_CLASS,
    Bucket,
    asset_class,
    bucket,
    sector_bucket,
)

pytestmark = pytest.mark.unit


def test_equity_single_name_maps_to_its_gics_sector() -> None:
    assert sector_bucket("AAPL") == "sector-technology"
    assert asset_class("AAPL") == "EQUITY"


def test_sector_etf_maps_to_its_sector() -> None:
    assert sector_bucket("XLV") == "sector-healthcare"
    assert asset_class("XLV") == "EQUITY"


def test_broad_equity_etf_is_equity_broad() -> None:
    assert bucket("SPY") == Bucket(sector="equity-broad", asset_class="EQUITY")
    assert sector_bucket("VTI") == "equity-broad"


def test_fixed_income_bucket() -> None:
    for t in ("BIL", "SHY", "TLT", "AGG", "HYG"):
        assert bucket(t) == Bucket(sector="fixed-income", asset_class="FIXED_INCOME"), t


def test_commodity_bucket() -> None:
    for t in ("IAU", "GLD", "SLV"):
        assert bucket(t) == Bucket(sector="commodity", asset_class="COMMODITY"), t


def test_crypto_bucket() -> None:
    assert bucket("IBIT") == Bucket(sector="crypto", asset_class="CRYPTO")
    assert bucket("BTC-USD") == Bucket(sector="crypto", asset_class="CRYPTO")


def test_international_bucket() -> None:
    assert bucket("EFA") == Bucket(sector="international", asset_class="INTERNATIONAL")
    assert asset_class("VWO") == "INTERNATIONAL"


def test_fx_and_cash_buckets() -> None:
    assert bucket("UUP") == Bucket(sector="fx", asset_class="FX")
    assert bucket("CASH") == Bucket(sector="cash", asset_class="CASH")


def test_asset_classes_yaml_wins_on_documented_conflicts() -> None:
    # USO is researched under the Energy sector (sectors.yaml) but is a crude-oil-futures
    # ETF → commodity for risk. QQQ is a broad multi-sector index → equity-broad, not a
    # pure Technology bet. asset_classes.yaml is authoritative for both.
    assert bucket("USO") == Bucket(sector="commodity", asset_class="COMMODITY")
    assert bucket("QQQ") == Bucket(sector="equity-broad", asset_class="EQUITY")


def test_dual_listed_ticker_resolves_deterministically() -> None:
    # GOOGL is listed in BOTH Technology and Communication Services in sectors.yaml (per
    # real GICS). The build layers sectors in file order with last-wins, so the later
    # sector (Communication Services) is authoritative. Pin the concrete outcome: this
    # locks determinism — a non-deterministic build or a sectors.yaml reorder breaks it.
    listing = {s.slug for s in load_sectors() if "GOOGL" in {t.upper() for t in s.top_tickers}}
    assert listing == {"sector-technology", "sector-comms"}, listing
    assert bucket("GOOGL").sector == "sector-comms"
    assert asset_class("GOOGL") == "EQUITY"


def test_unknown_ticker_falls_back() -> None:
    assert bucket("ZZZZ") == Bucket(UNKNOWN_BUCKET, UNKNOWN_CLASS)
    assert sector_bucket("not-a-ticker") == "unknown"
    assert asset_class("") == "UNKNOWN"


def test_lookup_is_case_and_whitespace_insensitive() -> None:
    assert sector_bucket("aapl") == "sector-technology"
    assert sector_bucket("  spy  ") == "equity-broad"
    assert asset_class("bil") == "FIXED_INCOME"


def test_every_sector_single_name_is_equity() -> None:
    # Single names are never overridden by the cross-asset config, so each GICS sector's
    # representative tickers stay EQUITY. A ticker dual-listed across sectors (e.g. GOOGL
    # in Technology *and* Communication Services, per real GICS) resolves deterministically
    # to one of the sectors that lists it.
    listing_slugs: dict[str, set[str]] = {}
    for sector in load_sectors():
        for ticker in sector.top_tickers:
            listing_slugs.setdefault(ticker.upper(), set()).add(sector.slug)
    for ticker, slugs in listing_slugs.items():
        b = bucket(ticker)
        assert b.sector in slugs, f"{ticker} → {b.sector}, expected one of {slugs}"
        assert b.asset_class == "EQUITY", ticker


def test_module_exports_are_callable() -> None:
    assert callable(sector_map.bucket)
    assert callable(sector_map.sector_bucket)
    assert callable(sector_map.asset_class)
