"""Versioned Pydantic v2 schema for a user's investment profile.

The ``InvestmentProfile`` is a coarse-grained input that downstream services
(Atlas idea generation, Hermes deliberation, Kairos portfolio construction)
consult to filter strategies and constrain allocation. It is intentionally
small: refinements are captured by bumping ``schema_version`` and shipping a
migration, not by inflating this model.

See ``digiquant/docs/profiles/README.md`` for the migration story and field
rationale.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvestmentProfile(BaseModel):
    """User investment profile (schema v1).

    Attributes
    ----------
    schema_version
        Monotonic schema version. Increment only on breaking changes.
        Additive fields with defaults do not require a bump.
    risk_tolerance
        Coarse risk bucket. Refined risk metrics (e.g. CVaR limits) belong
        on a per-portfolio policy object, not here.
    horizon_years
        Investment horizon in whole years. Bounded ``1..50`` to cover a
        single tactical year through a multi-decade plan.
    liquidity_needs
        How much of the portfolio may be locked up in illiquid positions:
        ``low`` tolerates lockups, ``high`` requires daily liquidity.
    base_currency
        ISO 4217 alphabetic currency code (e.g. ``USD``). Normalized to
        upper case before validation.
    tax_jurisdiction
        Coarse tax bucket — finer detail (state, ISA, RRSP, PEA, etc.) is
        deferred to a future ``TaxProfile`` companion model.
    esg_preference
        ``none`` ignores ESG, ``tilt`` overweights leaders, ``strict``
        excludes laggards entirely.
    excluded_sectors
        Free-form sector exclusion list (e.g. ``tobacco``, ``defense``).
        Normalized to lower case and de-duplicated while preserving
        insertion order.
    experience_level
        Self-reported sophistication. Used to gate complex order types
        and structured products in the UI.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Schema version; bump on breaking changes.",
    )
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = Field(
        ...,
        description="Coarse risk bucket.",
    )
    horizon_years: int = Field(
        ...,
        ge=1,
        le=50,
        description="Investment horizon in whole years.",
    )
    liquidity_needs: Literal["low", "medium", "high"] = Field(
        ...,
        description="Tolerance for capital lockup; high = needs daily liquidity.",
    )
    base_currency: str = Field(
        ...,
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 alphabetic currency code (3 upper-case letters).",
    )
    tax_jurisdiction: Literal["US", "EU", "UK", "CA", "AU", "OTHER"] = Field(
        ...,
        description="Coarse tax jurisdiction; refine via a future TaxProfile.",
    )
    esg_preference: Literal["none", "tilt", "strict"] = Field(
        ...,
        description="ESG posture: ignore, overweight leaders, or hard-exclude laggards.",
    )
    excluded_sectors: list[str] = Field(
        default_factory=list,
        description="Sectors to exclude (lower-cased, de-duplicated).",
    )
    experience_level: Literal["novice", "intermediate", "expert"] = Field(
        ...,
        description="Self-reported investing experience.",
    )

    @field_validator("base_currency", mode="before")
    @classmethod
    def _upper_currency(cls, value: object) -> object:
        """Upper-case currency before pattern validation rejects mixed case."""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("excluded_sectors", mode="after")
    @classmethod
    def _normalize_sectors(cls, value: list[str]) -> list[str]:
        """Lower-case, strip, drop empties, and de-duplicate while keeping order."""
        seen: dict[str, None] = {}
        for raw in value:
            if not isinstance(raw, str):
                # Pydantic's list[str] coercion will already reject non-strings,
                # but guard explicitly to keep the validator total.
                raise TypeError(f"excluded_sectors entries must be str, got {type(raw)!r}")
            normalized = raw.strip().lower()
            if not normalized:
                continue
            seen.setdefault(normalized, None)
        return list(seen)
