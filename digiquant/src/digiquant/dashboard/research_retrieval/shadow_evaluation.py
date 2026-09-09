"""WP13.5 — reconcile attention budgets and evaluate shadow decisions (#2934).

Joins WP13 attention plans/decisions to exact WP1 provider attempts and
per-target downstream artifacts. Evidence-only — never activates enforcement.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from digiquant.dashboard.research_retrieval.planner import (
    AttentionDecisionReconciliation,
    AttentionMode,
    AttentionPolicyEvaluation,
    AttentionReason,
    AttentionRolloutMode,
    H6PlannerModel,
    NonEmptyStr,
)
from digiquant.dashboard.research_retrieval.store import (
    ActualProviderAttemptUsage,
    AttentionStore,
)
from digiquant.dashboard.temporal import require_utc_datetime

FiniteRate: TypeAlias = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


class ShadowProviderAttemptDetail(H6PlannerModel):
    """Exact WP1 attempt usage for shadow evaluation (not aggregate billing)."""

    provider_attempt_id: UUID
    node_run_id: NonEmptyStr | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cached_prompt_tokens: int = Field(default=0, ge=0)
    cached_completion_tokens: int = Field(default=0, ge=0)
    searches: int = Field(default=0, ge=0)
    cost_usd: Decimal | None = None
    latency_ms: int | None = Field(default=None, ge=0)

    def to_actual_usage(self) -> ActualProviderAttemptUsage:
        return ActualProviderAttemptUsage(
            provider_attempt_id=self.provider_attempt_id,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            searches=self.searches,
            cost_usd=self.cost_usd,
        )

    @property
    def uncached_tokens(self) -> int:
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)

    @property
    def cached_tokens(self) -> int:
        return self.cached_prompt_tokens + self.cached_completion_tokens


class AttentionDownstreamOutcomes(H6PlannerModel):
    """Downstream artifact linkage for one attention target (run/node/ticker/artifact)."""

    target_key: NonEmptyStr
    node_run_id: NonEmptyStr | None = None
    carried: bool = False
    amendment_id: NonEmptyStr | None = None
    forecast_assessment_id: NonEmptyStr | None = None
    h7_decision_id: NonEmptyStr | None = None
    exploration_slot: bool = False
    artifact_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @field_validator("artifact_refs", mode="before")
    @classmethod
    def _coerce_artifact_refs(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class ShadowDecisionEvaluationRow(H6PlannerModel):
    """One decision with budget reconciliation, telemetry, and downstream linkage."""

    reconciliation: AttentionDecisionReconciliation
    attempt_details: tuple[ShadowProviderAttemptDetail, ...] = Field(default_factory=tuple)
    downstream: AttentionDownstreamOutcomes | None = None
    telemetry_complete: bool
    downstream_complete: bool
    complete: bool

    @field_validator("attempt_details", mode="before")
    @classmethod
    def _coerce_attempt_details(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class ResearchPolicyShadowEvaluationReport(H6PlannerModel):
    """Shadow evaluation report for one attention plan (WP13.5 / WP16 input)."""

    evaluation: AttentionPolicyEvaluation
    eligible: bool
    reconciliation_rate: FiniteRate
    telemetry_complete: bool
    downstream_complete: bool
    complete: bool
    decision_rows: tuple[ShadowDecisionEvaluationRow, ...] = Field(default_factory=tuple)
    recorded_at: AwareDatetime

    @field_validator("decision_rows", mode="before")
    @classmethod
    def _coerce_decision_rows(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def _attempt_details_to_usages(
    attempt_details: dict[str, tuple[ShadowProviderAttemptDetail, ...]],
) -> dict[str, tuple[ActualProviderAttemptUsage, ...]]:
    return {
        target_key: tuple(item.to_actual_usage() for item in group)
        for target_key, group in attempt_details.items()
    }


def _exploration_decision(decision) -> bool:
    if decision.reason is AttentionReason.EXPLORATION:
        return True
    return bool(getattr(decision.features, "exploration_slot", False))


def _downstream_row_complete(*, decision, downstream: AttentionDownstreamOutcomes | None) -> bool:
    if downstream is None:
        return False
    if downstream.target_key != decision.target_key:
        return False
    if decision.mode is AttentionMode.CARRY:
        if not downstream.carried:
            return False
    elif decision.mode is AttentionMode.METRIC_PATCH:
        has_artifact = bool(
            downstream.amendment_id
            or downstream.forecast_assessment_id
            or downstream.artifact_refs
        )
        if not has_artifact:
            return False
    if _exploration_decision(decision) and not downstream.exploration_slot:
        return False
    if decision.mode in {AttentionMode.CHALLENGE, AttentionMode.DEEP_REFRESH}:
        if decision.budget.provider_calls > 0:
            has_artifact = bool(
                downstream.amendment_id
                or downstream.forecast_assessment_id
                or downstream.artifact_refs
            )
            if not has_artifact:
                return False
    return True


def evaluate_research_policy_shadow(
    store: AttentionStore,
    *,
    plan_id: UUID,
    attempt_details: dict[str, tuple[ShadowProviderAttemptDetail, ...]],
    downstream_by_target: dict[str, AttentionDownstreamOutcomes],
    recorded_at: datetime,
) -> ResearchPolicyShadowEvaluationReport:
    """Reconcile one shadow attention plan to WP1 attempts and downstream artifacts."""
    stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
    envelope = store.load_plan(plan_id)
    plan = envelope.plan
    eligible = plan.rollout_mode is AttentionRolloutMode.SHADOW

    evaluation = store.reconcile_plan(
        plan_id=plan_id,
        attempt_usages=_attempt_details_to_usages(attempt_details),
        recorded_at=stamp,
    )

    decision_rows: list[ShadowDecisionEvaluationRow] = []
    telemetry_complete_count = 0
    downstream_complete_count = 0
    for reconciliation in evaluation.decision_reconciliations:
        details = attempt_details.get(reconciliation.target_key, ())
        downstream = downstream_by_target.get(reconciliation.target_key)
        decision = next(
            item for item in plan.decisions if item.target_key == reconciliation.target_key
        )
        telemetry_complete = reconciliation.complete
        downstream_complete = _downstream_row_complete(decision=decision, downstream=downstream)
        row_complete = telemetry_complete and downstream_complete
        if telemetry_complete:
            telemetry_complete_count += 1
        if downstream_complete:
            downstream_complete_count += 1
        decision_rows.append(
            ShadowDecisionEvaluationRow(
                reconciliation=reconciliation,
                attempt_details=details,
                downstream=downstream,
                telemetry_complete=telemetry_complete,
                downstream_complete=downstream_complete,
                complete=row_complete,
            )
        )

    total = len(evaluation.decision_reconciliations)
    if total == 0:
        reconciliation_rate = Decimal("1")
    else:
        reconciliation_rate = Decimal(telemetry_complete_count) / Decimal(total)

    telemetry_complete = telemetry_complete_count == total
    downstream_complete = downstream_complete_count == total
    if eligible:
        complete = telemetry_complete and downstream_complete
    else:
        complete = evaluation.complete

    return ResearchPolicyShadowEvaluationReport(
        evaluation=evaluation,
        eligible=eligible,
        reconciliation_rate=reconciliation_rate,
        telemetry_complete=telemetry_complete,
        downstream_complete=downstream_complete,
        complete=complete,
        decision_rows=tuple(decision_rows),
        recorded_at=stamp,
    )


def write_shadow_evaluation_report(
    report: ResearchPolicyShadowEvaluationReport,
    path: str | bytes,
) -> None:
    """Persist evaluation report as canonical JSON (file-only evidence)."""
    target = path if isinstance(path, str) else path.decode("utf-8")
    payload = report.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True, indent=2)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")


__all__ = [
    "AttentionDownstreamOutcomes",
    "ResearchPolicyShadowEvaluationReport",
    "ShadowDecisionEvaluationRow",
    "ShadowProviderAttemptDetail",
    "evaluate_research_policy_shadow",
    "write_shadow_evaluation_report",
]
