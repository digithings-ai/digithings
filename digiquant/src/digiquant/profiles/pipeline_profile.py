"""PipelineProfile / ProfileConfig — Olympus Track B investment overlay seam (#2607).

This package is **not** the DigiChat / UI ``InvestmentProfile`` posture model.
``InvestmentProfile`` captures user intake prefs; ``ProfileConfig`` is the
DB-backed run policy (universe, risk prefs, research themes, planner budgets)
that plugs into the **same** Atlas→Hermes topology.

Hard invariants (vision brief / #2607):

* digithings owns the **house** profile and house run identity — always-on,
  immutable; no overlay may cancel, replace, or mutate that identity.
* Profiles do **not** fork the graph; they pin config into graph state.
* Overlay application is **off or shadow by default**; even when active later,
  this seam never expands H4 roster/cap or rewrites H7/H8 authority.
* Shared-corpus requests use tenant-agnostic keys (WP12 follow-on); books stay
  user-private (Track A).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HOUSE_PROFILE_ID = "digithings-house"
HOUSE_RUN_ID = "digithings-house-run"
HOUSE_DISPLAY_NAME = "digithings house ETF baseline"

ProfileKind = Literal["house", "overlay"]
PipelineProfileMode = Literal["off", "shadow", "active"]
SUPPORTED_CONFIG_SCHEMA_VERSION = 1


class UniversePrefs(BaseModel):
    """Universe knobs for compile / mandate — not a private research tree."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    include_tickers: list[str] = Field(
        default_factory=list,
        description="Optional ticker includes (upper-cased). Empty = house watchlist.",
    )
    exclude_tickers: list[str] = Field(
        default_factory=list,
        description="Hard ticker exclusions (upper-cased).",
    )
    asset_classes: list[str] = Field(
        default_factory=list,
        description="Optional asset-class filters (lower-cased), e.g. etf.",
    )

    @field_validator("include_tickers", "exclude_tickers", mode="after")
    @classmethod
    def _normalize_tickers(cls, value: list[str]) -> list[str]:
        return _dedupe_upper(value)

    @field_validator("asset_classes", mode="after")
    @classmethod
    def _normalize_asset_classes(cls, value: list[str]) -> list[str]:
        return _dedupe_lower(value)


class RiskPrefs(BaseModel):
    """Coarse risk posture for mandate / book — not H8 sizing authority."""

    model_config = ConfigDict(extra="forbid")

    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = Field(
        default="moderate",
        description="Coarse risk bucket for overlays; house defaults to moderate.",
    )
    max_position_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional soft position cap (fraction). None = unset.",
    )
    max_gross_exposure: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Optional soft gross exposure (fraction). None = unset.",
    )


class ResearchThemeRequest(BaseModel):
    """Request additional research into the **shared** corpus (WP12 hook).

    Keys are tenant-agnostic (``theme:…`` / ``asset:…`` / ``segment:…``).
    Overlays publish-if-missing; they do not own private research trees.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    theme_key: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Tenant-agnostic corpus key, e.g. theme:ai-infra or asset:NVDA.",
    )
    publish_if_missing: bool = Field(
        default=True,
        description="WP12: request publish into shared corpus when absent/stale.",
    )

    @field_validator("theme_key", mode="after")
    @classmethod
    def _normalize_theme_key(cls, value: str) -> str:
        key = value.strip().lower()
        if not key:
            raise ValueError("theme_key must be non-empty")
        return key


class PlannerBudgetKnobs(BaseModel):
    """Planner spend caps (WP13 shadow hook). Defaults are inert (zero).

    These knobs are recorded on the pin for observability; enforcement is a
    follow-on (WP13). They must never expand H4 width or rewrite H7/H8.
    """

    model_config = ConfigDict(extra="forbid")

    max_theme_refreshes: int = Field(default=0, ge=0, le=500)
    max_asset_refreshes: int = Field(default=0, ge=0, le=500)
    max_llm_calls: int | None = Field(
        default=None,
        ge=0,
        le=10_000,
        description="Optional hard LLM call budget for overlay-requested work.",
    )


class ProfileConfig(BaseModel):
    """Versioned pipeline investment/run config (DB JSONB payload)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(
        default=SUPPORTED_CONFIG_SCHEMA_VERSION,
        ge=1,
        description="Config schema version; bump on breaking changes.",
    )
    universe: UniversePrefs = Field(default_factory=UniversePrefs)
    risk: RiskPrefs = Field(default_factory=RiskPrefs)
    research_themes: list[ResearchThemeRequest] = Field(default_factory=list)
    planner_budgets: PlannerBudgetKnobs = Field(default_factory=PlannerBudgetKnobs)

    @model_validator(mode="after")
    def _supported_schema(self) -> ProfileConfig:
        if self.schema_version > SUPPORTED_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ProfileConfig schema_version={self.schema_version}; "
                f"loader supports <= {SUPPORTED_CONFIG_SCHEMA_VERSION}"
            )
        return self


class PipelineProfile(BaseModel):
    """Thin wrapper around ``ProfileConfig`` with house/overlay identity."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = Field(default=1, ge=1)
    profile_id: str = Field(..., min_length=1, max_length=100)
    kind: ProfileKind
    display_name: str = Field(..., min_length=1, max_length=200)
    config: ProfileConfig = Field(default_factory=ProfileConfig)
    # House run identity — overlays may *reference* it but never replace it.
    house_run_id: str = Field(default=HOUSE_RUN_ID, min_length=1, max_length=100)
    always_on: bool = Field(
        default=False,
        description="True only for the digithings house profile.",
    )
    # Explicit anti-goal field: must always be False (overlays cannot cancel house).
    cancel_house_run: Literal[False] = False

    @model_validator(mode="after")
    def _enforce_house_invariants(self) -> PipelineProfile:
        if self.cancel_house_run is not False:  # pragma: no cover — Literal[False]
            raise ValueError("profiles cannot cancel the digithings house run")
        if self.kind == "house":
            if self.profile_id != HOUSE_PROFILE_ID:
                raise ValueError(
                    f"house profile_id must be {HOUSE_PROFILE_ID!r}, got {self.profile_id!r}"
                )
            if self.house_run_id != HOUSE_RUN_ID:
                raise ValueError(
                    f"house_run_id is immutable ({HOUSE_RUN_ID!r}); got {self.house_run_id!r}"
                )
            if not self.always_on:
                raise ValueError("house profile must be always_on=True")
        else:
            if self.profile_id == HOUSE_PROFILE_ID:
                raise ValueError("overlay cannot claim digithings house profile_id")
            if self.always_on:
                raise ValueError("overlay profiles cannot be always_on")
            if self.house_run_id != HOUSE_RUN_ID:
                raise ValueError(
                    "overlays must reference the digithings house_run_id; "
                    "they cannot replace house run identity"
                )
        return self


class PinnedPipelineProfile(BaseModel):
    """Preflight pin: house baseline + optional overlay under a mode.

    ``effective_config`` is always the house config while mode is ``off`` or
    ``shadow`` (default). Overlay config is retained for observability / WP12
    request lists but does not alter H4/H7/H8 authority in this seam.
    """

    model_config = ConfigDict(extra="forbid")

    house: PipelineProfile
    overlay: PipelineProfile | None = None
    mode: PipelineProfileMode = "off"
    effective_config: ProfileConfig
    applies_overlay: bool = False
    # Explicit pins so callers/tests can assert authority spine is untouched.
    h4_roster_cap_unchanged: Literal[True] = True
    h7_h8_authority_unchanged: Literal[True] = True
    house_run_id: str = HOUSE_RUN_ID

    @model_validator(mode="after")
    def _house_always_present(self) -> PinnedPipelineProfile:
        if self.house.kind != "house" or self.house.profile_id != HOUSE_PROFILE_ID:
            raise ValueError("pinned house must be the digithings house profile")
        if self.house_run_id != HOUSE_RUN_ID:
            raise ValueError("pinned house_run_id is immutable")
        if self.overlay is not None and self.overlay.kind != "overlay":
            raise ValueError("pinned overlay must have kind='overlay'")
        if self.mode in ("off", "shadow") and self.applies_overlay:
            raise ValueError("applies_overlay must be False when mode is off/shadow")
        return self


def default_house_config() -> ProfileConfig:
    """In-code digithings house baseline (ETF paper book)."""
    return ProfileConfig(
        schema_version=SUPPORTED_CONFIG_SCHEMA_VERSION,
        universe=UniversePrefs(asset_classes=["etf"]),
        risk=RiskPrefs(risk_tolerance="moderate"),
        research_themes=[],
        planner_budgets=PlannerBudgetKnobs(),
    )


def default_house_profile() -> PipelineProfile:
    """Canonical digithings house ``PipelineProfile`` (DB seed mirror)."""
    return PipelineProfile(
        schema_version=1,
        profile_id=HOUSE_PROFILE_ID,
        kind="house",
        display_name=HOUSE_DISPLAY_NAME,
        config=default_house_config(),
        house_run_id=HOUSE_RUN_ID,
        always_on=True,
        cancel_house_run=False,
    )


def _dedupe_upper(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in values:
        normalized = raw.strip().upper()
        if normalized:
            seen.setdefault(normalized, None)
    return list(seen)


def _dedupe_lower(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in values:
        normalized = raw.strip().lower()
        if normalized:
            seen.setdefault(normalized, None)
    return list(seen)
