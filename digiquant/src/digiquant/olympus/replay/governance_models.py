"""WP16.2 — minimal governance persistence contracts (#2983).

Store-ready frozen models for replay evidence, gate criteria, evaluations, and
human decisions. WP16.6 owns the rich comparison builder in ``comparison.py``;
this module keeps the thin persistence envelope consumed by ``PolicyReplayStore``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.temporal import require_utc_datetime

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
HashHex64: TypeAlias = Annotated[str, Field(min_length=64, max_length=64)]


class GovernanceContractModel(BaseModel):
    """Strict immutable base for replay governance persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplayRunEventKind(StrEnum):
    """Append-only lifecycle markers — status is derived, never updated in place."""

    RUN_STARTED = "run_started"
    ARM_DISPATCHED = "arm_dispatched"
    ARM_COMPLETED = "arm_completed"
    RUN_FAILED = "run_failed"
    RUN_COMPLETED = "run_completed"


class ReplayRunEvent(GovernanceContractModel):
    """One immutable replay-run lifecycle event."""

    event_id: UUID
    run_id: NonEmptyId
    pair_id: NonEmptyId
    event_kind: ReplayRunEventKind
    sequence: int = Field(ge=0)
    recorded_at: datetime
    detail: str = ""

    @field_validator("recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


class PolicyComparisonReport(GovernanceContractModel):
    """Paired policy comparison persistence envelope (rich report: comparison.py)."""

    comparison_id: UUID
    pair_content_hash: HashHex64
    shared_manifest_content_hash: HashHex64
    report_content_hash: HashHex64
    recorded_at: datetime
    status: NonEmptyId
    metric_groups_present: tuple[str, ...] = ()

    @field_validator("recorded_at")
    @classmethod
    def _require_recorded_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


class GateCriteriaVersion(GovernanceContractModel):
    """Immutable human-authored gate criteria version."""

    criteria_version_id: UUID
    criteria_key: NonEmptyId
    content_hash: HashHex64
    effective_at: datetime
    recorded_at: datetime
    author: NonEmptyId
    rationale: str
    supersedes_version_id: UUID | None = None

    @field_validator("effective_at", "recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime, info) -> datetime:
        return require_utc_datetime(value, field_name=str(info.field_name))


class GateEvaluation(GovernanceContractModel):
    """Immutable gate evaluation against one comparison and criteria version."""

    evaluation_id: UUID
    comparison_id: UUID
    criteria_version_id: UUID
    evaluation_content_hash: HashHex64
    recorded_at: datetime
    eligible_for_human_review: bool
    blockers: tuple[str, ...] = ()

    @field_validator("recorded_at")
    @classmethod
    def _require_recorded_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


class GovernanceDecisionKind(StrEnum):
    """Human governance decision — never activates production policy."""

    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"
    ROLLBACK_REVIEW = "rollback_review"


class PolicyGovernanceDecision(GovernanceContractModel):
    """Immutable authenticated human decision record."""

    decision_id: UUID
    evaluation_id: UUID
    decision_kind: GovernanceDecisionKind
    actor_principal: NonEmptyId
    rationale: str
    decision_content_hash: HashHex64
    recorded_at: datetime
    supersedes_decision_id: UUID | None = None

    @field_validator("recorded_at")
    @classmethod
    def _require_recorded_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


def governance_content_hash(model: GovernanceContractModel) -> str:
    """Stable SHA-256 digest excluding any self-referential hash field."""
    payload = model.model_dump(mode="json")
    for key in (
        "content_hash",
        "report_content_hash",
        "evaluation_content_hash",
        "decision_content_hash",
    ):
        payload.pop(key, None)
    return sha256_hex(payload)


__all__ = [
    "GateCriteriaVersion",
    "GateEvaluation",
    "GovernanceContractModel",
    "GovernanceDecisionKind",
    "PolicyComparisonReport",
    "PolicyGovernanceDecision",
    "ReplayRunEvent",
    "ReplayRunEventKind",
    "governance_content_hash",
]
