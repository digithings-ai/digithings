"""Unit tests for Yahoo-backed canonical instrument metadata."""

from datetime import datetime, timezone

import pytest

from digiquant.data.prices.instrument_metadata import (
    fetch_instrument_metadata,
    metadata_from_yahoo_info,
)

pytestmark = pytest.mark.unit


def test_maps_provider_identity_and_olympus_classification() -> None:
    metadata = metadata_from_yahoo_info(
        "xle",
        {
            "longName": "Energy Select Sector SPDR Fund",
            "shortName": "SPDR Select Sector Fund - Ene",
            "quoteType": "ETF",
            "fullExchangeName": "NYSEArca",
            "currency": "USD",
            "country": "United States",
            "sector": "Energy",
            "industry": "Asset Management",
            "market": "us_market",
            "exchangeTimezoneName": "America/New_York",
        },
        fetched_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )

    assert metadata.ticker == "XLE"
    assert metadata.official_name == "Energy Select Sector SPDR Fund"
    assert metadata.instrument_type == "ETF"
    assert metadata.asset_class == "EQUITY"
    assert metadata.category == "sector-energy"
    assert metadata.exchange == "NYSEArca"
    assert metadata.provider_metadata["market"] == "us_market"


def test_fetch_isolates_failures_without_emitting_destructive_fallbacks() -> None:
    def loader(ticker: str):
        if ticker == "BAD":
            raise RuntimeError("provider unavailable")
        return {"longName": f"Official {ticker}", "quoteType": "ETF"}

    result = fetch_instrument_metadata(
        [" xle ", "BAD", "XLE", "CASH"],
        info_loader=loader,
        throttle_s=0,
    )

    assert list(result.records) == ["XLE", "CASH"]
    assert result.records["XLE"].official_name == "Official XLE"
    assert result.records["CASH"].official_name == "Cash"
    assert result.errors == {"BAD": "provider unavailable"}


def test_missing_provider_name_is_unresolved() -> None:
    result = fetch_instrument_metadata(
        ["XLE"],
        info_loader=lambda _: {"quoteType": "ETF"},
        throttle_s=0,
    )

    assert result.records == {}
    assert "no longName or shortName" in result.errors["XLE"]
