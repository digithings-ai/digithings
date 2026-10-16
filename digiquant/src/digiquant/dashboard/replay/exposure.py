"""WP16.9 — typed policy-replay exposure summaries (recommendation/read only).

Service/MCP/CLI return artifact IDs and coarse status only — never confidential
fills/holdings/nav paths or raw metric leaves. Running and evaluating never
activate production policy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from digiquant.dashboard.replay.comparison import (
    PolicyComparisonReport as RichPolicyComparisonReport,
)
from digiquant.dashboard.replay.governance import (
    AuthenticatedPrincipal,
    HumanAuthoredGateCriteria,
    evaluate_gate_criteria,
    persist_gate_evaluation,
    record_policy_governance_decision,
    to_store_criteria_version,
)
from digiquant.dashboard.replay.governance_models import (
    GovernanceDecisionKind,
    PolicyGovernanceDecision,
    ReplayRunEvent,
    ReplayRunEventKind,
)
from digiquant.dashboard.replay.store import (
    PolicyReplayStore,
    PolicyReplayStoreMissingError,
)
from digiquant.dashboard.temporal import require_utc_datetime

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
HashHex64: TypeAlias = Annotated[str, Field(min_length=64, max_length=64)]


class ExposureModel(BaseModel):
    """Strict immutable summary envelope — IDs and coarse flags only."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyReplayRunSummary(ExposureModel):
    """Coarse replay-run status derived from append-only events."""

    run_id: NonEmptyId
    pair_id: NonEmptyId
    pair_content_hash: HashHex64
    status: NonEmptyId
    event_kinds: tuple[str, ...] = ()
    arm_ids: tuple[str, ...] = ()

    @field_validator("event_kinds", "arm_ids", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class PolicyComparisonSummary(ExposureModel):
    """Comparison artifact IDs — no metric leaves or fold evidence."""

    comparison_id: UUID
    pair_content_hash: HashHex64
    shared_manifest_content_hash: HashHex64
    report_content_hash: HashHex64
    status: NonEmptyId
    metric_groups_present: tuple[str, ...] = ()
    recorded_at: datetime

    @field_validator("metric_groups_present", mode="before")
    @classmethod
    def _coerce_groups(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


class PolicyGateEvaluationSummary(ExposureModel):
    """Gate evaluation eligibility summary — no per-criterion observed values."""

    evaluation_id: UUID
    comparison_id: UUID
    criteria_version_id: UUID
    evaluation_content_hash: HashHex64
    eligible_for_human_review: bool
    blockers: tuple[str, ...] = ()
    recorded_at: datetime
    decision_ids: tuple[UUID, ...] = ()

    @field_validator("blockers", "decision_ids", mode="before")
    @classmethod
    def _coerce_lists(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return require_utc_datetime(value, field_name="recorded_at")


class PolicyReplayExposureError(LookupError):
    """Invalid or missing replay/governance artifact (fail closed)."""


class PolicyReplayFacade:
    """In-process facade over ``PolicyReplayStore`` with rich-report caches.

    Rich comparison/criteria bodies stay process-local for evaluate; external
    surfaces only see summaries. Never activates or mutates production policy.
    """

    def __init__(self, store: PolicyReplayStore | None = None) -> None:
        self.store = store or PolicyReplayStore()
        self._rich_comparisons: dict[UUID, RichPolicyComparisonReport] = {}
        self._rich_criteria: dict[UUID, HumanAuthoredGateCriteria] = {}

    def ingest_comparison(self, report: RichPolicyComparisonReport) -> PolicyComparisonSummary:
        """Persist the thin envelope and cache the rich report for evaluate."""
        if self.store.get_pair_by_content_hash(report.pair_content_hash) is None:
            # Pair must already be stored (run/compare offline first).
            raise PolicyReplayExposureError(
                f"pair_content_hash {report.pair_content_hash} not found — "
                "append pair before ingesting comparison"
            )
        envelope = report.to_governance_envelope()
        self.store.append_comparison(envelope)
        self._rich_comparisons[report.comparison_id] = report
        return self._comparison_summary(envelope)

    def ingest_criteria(self, criteria: HumanAuthoredGateCriteria) -> UUID:
        """Persist criteria version and cache the rich package for evaluate."""
        self.store.append_criteria(to_store_criteria_version(criteria))
        self._rich_criteria[criteria.criteria_version_id] = criteria
        return criteria.criteria_version_id

    def run_policy_replay(
        self,
        *,
        pair_content_hash: str,
        run_id: str | None = None,
        recorded_at: datetime | None = None,
    ) -> PolicyReplayRunSummary:
        """Register a replay run against a stored pair (no policy activation)."""
        pair_row = self.store.get_pair_by_content_hash(pair_content_hash)
        if pair_row is None:
            raise PolicyReplayExposureError(f"pair_content_hash {pair_content_hash} not found")
        stamp = require_utc_datetime(recorded_at or datetime.now(tz=UTC), field_name="recorded_at")
        rid = (run_id or f"replay-{uuid4()}").strip()
        if not rid:
            raise PolicyReplayExposureError("run_id must be non-empty")
        existing = self.store.list_run_events(rid)
        if existing:
            return self.get_policy_replay(rid)
        self.store.append_run_event(
            ReplayRunEvent(
                event_id=uuid4(),
                run_id=rid,
                pair_id=pair_row.pair.pair_id,
                event_kind=ReplayRunEventKind.RUN_STARTED,
                sequence=0,
                recorded_at=stamp,
                detail="service_run_policy_replay",
            )
        )
        return self.get_policy_replay(rid)

    def get_policy_replay(self, run_id: str) -> PolicyReplayRunSummary:
        events = self.store.list_run_events(run_id)
        if not events:
            raise PolicyReplayExposureError(f"run_id {run_id} not found")
        pair_id = events[0].pair_id
        pair_row = self.store.get_pair_by_pair_id(pair_id)
        if pair_row is None:
            raise PolicyReplayExposureError(f"run {run_id} references unknown pair_id {pair_id}")
        arm_ids = self.store.list_arm_ids_for_run(run_id)
        return PolicyReplayRunSummary(
            run_id=run_id,
            pair_id=pair_id,
            pair_content_hash=pair_row.pair.pair_content_hash,
            status=self.store.run_status_from_events(run_id),
            event_kinds=tuple(event.event_kind.value for event in events),
            arm_ids=arm_ids,
        )

    def get_policy_comparison(self, comparison_id: UUID | str) -> PolicyComparisonSummary:
        cid = _as_uuid(comparison_id, label="comparison_id")
        envelope = self.store.get_comparison(cid)
        if envelope is None:
            raise PolicyReplayExposureError(f"comparison_id {cid} not found")
        return self._comparison_summary(envelope)

    def evaluate_policy_gate(
        self,
        *,
        comparison_id: UUID | str,
        criteria_version_id: UUID | str,
        recorded_at: datetime | None = None,
    ) -> PolicyGateEvaluationSummary:
        """Apply cached human-authored criteria; never activates policy."""
        cid = _as_uuid(comparison_id, label="comparison_id")
        crit_id = _as_uuid(criteria_version_id, label="criteria_version_id")
        rich = self._rich_comparisons.get(cid)
        if rich is None:
            raise PolicyReplayExposureError(
                f"comparison_id {cid} metrics not available for evaluate "
                "(ingest rich comparison in this process first)"
            )
        criteria = self._rich_criteria.get(crit_id)
        if criteria is None:
            raise PolicyReplayExposureError(
                f"criteria_version_id {crit_id} not available for evaluate "
                "(ingest rich criteria in this process first)"
            )
        stamp = require_utc_datetime(recorded_at or datetime.now(tz=UTC), field_name="recorded_at")
        detail = evaluate_gate_criteria(criteria=criteria, report=rich, recorded_at=stamp)
        persist_gate_evaluation(self.store, criteria=criteria, report=rich, detail=detail)
        return PolicyGateEvaluationSummary(
            evaluation_id=detail.evaluation_id,
            comparison_id=detail.comparison_id,
            criteria_version_id=detail.criteria_version_id,
            evaluation_content_hash=detail.evaluation_content_hash,
            eligible_for_human_review=detail.eligible_for_human_review,
            blockers=detail.blockers,
            recorded_at=detail.recorded_at,
            decision_ids=(),
        )

    def get_policy_gate_evaluation(self, evaluation_id: UUID | str) -> PolicyGateEvaluationSummary:
        eid = _as_uuid(evaluation_id, label="evaluation_id")
        try:
            evidence = self.store.load_gate_evidence(eid)
        except PolicyReplayStoreMissingError as exc:
            raise PolicyReplayExposureError(str(exc)) from exc
        decisions = evidence.decisions
        return PolicyGateEvaluationSummary(
            evaluation_id=evidence.evaluation.evaluation_id,
            comparison_id=evidence.evaluation.comparison_id,
            criteria_version_id=evidence.evaluation.criteria_version_id,
            evaluation_content_hash=evidence.evaluation.evaluation_content_hash,
            eligible_for_human_review=evidence.evaluation.eligible_for_human_review,
            blockers=evidence.evaluation.blockers,
            recorded_at=evidence.evaluation.recorded_at,
            decision_ids=tuple(d.decision_id for d in decisions),
        )

    def record_decision(
        self,
        *,
        principal: AuthenticatedPrincipal,
        evaluation_id: UUID | str,
        decision_kind: GovernanceDecisionKind | str,
        rationale: str,
        recorded_at: datetime | None = None,
        current_policy_version_id: str | None = None,
        supersedes_decision_id: UUID | str | None = None,
    ) -> PolicyGovernanceDecision:
        """Authenticated decision write — never expose on unauthenticated MCP."""
        if not isinstance(principal, AuthenticatedPrincipal):
            raise TypeError("principal must be AuthenticatedPrincipal")
        kind = (
            decision_kind
            if isinstance(decision_kind, GovernanceDecisionKind)
            else GovernanceDecisionKind(str(decision_kind))
        )
        stamp = require_utc_datetime(recorded_at or datetime.now(tz=UTC), field_name="recorded_at")
        supersedes = (
            None
            if supersedes_decision_id is None
            else _as_uuid(supersedes_decision_id, label="supersedes_decision_id")
        )
        return record_policy_governance_decision(
            self.store,
            principal=principal,
            evaluation_id=_as_uuid(evaluation_id, label="evaluation_id"),
            decision_kind=kind,
            rationale=rationale,
            recorded_at=stamp,
            current_policy_version_id=current_policy_version_id,
            supersedes_decision_id=supersedes,
        )

    @staticmethod
    def _comparison_summary(envelope) -> PolicyComparisonSummary:
        return PolicyComparisonSummary(
            comparison_id=envelope.comparison_id,
            pair_content_hash=envelope.pair_content_hash,
            shared_manifest_content_hash=envelope.shared_manifest_content_hash,
            report_content_hash=envelope.report_content_hash,
            status=envelope.status,
            metric_groups_present=envelope.metric_groups_present,
            recorded_at=envelope.recorded_at,
        )


def _as_uuid(value: UUID | str, *, label: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise PolicyReplayExposureError(f"invalid {label}: {value!r}") from exc


__all__ = [
    "PolicyComparisonSummary",
    "PolicyGateEvaluationSummary",
    "PolicyReplayExposureError",
    "PolicyReplayFacade",
    "PolicyReplayRunSummary",
]
