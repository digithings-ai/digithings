"""WP15.1 — strict outcome-learning contracts (#2954).

Frozen Pydantic v2 vocabulary connecting forecast → decision → execution → realized
outcome → learning eligibility. Models only — persistence lands in WP15.2;
assembly in WP15.3; attribution in WP15.4; lesson compiler in WP15.5.

Style mirrors ``research_retrieval.models`` / ``accounting.models``: frozen,
``extra="forbid"``, UTC-only aware datetimes, ``Decimal`` for financial values,
immutable tuples, SHA-256 content identity.

Anti-goals: causal claims from foreign keys alone, fabricated targets/fills for
excluded/no-op episodes, mutable lessons, prose authority, persistence.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from digiquant.portfolio.allocation_hashes import sha256_hex

# Stable UUID5 namespaces — do not change; persisted IDs would diverge.
_EPISODE_VERSION_ID_NS = UUID("d1a0e601-4b8d-5f2a-9c17-3d6e8f0a1b22")
_LESSON_VERSION_ID_NS = UUID("d1a0e602-4b8d-5f2a-9c17-3d6e8f0a1b22")

# Identifiers / short keys. Free-text messages use NonEmptyText (no max_length).
NonEmptyStr: TypeAlias = Annotated[str, Field(min_length=1, max_length=500)]
NonEmptyText: TypeAlias = Annotated[str, Field(min_length=1)]
ContentHash: TypeAlias = Annotated[str, Field(min_length=64, max_length=64)]
FiniteDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
SignedDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
NonNegDec: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
UnitInterval: TypeAlias = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]

# Metrics that imply causal P&L for sizing/timing — require counterfactual replay.
_CAUSAL_PNL_METRICS: frozenset[str] = frozenset(
    {
        "sizing_pnl_usd",
        "timing_pnl_usd",
        "sizing_pnl_bps",
        "timing_pnl_bps",
    }
)


class OutcomeLearningModel(BaseModel):
    """Strict immutable base for every outcome-learning contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EpisodeDisposition(StrEnum):
    """H7-aligned disposition explaining downstream action/fill presence."""

    AUTHORIZED = "authorized"
    EXCLUDED = "excluded"
    REJECTED = "rejected"
    NO_OP = "no_op"


class AttributionComponent(StrEnum):
    """Independent attribution component — never summed without declared order."""

    FORECAST = "forecast"
    SIZING = "sizing"
    TIMING = "timing"
    EXECUTION = "execution"
    RESIDUAL = "residual"


class AttributionMethod(StrEnum):
    """How the observation was produced."""

    OBSERVED = "observed"
    MODEL_ESTIMATE = "model_estimate"
    COUNTERFACTUAL_REPLAY = "counterfactual_replay"
    UNAVAILABLE = "unavailable"


class EvidenceQuality(StrEnum):
    """Closed vocabulary for observation evidence strength."""

    OBSERVED = "observed"
    MODELED = "modeled"
    COUNTERFACTUAL = "counterfactual"
    DESCRIPTIVE = "descriptive"
    UNAVAILABLE = "unavailable"


class UnavailableReason(StrEnum):
    """Why a component or observation is unavailable — never substitute zero."""

    MISSING_FILL_DATA = "missing_fill_data"
    MISSING_REPLAY_ARTIFACT = "missing_replay_artifact"
    MISSING_ACCOUNTING = "missing_accounting"
    UNRECONCILED_ACCOUNTING = "unreconciled_accounting"
    IMMATURE_HORIZON = "immature_horizon"
    LATE_KNOWN_DATA = "late_known_data"
    EXCLUDED_EPISODE = "excluded_episode"
    NO_OP_EPISODE = "no_op_episode"
    REJECTED_EPISODE = "rejected_episode"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    POLICY_NOT_REGISTERED = "policy_not_registered"


class LessonQualityState(StrEnum):
    """Compiler confidence in a structured lesson version."""

    ADEQUATE = "adequate"
    LOW_SAMPLE = "low_sample"
    HIGH_UNCERTAINTY = "high_uncertainty"
    DEGRADED_INPUT = "degraded_input"
    BLOCKED = "blocked"


class OutcomeQualityCode(StrEnum):
    """Typed episode quality issues."""

    UNRECONCILED_ACCOUNTING = "unreconciled_accounting"
    LATE_KNOWN_OUTCOME = "late_known_outcome"
    MISSING_BENCHMARK = "missing_benchmark"
    PARTIAL_FILL = "partial_fill"
    STALE_MARK = "stale_mark"
    ASSEMBLY_BLOCKER = "assembly_blocker"


def _require_utc(value: AwareDatetime, *, field_name: str) -> AwareDatetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _reject_self_supersession(*, self_id: UUID, supersedes_id: UUID | None, label: str) -> None:
    if supersedes_id is not None and supersedes_id == self_id:
        raise ValueError(f"{label} cannot supersede itself")


class OutcomeTemporalContract(OutcomeLearningModel):
    """Temporal contract for episodes, reports, and lessons."""

    effective_at: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    horizon_end: AwareDatetime
    available_at: AwareDatetime
    replay_as_of: AwareDatetime

    @model_validator(mode="after")
    def _validate_temporal(self) -> OutcomeTemporalContract:
        for name in (
            "effective_at",
            "known_at",
            "recorded_at",
            "horizon_end",
            "available_at",
            "replay_as_of",
        ):
            _require_utc(getattr(self, name), field_name=name)
        if self.available_at < self.horizon_end:
            raise ValueError("available_at must be >= horizon_end")
        if self.effective_at > self.horizon_end:
            raise ValueError("effective_at must be <= horizon_end")
        if self.known_at > self.available_at:
            raise ValueError("known_at must be <= available_at")
        if self.effective_at > self.known_at:
            raise ValueError("effective_at must be <= known_at")
        if self.recorded_at < self.known_at:
            raise ValueError("recorded_at must be >= known_at")
        if self.replay_as_of < self.effective_at:
            raise ValueError("replay_as_of must be >= effective_at")
        if self.replay_as_of > self.available_at:
            raise ValueError("replay_as_of must be <= available_at")
        return self


class H8TargetLineage(OutcomeLearningModel):
    """Requested vs approved H8 targets with reason-coded adjustments."""

    requested_weight: UnitInterval | None = None
    approved_weight: UnitInterval | None = None
    adjustment_codes: tuple[NonEmptyStr, ...] = ()


class H9ExecutionLinks(OutcomeLearningModel):
    """Lineage into the action/fill ledger when execution occurred."""

    action_id: UUID
    order_id: UUID | None = None
    fill_ids: tuple[UUID, ...] = ()
    holding_id: UUID | None = None


class RealizedReturnObservation(OutcomeLearningModel):
    """Authoritative realized returns — never inferred from links alone."""

    instrument_return: SignedDec
    benchmark_return: SignedDec | None = None
    active_return: SignedDec | None = None
    accounting_period_id: UUID
    contribution_id: UUID


class ComponentEligibility(OutcomeLearningModel):
    """Per-component learning eligibility for one episode."""

    component: AttributionComponent
    eligible: bool
    unavailable_reason: UnavailableReason | None = None

    @model_validator(mode="after")
    def _validate_eligibility(self) -> ComponentEligibility:
        if not self.eligible and self.unavailable_reason is None:
            raise ValueError("ineligible component requires unavailable_reason")
        if self.eligible and self.unavailable_reason is not None:
            raise ValueError("eligible component must not carry unavailable_reason")
        return self


class OutcomeQualityIssue(OutcomeLearningModel):
    """Typed quality flag on an episode."""

    code: OutcomeQualityCode
    message: NonEmptyText


class OutcomeEpisode(OutcomeLearningModel):
    """Immutable outcome episode for one matured typed forecast."""

    schema_version: int = 1
    episode_key: NonEmptyStr
    episode_version_id: UUID
    content_hash: ContentHash
    supersedes_version_id: UUID | None = None

    forecast_id: UUID
    outcome_id: UUID
    mandate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    horizon_id: NonEmptyStr
    source_run_id: NonEmptyStr

    evidence_bundle_id: UUID | None = None
    research_state_version_id: UUID | None = None
    context_manifest_id: UUID | None = None
    policy_version_id: NonEmptyStr | None = None

    disposition: EpisodeDisposition
    temporal: OutcomeTemporalContract

    h8_lineage: H8TargetLineage | None = None
    h9_links: H9ExecutionLinks | None = None
    realized: RealizedReturnObservation | None = None

    expected_cost_id: UUID | None = None
    realized_cost_id: UUID | None = None
    pre_trade_risk_report_id: UUID | None = None

    component_eligibility: tuple[ComponentEligibility, ...] = ()
    quality_issues: tuple[OutcomeQualityIssue, ...] = ()

    @field_validator("component_eligibility", "quality_issues", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_episode(self) -> OutcomeEpisode:
        expected_hash = episode_content_hash(
            episode_key=self.episode_key,
            forecast_id=self.forecast_id,
            outcome_id=self.outcome_id,
            mandate_id=self.mandate_id,
            instrument_id=self.instrument_id,
            horizon_id=self.horizon_id,
            source_run_id=self.source_run_id,
            disposition=self.disposition,
            temporal=self.temporal,
            realized=self.realized,
            h8_lineage=self.h8_lineage,
            h9_links=self.h9_links,
            evidence_bundle_id=self.evidence_bundle_id,
            research_state_version_id=self.research_state_version_id,
            context_manifest_id=self.context_manifest_id,
            policy_version_id=self.policy_version_id,
            expected_cost_id=self.expected_cost_id,
            realized_cost_id=self.realized_cost_id,
            pre_trade_risk_report_id=self.pre_trade_risk_report_id,
            component_eligibility=self.component_eligibility,
            quality_issues=self.quality_issues,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical OutcomeEpisode digest")
        expected_version_id = episode_version_id(
            episode_key=self.episode_key,
            content_hash=self.content_hash,
            supersedes_version_id=self.supersedes_version_id,
        )
        if self.episode_version_id != expected_version_id:
            raise ValueError("episode_version_id must match canonical UUID5 identity")
        _reject_self_supersession(
            self_id=self.episode_version_id,
            supersedes_id=self.supersedes_version_id,
            label="episode_version_id",
        )
        if self.disposition == EpisodeDisposition.AUTHORIZED:
            if self.h9_links is None:
                raise ValueError("authorized disposition requires h9_links")
            if self.realized is None:
                raise ValueError("authorized disposition requires realized returns")
        if self.disposition in (EpisodeDisposition.EXCLUDED, EpisodeDisposition.NO_OP):
            if self.h9_links is not None:
                raise ValueError(f"{self.disposition.value} disposition forbids h9_links")
            if self.realized is not None:
                raise ValueError(
                    f"{self.disposition.value} disposition forbids fabricated realized"
                )
        if self.disposition == EpisodeDisposition.REJECTED:
            if self.h9_links is not None:
                raise ValueError("rejected disposition forbids h9_links")
            if self.realized is not None:
                raise ValueError("rejected disposition forbids fabricated realized")
        return self


class ComponentObservation(OutcomeLearningModel):
    """One typed component attribution observation."""

    component: AttributionComponent
    metric: NonEmptyStr
    value: SignedDec | None = None
    unit: NonEmptyStr = "unitless"
    uncertainty: NonNegDec | None = None
    baseline: NonEmptyStr | None = None
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    artifact_ids: tuple[UUID, ...] = ()
    evidence_quality: EvidenceQuality
    method: AttributionMethod
    unavailable_reason: UnavailableReason | None = None
    replay_artifact_id: UUID | None = None

    @field_validator("artifact_ids", mode="before")
    @classmethod
    def _coerce_artifact_ids(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_observation(self) -> ComponentObservation:
        if self.method == AttributionMethod.UNAVAILABLE:
            if self.unavailable_reason is None:
                raise ValueError("unavailable method requires unavailable_reason")
            if self.value is not None:
                raise ValueError("unavailable observation must not carry value")
        else:
            if self.value is None:
                raise ValueError(f"{self.method.value} observation requires value")
            if self.unavailable_reason is not None:
                raise ValueError("available observation must not carry unavailable_reason")

        if self.method == AttributionMethod.COUNTERFACTUAL_REPLAY:
            if self.replay_artifact_id is None:
                raise ValueError("counterfactual_replay requires replay_artifact_id")

        if self.metric in _CAUSAL_PNL_METRICS and self.method not in (
            AttributionMethod.COUNTERFACTUAL_REPLAY,
            AttributionMethod.UNAVAILABLE,
        ):
            raise ValueError(
                f"causal P&L metric {self.metric!r} requires counterfactual_replay with replay artifact"
            )

        for name in ("interval_start", "interval_end"):
            ts = getattr(self, name)
            if ts is not None:
                _require_utc(ts, field_name=name)
        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_start > self.interval_end
        ):
            raise ValueError("interval_start must be <= interval_end")
        return self


class ComponentAttributionReport(OutcomeLearningModel):
    """Independent typed component observations for one episode version."""

    schema_version: int = 1
    report_id: UUID
    episode_version_id: UUID
    observations: tuple[ComponentObservation, ...]

    @field_validator("observations", mode="before")
    @classmethod
    def _coerce_observations(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_report(self) -> ComponentAttributionReport:
        if not self.observations:
            raise ValueError("report requires at least one observation")
        return self


class OutcomeLessonVersion(OutcomeLearningModel):
    """Immutable structured lesson compiled from eligible episodes/reports."""

    schema_version: int = 1
    lesson_version_id: UUID
    content_hash: ContentHash
    supersedes_version_id: UUID | None = None

    compilation_policy_id: NonEmptyStr
    compilation_cutoff: AwareDatetime

    episode_version_ids: tuple[UUID, ...]
    report_ids: tuple[UUID, ...]

    cohort: NonEmptyStr
    regime: NonEmptyStr | None = None
    horizon_id: NonEmptyStr
    component: AttributionComponent

    sample_count: Annotated[int, Field(ge=0)]
    effective_sample_count: Annotated[int, Field(ge=0)]
    estimate: SignedDec
    uncertainty: NonNegDec
    prior: SignedDec | None = None
    shrinkage: UnitInterval | None = None

    quality_state: LessonQualityState
    recommendation_code: NonEmptyStr | None = None
    warning_codes: tuple[NonEmptyStr, ...] = ()

    available_at: AwareDatetime

    @field_validator("episode_version_ids", "report_ids", "warning_codes", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_lesson(self) -> OutcomeLessonVersion:
        _require_utc(self.compilation_cutoff, field_name="compilation_cutoff")
        _require_utc(self.available_at, field_name="available_at")
        expected_hash = lesson_content_hash(
            compilation_policy_id=self.compilation_policy_id,
            compilation_cutoff=self.compilation_cutoff,
            episode_version_ids=self.episode_version_ids,
            report_ids=self.report_ids,
            component=self.component,
            estimate=self.estimate,
            uncertainty=self.uncertainty,
            sample_count=self.sample_count,
            effective_sample_count=self.effective_sample_count,
            quality_state=self.quality_state,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical OutcomeLessonVersion digest")
        expected_version_id = lesson_version_id(
            compilation_policy_id=self.compilation_policy_id,
            content_hash=self.content_hash,
            supersedes_version_id=self.supersedes_version_id,
        )
        if self.lesson_version_id != expected_version_id:
            raise ValueError("lesson_version_id must match canonical UUID5 identity")
        _reject_self_supersession(
            self_id=self.lesson_version_id,
            supersedes_id=self.supersedes_version_id,
            label="lesson_version_id",
        )
        if not self.episode_version_ids:
            raise ValueError("lesson requires episode_version_ids")
        if self.effective_sample_count > self.sample_count:
            raise ValueError("effective_sample_count cannot exceed sample_count")
        if self.available_at < self.compilation_cutoff:
            raise ValueError("available_at must be >= compilation_cutoff")
        return self


def episode_content_hash(
    *,
    episode_key: str,
    forecast_id: UUID,
    outcome_id: UUID,
    mandate_id: str,
    instrument_id: str,
    horizon_id: str,
    source_run_id: str,
    disposition: EpisodeDisposition,
    temporal: OutcomeTemporalContract,
    realized: RealizedReturnObservation | None,
    h8_lineage: H8TargetLineage | None,
    h9_links: H9ExecutionLinks | None,
    evidence_bundle_id: UUID | None = None,
    research_state_version_id: UUID | None = None,
    context_manifest_id: UUID | None = None,
    policy_version_id: str | None = None,
    expected_cost_id: UUID | None = None,
    realized_cost_id: UUID | None = None,
    pre_trade_risk_report_id: UUID | None = None,
    component_eligibility: tuple[ComponentEligibility, ...] = (),
    quality_issues: tuple[OutcomeQualityIssue, ...] = (),
) -> str:
    """Stable digest of materially significant episode fields."""
    payload = {
        "episode_key": episode_key,
        "forecast_id": str(forecast_id),
        "outcome_id": str(outcome_id),
        "mandate_id": mandate_id,
        "instrument_id": instrument_id,
        "horizon_id": horizon_id,
        "source_run_id": source_run_id,
        "disposition": disposition.value,
        "temporal": temporal.model_dump(mode="json"),
        "realized": realized.model_dump(mode="json") if realized else None,
        "h8_lineage": h8_lineage.model_dump(mode="json") if h8_lineage else None,
        "h9_links": h9_links.model_dump(mode="json") if h9_links else None,
        "evidence_bundle_id": str(evidence_bundle_id) if evidence_bundle_id else None,
        "research_state_version_id": (
            str(research_state_version_id) if research_state_version_id else None
        ),
        "context_manifest_id": str(context_manifest_id) if context_manifest_id else None,
        "policy_version_id": policy_version_id,
        "expected_cost_id": str(expected_cost_id) if expected_cost_id else None,
        "realized_cost_id": str(realized_cost_id) if realized_cost_id else None,
        "pre_trade_risk_report_id": (
            str(pre_trade_risk_report_id) if pre_trade_risk_report_id else None
        ),
        "component_eligibility": [e.model_dump(mode="json") for e in component_eligibility],
        "quality_issues": [q.model_dump(mode="json") for q in quality_issues],
    }
    return sha256_hex(payload)


def episode_version_id(
    *,
    episode_key: str,
    content_hash: str,
    supersedes_version_id: UUID | None,
) -> UUID:
    """Deterministic version ID from logical key and content."""
    seed = _canonical_json(
        {
            "episode_key": episode_key,
            "content_hash": content_hash,
            "supersedes_version_id": str(supersedes_version_id) if supersedes_version_id else None,
        }
    )
    return uuid5(_EPISODE_VERSION_ID_NS, seed)


def lesson_content_hash(
    *,
    compilation_policy_id: str,
    compilation_cutoff: AwareDatetime,
    episode_version_ids: tuple[UUID, ...],
    report_ids: tuple[UUID, ...],
    component: AttributionComponent,
    estimate: Decimal,
    uncertainty: Decimal,
    sample_count: int,
    effective_sample_count: int,
    quality_state: LessonQualityState,
) -> str:
    """Stable digest of materially significant lesson fields."""
    payload = {
        "compilation_policy_id": compilation_policy_id,
        "compilation_cutoff": compilation_cutoff.isoformat(),
        "episode_version_ids": sorted(str(v) for v in episode_version_ids),
        "report_ids": sorted(str(v) for v in report_ids),
        "component": component.value,
        "estimate": str(estimate),
        "uncertainty": str(uncertainty),
        "sample_count": sample_count,
        "effective_sample_count": effective_sample_count,
        "quality_state": quality_state.value,
    }
    return sha256_hex(payload)


def lesson_version_id(
    *,
    compilation_policy_id: str,
    content_hash: str,
    supersedes_version_id: UUID | None,
) -> UUID:
    """Deterministic lesson version ID."""
    seed = _canonical_json(
        {
            "compilation_policy_id": compilation_policy_id,
            "content_hash": content_hash,
            "supersedes_version_id": str(supersedes_version_id) if supersedes_version_id else None,
        }
    )
    return uuid5(_LESSON_VERSION_ID_NS, seed)


__all__ = [
    "AttributionComponent",
    "AttributionMethod",
    "ComponentAttributionReport",
    "ComponentEligibility",
    "ComponentObservation",
    "EpisodeDisposition",
    "EvidenceQuality",
    "H8TargetLineage",
    "H9ExecutionLinks",
    "LessonQualityState",
    "OutcomeEpisode",
    "OutcomeLessonVersion",
    "OutcomeLearningModel",
    "OutcomeQualityCode",
    "OutcomeQualityIssue",
    "OutcomeTemporalContract",
    "RealizedReturnObservation",
    "UnavailableReason",
    "episode_content_hash",
    "episode_version_id",
    "lesson_content_hash",
    "lesson_version_id",
]
