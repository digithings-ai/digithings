"""DB-pinable dashboard ProfileConfig (Track B / #2609).

The digithings-owned **house** profile is the immutable always-on default run.
User overlays are additional ProfileConfig versions that may request different
universe / risk / themes / budgets. They must never claim the house key or
cancel/replace the house run.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.profiles.asset_preferences import AssetPreferences
from digiquant.profiles.investment_profile import InvestmentProfile

HOUSE_PROFILE_KEY = "house"
# Frozen identity string (migration 075). Do not rename with the package.
_PROFILE_VERSION_NS = uuid5(NAMESPACE_URL, "digithings.olympus.profile_config")


class ProfileConfigMissingError(LookupError):
    """Raised when an exact profile_config version pin cannot be resolved."""


def profile_config_version_id(profile_key: str, schema_version: int = 1) -> UUID:
    """Deterministic version id for a logical profile key + schema version."""
    return uuid5(_PROFILE_VERSION_NS, f"{profile_key}:v{schema_version}")


class ProfileConfig(BaseModel):
    """Versioned investment overlay pin for research/portfolio preflight.

    ``is_house_default`` rows own the digithings house run identity. Overlay
    rows must use a non-house ``profile_key`` and never set ``is_house_default``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    version_id: UUID
    profile_key: str = Field(..., min_length=1, max_length=100)
    schema_version: int = Field(default=1, ge=1)
    is_house_default: bool
    label: str = Field(..., min_length=1, max_length=200)
    watchlist: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    research_budget_usd: Decimal | None = Field(default=None, ge=0)
    investment: InvestmentProfile | None = None
    assets: AssetPreferences | None = None

    @field_validator("watchlist", "themes", mode="before")
    @classmethod
    def _normalize_str_lists(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        out: list[str] = []
        seen_lower: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                return value
            cleaned = item.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen_lower:
                continue
            seen_lower.add(lowered)
            out.append(cleaned)
        return out

    @field_validator("watchlist")
    @classmethod
    def _upper_watchlist(cls, value: list[str]) -> list[str]:
        return [ticker.upper() for ticker in value]

    @field_validator("themes")
    @classmethod
    def _lower_themes(cls, value: list[str]) -> list[str]:
        return [theme.lower() for theme in value]

    @model_validator(mode="after")
    def _house_key_invariant(self) -> ProfileConfig:
        if self.is_house_default and self.profile_key != HOUSE_PROFILE_KEY:
            raise ValueError("house default ProfileConfig must use profile_key='house'")
        if not self.is_house_default and self.profile_key == HOUSE_PROFILE_KEY:
            raise ValueError("overlay ProfileConfig cannot use the reserved house profile_key")
        return self


def house_profile_config(*, schema_version: int = 1) -> ProfileConfig:
    """In-memory digithings house default — always available without a DB round-trip."""
    return ProfileConfig(
        version_id=profile_config_version_id(HOUSE_PROFILE_KEY, schema_version),
        profile_key=HOUSE_PROFILE_KEY,
        schema_version=schema_version,
        is_house_default=True,
        label="digithings house",
        investment=InvestmentProfile(
            risk_tolerance="moderate",
            horizon_years=10,
            liquidity_needs="medium",
            base_currency="USD",
            tax_jurisdiction="US",
            esg_preference="none",
            experience_level="intermediate",
        ),
    )


def load_profile_config_by_version_id(
    store: Mapping[str, ProfileConfig | Mapping[str, Any]],
    version_id: UUID,
) -> ProfileConfig:
    """Resolve an exact version pin; missing ids fail closed (no unversioned latest)."""
    key = str(version_id)
    if key not in store:
        raise ProfileConfigMissingError(f"profile_config version {version_id} not found")
    raw = store[key]
    if isinstance(raw, ProfileConfig):
        if raw.version_id != version_id:
            raise ProfileConfigMissingError(
                f"profile_config store key {key} disagrees with payload version_id {raw.version_id}"
            )
        return raw
    cfg = ProfileConfig.model_validate(raw)
    if cfg.version_id != version_id:
        raise ProfileConfigMissingError(
            f"profile_config payload version_id {cfg.version_id} != requested {version_id}"
        )
    return cfg


def pin_profile_config_for_preflight(
    *,
    requested_version_id: UUID | None,
    store: Mapping[str, ProfileConfig | Mapping[str, Any]] | None = None,
) -> ProfileConfig:
    """Preflight helper: pin requested overlay or fall back to the house default.

    Overlay requests with a missing pin fail closed. Omitting ``requested_version_id``
    selects the house profile (always-on immutable baseline).
    """
    if requested_version_id is None:
        return house_profile_config()
    if store is None:
        raise ProfileConfigMissingError(
            f"profile_config version {requested_version_id} requested but no store provided"
        )
    return load_profile_config_by_version_id(store, requested_version_id)
