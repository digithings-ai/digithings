"""Unit tests for the canonical Olympus instrument metadata contract."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from digiquant.olympus.instrument_metadata import InstrumentMetadata

pytestmark = pytest.mark.unit


def test_normalizes_symbol_and_serializes_provider_metadata() -> None:
    metadata = InstrumentMetadata(
        ticker=" xle ",
        official_name="Energy Select Sector SPDR Fund",
        instrument_type="ETF",
        asset_class="EQUITY",
        category="sector-energy",
        exchange="NYSEArca",
        currency="USD",
        country="United States",
        provider="yahoo",
        provider_metadata={"quote_type": "ETF"},
        source_updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )

    row = metadata.to_row()
    assert row["ticker"] == "XLE"
    assert row["official_name"] == "Energy Select Sector SPDR Fund"
    assert row["provider_metadata"] == {"quote_type": "ETF"}
    assert row["source_updated_at"] == "2026-07-20T00:00:00Z"


def test_fallback_uses_deterministic_olympus_classification() -> None:
    metadata = InstrumentMetadata.fallback(" tlt ")

    assert metadata.ticker == "TLT"
    assert metadata.official_name == "TLT"
    assert metadata.asset_class == "FIXED_INCOME"
    assert metadata.category == "fixed-income"
    assert metadata.provider_metadata == {"resolution": "unresolved"}


def test_rejects_empty_official_name() -> None:
    with pytest.raises(ValidationError):
        InstrumentMetadata(
            ticker="XLE",
            official_name=" ",
            asset_class="EQUITY",
            category="sector-energy",
            provider="yahoo",
            source_updated_at=datetime.now(timezone.utc),
        )
