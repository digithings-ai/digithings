"""WP13-class AttentionPlan planner — shadow only (Track B / #2616).

Produces typed pre-provider attention decisions with stable refresh reasons while
the **incumbent** ``edit_mode`` path still executes. Planner mode is ``off`` or
``shadow`` only — ``enforce`` is intentionally absent. The digithings house
profile pin is required for plan identity; overlay pins fail closed when missing.
The planner cannot expand an H4 roster or rewrite H7/H8 authority.
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from typing import Literal, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.dashboard.edit_mode.models import ArtifactKey, EditMode, TriageSignal
from digiquant.dashboard.edit_mode.prior import PriorLoader
from digiquant.dashboard.edit_mode.resolve import resolve_edit_mode
from digiquant.dashboard.profile_config import (
    HOUSE_PROFILE_KEY,
    ProfileConfig,
    ProfileConfigMissingError,
    house_profile_config,
    load_profile_config_by_version_id,
    profile_config_version_id,
)

_PLAN_NS = uuid5(NAMESPACE_URL, "digithings.olympus.attention_plan")

PlannerMode = Literal["off", "shadow"]
AttentionAction = Literal["carry", "section_refresh", "deep_refresh"]


class AttentionPlanError(ValueError):
    """Raised when plan inputs violate house/overlay or authority invariants."""


class RefreshReasonCode(StrEnum):
    """Stable refresh reason codes for glass-box UI (#1945) and shadow eval."""

    NO_PRIOR = "no_prior"
    STALE_CONTENT = "stale_content"
    TRIAGE_STALE = "triage_stale"
    TRIAGE_QUIET = "triage_quiet"
    FORCE_FULL = "force_full"
    INCUMBENT_EDIT = "incumbent_edit"
    INCUMBENT_SKIP = "incumbent_skip"
    INCUMBENT_FULL = "incumbent_full"


def _artifact_key_str(key: ArtifactKey) -> str:
    return f"{key[0]}:{key[1]}"


def h4_roster_fingerprint(roster: Sequence[str]) -> str:
    """Deterministic fingerprint of an H4 focus roster (order-sensitive)."""
    normalized = [ticker.strip().upper() for ticker in roster if ticker and ticker.strip()]
    blob = "\n".join(normalized).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def attention_plan_id(
    *,
    run_date: date,
    profile_config_version_id: UUID,
    roster_fingerprint: str,
    schema_version: int = 1,
) -> UUID:
    """Deterministic plan id for identical house pin + roster + run date."""
    return uuid5(
        _PLAN_NS,
        f"{run_date.isoformat()}:{profile_config_version_id}:{roster_fingerprint}:v{schema_version}",
    )


def action_for_edit_mode(mode: EditMode) -> AttentionAction:
    if mode == "skip":
        return "carry"
    if mode == "edit":
        return "section_refresh"
    return "deep_refresh"


def reasons_for_edit_mode(
    mode: EditMode,
    *,
    triage: TriageSignal | None,
    force_full_rewrite: bool,
    had_prior: bool,
) -> list[RefreshReasonCode]:
    reasons: list[RefreshReasonCode] = []
    if force_full_rewrite:
        reasons.append(RefreshReasonCode.FORCE_FULL)
    if not had_prior:
        reasons.append(RefreshReasonCode.NO_PRIOR)
    if triage is not None and triage.mode == "quiet":
        reasons.append(RefreshReasonCode.TRIAGE_QUIET)
    if triage is not None and triage.mode == "stale":
        reasons.append(RefreshReasonCode.TRIAGE_STALE)
    if mode == "full":
        reasons.append(RefreshReasonCode.INCUMBENT_FULL)
        if had_prior and not force_full_rewrite:
            reasons.append(RefreshReasonCode.STALE_CONTENT)
    elif mode == "edit":
        reasons.append(RefreshReasonCode.INCUMBENT_EDIT)
    else:
        reasons.append(RefreshReasonCode.INCUMBENT_SKIP)
    # Stable unique order
    seen: set[RefreshReasonCode] = set()
    ordered: list[RefreshReasonCode] = []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


class AttentionDecision(BaseModel):
    """Per-artifact attention decision (shadow record; does not actuate)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_key: str = Field(..., min_length=3, max_length=220)
    action: AttentionAction
    proposed_edit_mode: EditMode
    refresh_reasons: list[RefreshReasonCode] = Field(..., min_length=1)

    @field_validator("artifact_key")
    @classmethod
    def _require_colon(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError("artifact_key must be kind:id")
        return value


class AttentionPlan(BaseModel):
    """Immutable attention plan for one run under a pinned ProfileConfig."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: UUID
    schema_version: int = Field(default=1, ge=1)
    planner_mode: PlannerMode
    profile_config_version_id: UUID
    profile_key: str = Field(..., min_length=1, max_length=100)
    is_house_default: bool
    run_date: date
    h4_roster: list[str] = Field(default_factory=list)
    h4_roster_fingerprint: str = Field(..., min_length=64, max_length=64)
    decisions: list[AttentionDecision] = Field(default_factory=list)
    # Explicitly absent: mandate weights, H7 memo, H8 sizing — planner has no authority.

    @field_validator("h4_roster")
    @classmethod
    def _upper_roster(cls, value: list[str]) -> list[str]:
        return [ticker.strip().upper() for ticker in value if ticker and ticker.strip()]

    @model_validator(mode="after")
    def _fingerprint_matches_roster(self) -> AttentionPlan:
        expected = h4_roster_fingerprint(self.h4_roster)
        if self.h4_roster_fingerprint != expected:
            raise ValueError("h4_roster_fingerprint must match h4_roster")
        expected_id = attention_plan_id(
            run_date=self.run_date,
            profile_config_version_id=self.profile_config_version_id,
            roster_fingerprint=self.h4_roster_fingerprint,
            schema_version=self.schema_version,
        )
        if self.plan_id != expected_id:
            raise ValueError("plan_id must be deterministic for pin/roster/run_date")
        if self.is_house_default and self.profile_key != HOUSE_PROFILE_KEY:
            raise ValueError("house AttentionPlan must use profile_key='house'")
        if not self.is_house_default and self.profile_key == HOUSE_PROFILE_KEY:
            raise ValueError("overlay AttentionPlan cannot claim the house profile_key")
        return self


class AttentionPlanShadowResult(BaseModel):
    """Shadow planner output: plan may be present; actuation is always false."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planner_mode: PlannerMode
    plan: AttentionPlan | None = None
    actuated: bool = False
    incumbent_edit_modes: dict[str, EditMode] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _never_actuate(self) -> AttentionPlanShadowResult:
        if self.actuated:
            raise ValueError("AttentionPlan shadow/off must never set actuated=True")
        if self.planner_mode == "off" and self.plan is not None:
            raise ValueError("planner_mode=off must not produce a plan")
        if self.planner_mode == "shadow" and self.plan is None:
            raise ValueError("planner_mode=shadow must produce a plan")
        return self


def resolve_profile_pin_for_planner(
    *,
    requested_version_id: UUID | None,
    store: Mapping[str, ProfileConfig | Mapping[str, object]] | None = None,
) -> ProfileConfig:
    """Pin house by default; overlay requests fail closed when missing."""
    if requested_version_id is None:
        return house_profile_config()
    if store is None:
        raise ProfileConfigMissingError(
            f"overlay profile_config {requested_version_id} requested but no store provided"
        )
    return load_profile_config_by_version_id(store, requested_version_id)


def plan_attention_shadow(
    *,
    run_date: date,
    artifacts: Sequence[ArtifactKey],
    prior_loader: PriorLoader,
    triages: Mapping[ArtifactKey, TriageSignal | None] | None = None,
    force_full_rewrite: bool = False,
    h4_roster: Sequence[str] | None = None,
    planner_mode: PlannerMode = "shadow",
    profile_config_version_id: UUID | None = None,
    profile_store: Mapping[str, ProfileConfig | Mapping[str, object]] | None = None,
) -> AttentionPlanShadowResult:
    """Build a shadow AttentionPlan beside incumbent ``resolve_edit_mode``.

    Never actuates alternate routing. Does not mutate ``h4_roster``. Does not
    emit H7/H8 fields.
    """
    if planner_mode not in ("off", "shadow"):
        raise AttentionPlanError(
            f"unsupported planner_mode {planner_mode!r}; only off|shadow allowed"
        )

    profile = resolve_profile_pin_for_planner(
        requested_version_id=profile_config_version_id,
        store=profile_store,
    )
    roster = list(h4_roster or [])
    roster_fp = h4_roster_fingerprint(roster)
    triage_map = triages or {}

    incumbent: dict[str, EditMode] = {}
    decisions: list[AttentionDecision] = []
    for key in artifacts:
        triage = triage_map.get(key)
        prior = prior_loader.load(key, run_date)
        mode = resolve_edit_mode(
            artifact_key=key,
            run_date=run_date,
            prior_loader=prior_loader,
            triage=triage,
            force_full_rewrite=force_full_rewrite,
        )
        key_str = _artifact_key_str(key)
        incumbent[key_str] = mode
        decisions.append(
            AttentionDecision(
                artifact_key=key_str,
                action=action_for_edit_mode(mode),
                proposed_edit_mode=mode,
                refresh_reasons=reasons_for_edit_mode(
                    mode,
                    triage=triage,
                    force_full_rewrite=force_full_rewrite,
                    had_prior=prior is not None,
                ),
            )
        )

    if planner_mode == "off":
        return AttentionPlanShadowResult(
            planner_mode="off",
            plan=None,
            actuated=False,
            incumbent_edit_modes=incumbent,
        )

    plan = AttentionPlan(
        plan_id=attention_plan_id(
            run_date=run_date,
            profile_config_version_id=profile.version_id,
            roster_fingerprint=roster_fp,
        ),
        planner_mode="shadow",
        profile_config_version_id=profile.version_id,
        profile_key=profile.profile_key,
        is_house_default=profile.is_house_default,
        run_date=run_date,
        h4_roster=roster,
        h4_roster_fingerprint=roster_fp,
        decisions=decisions,
    )
    return AttentionPlanShadowResult(
        planner_mode="shadow",
        plan=plan,
        actuated=False,
        incumbent_edit_modes=incumbent,
    )


def assert_plan_preserves_h4_roster(plan: AttentionPlan, roster: Sequence[str]) -> None:
    """Test/helper: planner output roster must be byte-identical to input."""
    expected = [t.strip().upper() for t in roster if t and t.strip()]
    if plan.h4_roster != expected:
        raise AttentionPlanError("AttentionPlan must not expand, shrink, or reorder H4 roster")
    if plan.h4_roster_fingerprint != h4_roster_fingerprint(expected):
        raise AttentionPlanError("AttentionPlan H4 fingerprint mismatch")


def assert_plan_has_no_h7_h8_authority(plan: AttentionPlan) -> None:
    """Test/helper: plan payload must not carry H7/H8 authority fields."""
    dumped = plan.model_dump()
    forbidden = {
        "mandate",
        "weights",
        "target_weights",
        "h7",
        "h8",
        "pm_direction_memo",
        "allocation",
        "book_change",
    }
    overlap = forbidden.intersection(dumped)
    if overlap:
        raise AttentionPlanError(f"AttentionPlan must not carry H7/H8 fields: {sorted(overlap)}")


# Re-export house pin helper id for tests / callers
__all__ = [
    "AttentionAction",
    "AttentionDecision",
    "AttentionPlan",
    "AttentionPlanError",
    "AttentionPlanShadowResult",
    "PlannerMode",
    "RefreshReasonCode",
    "action_for_edit_mode",
    "assert_plan_has_no_h7_h8_authority",
    "assert_plan_preserves_h4_roster",
    "attention_plan_id",
    "h4_roster_fingerprint",
    "house_profile_config",
    "plan_attention_shadow",
    "profile_config_version_id",
    "reasons_for_edit_mode",
    "resolve_profile_pin_for_planner",
]
