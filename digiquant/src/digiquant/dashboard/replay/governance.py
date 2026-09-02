"""WP16.7 / WP16.8 — gate evaluation and authenticated human decisions.

Machine output is eligibility for human review only — never promotion,
activation, or production config mutation. Criteria must be authored outside
this module; the evaluator only applies a pre-versioned package.

WP16.8 records approve/reject/defer/rollback-review decisions from an
``AuthenticatedPrincipal`` (trusted identity). Activation remains external.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.dashboard.replay.comparison import (
    EvidenceMode,
    MetricAvailability,
    MetricDirection,
    PolicyComparisonReport,
)
from digiquant.dashboard.replay.governance_models import (
    GateCriteriaVersion,
    GateEvaluation,
    GovernanceDecisionKind,
    PolicyGovernanceDecision,
    governance_content_hash,
)
from digiquant.dashboard.replay.store import PolicyReplayStore
from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.portfolio.allocation_hashes import sha256_hex

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
HashHex64: TypeAlias = Annotated[str, Field(min_length=64, max_length=64)]
FiniteDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]


class GovernanceModel(BaseModel):
    """Strict immutable base for gate evaluation contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GateKind(StrEnum):
    """Human gate family — rollback is evaluated separately from promotion."""

    ACCOUNTING = "accounting"
    SIGNAL = "signal"
    SHADOW = "shadow"
    PROMOTION = "promotion"
    ROLLBACK = "rollback"


class MetricComparisonKind(StrEnum):
    """Which leaf value a criterion compares against its threshold."""

    ABSOLUTE_INCUMBENT = "absolute_incumbent"
    ABSOLUTE_CHALLENGER = "absolute_challenger"
    PAIRED_DELTA = "paired_delta"


class MissingDataRule(StrEnum):
    """How missing/unavailable metrics affect a criterion."""

    FAIL_CLOSED = "fail_closed"


class ConfidenceBoundRule(StrEnum):
    """Confidence / availability bound required on the metric leaf."""

    NONE = "none"
    REQUIRE_AVAILABLE = "require_available"


class CriterionOutcome(StrEnum):
    """Per-criterion evaluation outcome."""

    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT = "insufficient"


_PROMOTION_KINDS = frozenset(
    {
        GateKind.ACCOUNTING,
        GateKind.SIGNAL,
        GateKind.SHADOW,
        GateKind.PROMOTION,
    }
)


class GateCriterion(GovernanceModel):
    """One immutable human-authored rule inside a criteria package."""

    criterion_id: NonEmptyId
    gate_kind: GateKind
    metric_name: NonEmptyId
    cohort: NonEmptyId = "all"
    comparison_kind: MetricComparisonKind
    direction: MetricDirection
    threshold: FiniteDec
    evidence_mode: EvidenceMode
    min_sample_count: Annotated[int, Field(ge=0)] = 0
    min_folds: Annotated[int, Field(ge=0)] = 0
    min_duration_days: Annotated[int, Field(ge=0)] = 0
    missing_data_rule: MissingDataRule = MissingDataRule.FAIL_CLOSED
    confidence_bound_rule: ConfidenceBoundRule = ConfidenceBoundRule.REQUIRE_AVAILABLE


class HumanAuthoredGateCriteria(GovernanceModel):
    """Pre-versioned criteria package — never minted by the evaluator."""

    schema_version: str = "1.0"
    criteria_key: NonEmptyId
    criteria_version_id: UUID
    author: NonEmptyId
    rationale: NonEmptyId
    effective_at: datetime
    recorded_at: datetime
    content_hash: HashHex64
    criteria: tuple[GateCriterion, ...] = ()
    require_identical_manifest: bool = True
    require_eligible_comparison: bool = True
    reject_accounting_breach: bool = True
    reject_hard_constraint_breach: bool = True
    supersedes_version_id: UUID | None = None

    @field_validator("criteria", mode="before")
    @classmethod
    def _coerce_criteria(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("effective_at", "recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return require_utc_datetime(value, field_name=str(field_name))

    @model_validator(mode="after")
    def _validate_hash(self) -> HumanAuthoredGateCriteria:
        expected = gate_criteria_content_hash(self)
        if self.content_hash != expected:
            raise ValueError("content_hash must match canonical digest")
        return self


class CriterionEvaluationResult(GovernanceModel):
    """One per-criterion outcome with an explicit reason."""

    criterion_id: NonEmptyId
    gate_kind: GateKind
    outcome: CriterionOutcome
    reason: NonEmptyId
    observed_value: FiniteDec | None = None
    metric_provenance: NonEmptyId | None = None


class GateEvaluationDetail(GovernanceModel):
    """Rich gate evaluation — projects into the WP16.2 ``GateEvaluation`` row."""

    evaluation_id: UUID
    comparison_id: UUID
    criteria_version_id: UUID
    criteria_content_hash: HashHex64
    report_content_hash: HashHex64
    recorded_at: datetime
    eligible_for_human_review: bool
    rollback_eligible_for_human_review: bool
    criterion_results: tuple[CriterionEvaluationResult, ...] = ()
    blockers: tuple[str, ...] = ()
    evaluation_content_hash: HashHex64

    @field_validator("criterion_results", "blockers", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("recorded_at")
    @classmethod
    def _require_recorded_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")

    @model_validator(mode="after")
    def _validate_hash(self) -> GateEvaluationDetail:
        expected = gate_evaluation_content_hash(self)
        if self.evaluation_content_hash != expected:
            raise ValueError("evaluation_content_hash must match canonical digest")
        return self


def gate_criteria_content_hash(criteria: HumanAuthoredGateCriteria) -> str:
    """Stable SHA-256 of criteria fields excluding the self-hash."""
    payload = {
        "schema_version": criteria.schema_version,
        "criteria_key": criteria.criteria_key,
        "criteria_version_id": str(criteria.criteria_version_id),
        "author": criteria.author,
        "rationale": criteria.rationale,
        "effective_at": criteria.effective_at.isoformat(),
        "recorded_at": criteria.recorded_at.isoformat(),
        "criteria": [c.model_dump(mode="json") for c in criteria.criteria],
        "require_identical_manifest": criteria.require_identical_manifest,
        "require_eligible_comparison": criteria.require_eligible_comparison,
        "reject_accounting_breach": criteria.reject_accounting_breach,
        "reject_hard_constraint_breach": criteria.reject_hard_constraint_breach,
        "supersedes_version_id": (
            None if criteria.supersedes_version_id is None else str(criteria.supersedes_version_id)
        ),
    }
    return sha256_hex(payload)


def gate_evaluation_content_hash(detail: GateEvaluationDetail) -> str:
    """Stable SHA-256 of evaluation fields excluding the self-hash."""
    payload = {
        "evaluation_id": str(detail.evaluation_id),
        "comparison_id": str(detail.comparison_id),
        "criteria_version_id": str(detail.criteria_version_id),
        "criteria_content_hash": detail.criteria_content_hash,
        "report_content_hash": detail.report_content_hash,
        "recorded_at": detail.recorded_at.isoformat(),
        "eligible_for_human_review": detail.eligible_for_human_review,
        "rollback_eligible_for_human_review": detail.rollback_eligible_for_human_review,
        "criterion_results": [r.model_dump(mode="json") for r in detail.criterion_results],
        "blockers": list(detail.blockers),
    }
    return sha256_hex(payload)


def to_store_criteria_version(criteria: HumanAuthoredGateCriteria) -> GateCriteriaVersion:
    """Project a rich criteria package into the WP16.2 persistence envelope."""
    return GateCriteriaVersion(
        criteria_version_id=criteria.criteria_version_id,
        criteria_key=criteria.criteria_key,
        content_hash=criteria.content_hash,
        effective_at=criteria.effective_at,
        recorded_at=criteria.recorded_at,
        author=criteria.author,
        rationale=criteria.rationale,
        supersedes_version_id=criteria.supersedes_version_id,
    )


def to_store_evaluation(detail: GateEvaluationDetail) -> GateEvaluation:
    """Project a rich evaluation into the WP16.2 ``GateEvaluation`` row."""
    return GateEvaluation(
        evaluation_id=detail.evaluation_id,
        comparison_id=detail.comparison_id,
        criteria_version_id=detail.criteria_version_id,
        evaluation_content_hash=detail.evaluation_content_hash,
        recorded_at=detail.recorded_at,
        eligible_for_human_review=detail.eligible_for_human_review,
        blockers=detail.blockers,
    )


def persist_gate_evaluation(
    store: PolicyReplayStore,
    *,
    criteria: HumanAuthoredGateCriteria,
    report: PolicyComparisonReport,
    detail: GateEvaluationDetail,
) -> GateEvaluation:
    """Append criteria + comparison envelope + evaluation (no config write)."""
    store.append_criteria(to_store_criteria_version(criteria))
    store.append_comparison(report.to_governance_envelope())
    return store.append_evaluation(to_store_evaluation(detail))


def evaluate_gate_criteria(
    *,
    criteria: HumanAuthoredGateCriteria,
    report: PolicyComparisonReport,
    recorded_at: datetime,
    evaluation_id: UUID | None = None,
    config_root: Path | str | None = None,
) -> GateEvaluationDetail:
    """Apply pre-versioned criteria to a comparison report.

    Returns eligibility for human review only. Never authors criteria, never
    promotes, never writes production config (``config_root`` is accepted solely
    so callers can assert the evaluator leaves the filesystem untouched).
    """
    _ = config_root  # intentionally unused — proves no config side effect
    expected = gate_criteria_content_hash(criteria)
    if criteria.content_hash != expected:
        raise ValueError("content_hash must match canonical digest")

    stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
    blockers: list[str] = []

    if not criteria.criteria:
        blockers.append("no_criteria")

    if criteria.require_identical_manifest:
        if not report.shared_manifest_content_hash:
            blockers.append("manifest_missing")
        elif len(report.shared_manifest_content_hash) != 64:
            blockers.append("manifest_invalid")

    if criteria.reject_accounting_breach and report.accounting_breach_visible:
        blockers.append("accounting_breach_visible")

    if criteria.reject_hard_constraint_breach and report.hard_constraint_breach_visible:
        blockers.append("hard_constraint_breach_visible")

    if criteria.require_eligible_comparison and not report.eligible_for_governance:
        blockers.append("comparison_not_eligible_for_governance")

    fold_count = len(report.folds)
    results = tuple(
        _evaluate_one_criterion(criterion, report=report, fold_count=fold_count)
        for criterion in criteria.criteria
    )

    promo_results = tuple(r for r in results if r.gate_kind in _PROMOTION_KINDS)
    rollback_results = tuple(r for r in results if r.gate_kind is GateKind.ROLLBACK)

    promo_ok = (
        not blockers
        and bool(promo_results)
        and all(r.outcome is CriterionOutcome.PASSED for r in promo_results)
    )
    # Empty promotion set with only rollback criteria → not promotion-eligible.
    if not promo_results and criteria.criteria and not blockers:
        blockers.append("no_promotion_criteria")
        promo_ok = False

    for row in promo_results:
        if row.outcome is not CriterionOutcome.PASSED:
            blockers.append(f"criterion:{row.criterion_id}:{row.outcome.value}")

    rollback_ok = bool(rollback_results) and all(
        r.outcome is CriterionOutcome.PASSED for r in rollback_results
    )

    eval_id = evaluation_id or uuid4()
    draft = GateEvaluationDetail.model_construct(
        evaluation_id=eval_id,
        comparison_id=report.comparison_id,
        criteria_version_id=criteria.criteria_version_id,
        criteria_content_hash=criteria.content_hash,
        report_content_hash=report.report_content_hash,
        recorded_at=stamp,
        eligible_for_human_review=promo_ok,
        rollback_eligible_for_human_review=rollback_ok,
        criterion_results=results,
        blockers=tuple(dict.fromkeys(blockers)),
        evaluation_content_hash="0" * 64,
    )
    digest = gate_evaluation_content_hash(draft)
    return GateEvaluationDetail.model_validate(
        {**draft.model_dump(mode="python"), "evaluation_content_hash": digest}
    )


def _evaluate_one_criterion(
    criterion: GateCriterion,
    *,
    report: PolicyComparisonReport,
    fold_count: int,
) -> CriterionEvaluationResult:
    metric = _find_metric(report, criterion.metric_name)
    if metric is None:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=f"missing_metric:{criterion.metric_name}",
        )

    if fold_count < criterion.min_folds:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=f"min_folds:{fold_count}<{criterion.min_folds}",
            metric_provenance=metric.provenance,
        )

    if metric.sample_count < criterion.min_sample_count:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=(f"min_sample_count:{metric.sample_count}<{criterion.min_sample_count}"),
            metric_provenance=metric.provenance,
        )

    if criterion.min_duration_days > 0 and fold_count < 1:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=f"min_duration_days:{criterion.min_duration_days}",
            metric_provenance=metric.provenance,
        )

    if (
        criterion.confidence_bound_rule is ConfidenceBoundRule.REQUIRE_AVAILABLE
        and metric.availability is not MetricAvailability.AVAILABLE
    ):
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=f"metric_not_available:{metric.availability.value}",
            metric_provenance=metric.provenance,
        )

    if metric.availability is not MetricAvailability.AVAILABLE:
        if criterion.missing_data_rule is MissingDataRule.FAIL_CLOSED:
            return CriterionEvaluationResult(
                criterion_id=criterion.criterion_id,
                gate_kind=criterion.gate_kind,
                outcome=CriterionOutcome.INSUFFICIENT,
                reason=f"missing_data:{metric.unavailable_reason or metric.availability.value}",
                metric_provenance=metric.provenance,
            )

    if metric.evidence_mode is not criterion.evidence_mode:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=(
                f"evidence_mode_mismatch:got={metric.evidence_mode.value}"
                f":want={criterion.evidence_mode.value}"
            ),
            metric_provenance=metric.provenance,
        )

    observed = _observed_value(metric, criterion.comparison_kind)
    if observed is None:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.INSUFFICIENT,
            reason=f"missing_value:{criterion.comparison_kind.value}",
            metric_provenance=metric.provenance,
        )

    passed = _threshold_met(
        observed=observed,
        threshold=criterion.threshold,
        direction=criterion.direction,
        comparison_kind=criterion.comparison_kind,
    )
    if passed:
        return CriterionEvaluationResult(
            criterion_id=criterion.criterion_id,
            gate_kind=criterion.gate_kind,
            outcome=CriterionOutcome.PASSED,
            reason="threshold_met",
            observed_value=observed,
            metric_provenance=metric.provenance,
        )
    return CriterionEvaluationResult(
        criterion_id=criterion.criterion_id,
        gate_kind=criterion.gate_kind,
        outcome=CriterionOutcome.FAILED,
        reason=(
            f"threshold_not_met:observed={observed}:threshold={criterion.threshold}"
            f":direction={criterion.direction.value}"
        ),
        observed_value=observed,
        metric_provenance=metric.provenance,
    )


def _find_metric(report: PolicyComparisonReport, metric_name: str):
    for group in report.metric_groups:
        for metric in group.metrics:
            if metric.name == metric_name:
                return metric
    return None


def _observed_value(metric, comparison_kind: MetricComparisonKind) -> Decimal | None:
    if comparison_kind is MetricComparisonKind.ABSOLUTE_INCUMBENT:
        return metric.absolute_incumbent
    if comparison_kind is MetricComparisonKind.ABSOLUTE_CHALLENGER:
        return metric.absolute_challenger
    return metric.delta


def _threshold_met(
    *,
    observed: Decimal,
    threshold: Decimal,
    direction: MetricDirection,
    comparison_kind: MetricComparisonKind,
) -> bool:
    """Interpret threshold relative to metric direction.

    For paired deltas and absolute leaves:
    - ``higher_is_better``: observed >= threshold
    - ``lower_is_better``: observed <= threshold
    - ``neutral``: abs(observed) <= abs(threshold) when threshold is a bound
      on magnitude; otherwise observed == threshold is not required — treat as
      ``observed <= threshold`` for an upper magnitude guard.
    """
    _ = comparison_kind
    if direction is MetricDirection.HIGHER_IS_BETTER:
        return observed >= threshold
    if direction is MetricDirection.LOWER_IS_BETTER:
        return observed <= threshold
    return abs(observed) <= abs(threshold)


class GovernanceDecisionError(ValueError):
    """Human decision recording refused (eligibility, identity, or contract)."""


class AuthenticatedPrincipal(GovernanceModel):
    """Trusted operator identity — construct only at authenticated boundaries.

    Digiquant already receives verified JWT claims via digikey's
    ``DigiAuthMiddleware`` (``request.state.digi_auth``). Use
    :meth:`from_digi_auth` at that boundary. Do not invent caller-supplied
    actor strings. No digikey source changes are required for this VO.
    """

    subject: NonEmptyId
    principal_kind: NonEmptyId = "api_key"

    @classmethod
    def from_digi_auth(cls, auth: object) -> AuthenticatedPrincipal:
        """Build from ``DigiAuthContext`` / ``request.state.digi_auth``."""
        subject = str(getattr(auth, "subject", "") or "").strip()
        if not subject:
            raise GovernanceDecisionError("authenticated principal subject required")
        kind = str(getattr(auth, "principal_kind", "") or "").strip() or "api_key"
        return cls(subject=subject, principal_kind=kind)


def record_policy_governance_decision(
    store: PolicyReplayStore,
    *,
    principal: AuthenticatedPrincipal,
    evaluation_id: UUID,
    decision_kind: GovernanceDecisionKind,
    rationale: str,
    recorded_at: datetime,
    current_policy_version_id: str | None = None,
    supersedes_decision_id: UUID | None = None,
    decision_id: UUID | None = None,
) -> PolicyGovernanceDecision:
    """Append an authenticated human governance decision (no activation).

    Identity is taken only from ``principal.subject``. There is no
    ``actor`` / ``actor_principal`` parameter — MCP and unauthenticated
    callers cannot impersonate. Approval requires a stored evaluation with
    ``eligible_for_human_review=True``. Reject/defer need a non-empty
    rationale. Rollback-review must link ``current_policy_version_id``.
    """
    if not isinstance(principal, AuthenticatedPrincipal):
        raise GovernanceDecisionError("principal must be AuthenticatedPrincipal")

    reason = (rationale or "").strip()
    if not reason:
        raise GovernanceDecisionError("rationale is required")

    evaluation = store.get_evaluation(evaluation_id)
    if evaluation is None:
        raise GovernanceDecisionError(f"evaluation_id {evaluation_id} not found")

    if decision_kind is GovernanceDecisionKind.APPROVE:
        if not evaluation.eligible_for_human_review:
            raise GovernanceDecisionError("approve requires evaluation.eligible_for_human_review")

    version_id: str | None = None
    if current_policy_version_id is not None:
        version_id = current_policy_version_id.strip() or None

    if decision_kind is GovernanceDecisionKind.ROLLBACK_REVIEW:
        if not version_id:
            raise GovernanceDecisionError("rollback_review requires current_policy_version_id")

    stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
    did = decision_id or uuid4()
    draft = PolicyGovernanceDecision.model_construct(
        decision_id=did,
        evaluation_id=evaluation_id,
        decision_kind=decision_kind,
        actor_principal=principal.subject,
        rationale=reason,
        decision_content_hash="0" * 64,
        recorded_at=stamp,
        supersedes_decision_id=supersedes_decision_id,
        current_policy_version_id=version_id,
    )
    digest = governance_content_hash(draft)
    decision = PolicyGovernanceDecision.model_validate(
        {**draft.model_dump(mode="python"), "decision_content_hash": digest}
    )
    return store.append_decision(decision)


__all__ = [
    "AuthenticatedPrincipal",
    "ConfidenceBoundRule",
    "CriterionEvaluationResult",
    "CriterionOutcome",
    "GateCriterion",
    "GateEvaluationDetail",
    "GateKind",
    "GovernanceDecisionError",
    "HumanAuthoredGateCriteria",
    "MetricComparisonKind",
    "MissingDataRule",
    "evaluate_gate_criteria",
    "gate_criteria_content_hash",
    "gate_evaluation_content_hash",
    "persist_gate_evaluation",
    "record_policy_governance_decision",
    "to_store_criteria_version",
    "to_store_evaluation",
]
