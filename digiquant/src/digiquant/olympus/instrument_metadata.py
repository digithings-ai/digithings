"""Canonical metadata contract for instruments tracked by Olympus."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any  # noqa  # scored-lint suppression: provider jsonb payloads are heterogeneous

from pydantic import BaseModel, ConfigDict, Field, field_validator

from digiquant.olympus.hermes.sector_map import asset_class, sector_bucket


class InstrumentMetadata(BaseModel):
    """Provider-sourced identity plus deterministic Olympus classification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str = Field(min_length=1, max_length=32)
    official_name: str = Field(min_length=1, max_length=300)
    instrument_type: str | None = Field(default=None, max_length=80)
    asset_class: str
    category: str
    sector: str | None = Field(default=None, max_length=160)
    industry: str | None = Field(default=None, max_length=160)
    exchange: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=12)
    country: str | None = Field(default=None, max_length=80)
    provider: str = Field(min_length=1, max_length=80)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    source_updated_at: datetime

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> str:
        return str(value).strip().upper()

    @classmethod
    def fallback(cls, ticker: str, *, provider: str = "olympus") -> InstrumentMetadata:
        """Return a truthful row when a provider cannot resolve a symbol."""
        normalized = str(ticker).strip().upper()
        return cls(
            ticker=normalized,
            official_name=normalized,
            asset_class=asset_class(normalized),
            category=sector_bucket(normalized),
            provider=provider,
            provider_metadata={"resolution": "unresolved"},
            source_updated_at=datetime.now(timezone.utc),
        )

    def to_row(self) -> dict[str, Any]:
        """Serialize to the Supabase instruments row shape."""
        return self.model_dump(mode="json")


__all__ = ["InstrumentMetadata"]
