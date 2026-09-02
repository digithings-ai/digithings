"""Private append-only policy replay governance store (#2983 / WP16.2).

Persists WP16.1 manifests/pairs, run lifecycle events, arm results, comparison
reports, gate criteria, evaluations, and human decisions. In-memory for unit tests;
migration ``094_olympus_policy_replay.sql`` is the durable schema.

Semantics:
- **Manifest/pair dedupe:** identical content hash is a no-op.
- **Run lifecycle:** append-only events; no mutable running-status row.
- **Arm results:** one immutable final result per (run_id, arm_id).
- **Governance rows:** criteria/decisions may supersede via child versions;
  evaluations and comparisons are immutable once written.
- **As-of reads:** criteria and manifest selection honor temporal cutoffs.
- **Reconstruction:** ``load_gate_evidence`` resolves full lineage by IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from digiquant.olympus.replay.governance_models import (
    GateCriteriaVersion,
    GateEvaluation,
    PolicyComparisonReport,
    PolicyGovernanceDecision,
    ReplayRunEvent,
    ReplayRunEventKind,
)
from digiquant.olympus.replay.models import (
    PortfolioReplayResult,
    ReplayInputManifest,
    ReplayPairSpec,
)
from digiquant.olympus.temporal import require_utc_datetime

T = TypeVar("T", bound=BaseModel)


class PolicyReplayStoreConflict(RuntimeError):
    """Same identity already stored with incompatible content."""


class PolicyReplayStoreError(RuntimeError):
    """Store refused a write or could not resolve exact state."""


class PolicyReplayStoreMissingError(LookupError):
    """Exact entity or lineage target not found."""


@dataclass(frozen=True)
class PersistedManifest:
    """Stored manifest envelope with stable record id."""

    record_id: UUID
    manifest: ReplayInputManifest
    recorded_at: datetime


@dataclass(frozen=True)
class PersistedPair:
    """Stored pair envelope."""

    record_id: UUID
    pair: ReplayPairSpec
    shared_manifest_content_hash: str
    recorded_at: datetime


@dataclass(frozen=True)
class PersistedArmResult:
    """Immutable final arm result for one replay run."""

    record_id: UUID
    run_id: str
    arm_id: str
    result: PortfolioReplayResult
    recorded_at: datetime


@dataclass(frozen=True)
class LoadedGateEvidence:
    """Full immutable lineage for one gate evaluation."""

    evaluation: GateEvaluation
    comparison: PolicyComparisonReport
    criteria: GateCriteriaVersion
    pair: ReplayPairSpec
    manifest: ReplayInputManifest
    decisions: tuple[PolicyGovernanceDecision, ...]


def _require_parent(*, label: str, parent_id: UUID | None, present: bool) -> None:
    if parent_id is not None and not present:
        raise PolicyReplayStoreError(f"{label} references missing parent {parent_id}")


class PolicyReplayStore:
    """Append-only replay/governance boundary (no upsert / update / delete)."""

    def __init__(self) -> None:
        self._manifests_by_hash: dict[str, PersistedManifest] = {}
        self._manifests_by_id: dict[UUID, PersistedManifest] = {}
        self._pairs_by_hash: dict[str, PersistedPair] = {}
        self._pairs_by_id: dict[UUID, PersistedPair] = {}
        self._events: dict[UUID, ReplayRunEvent] = {}
        self._events_by_run: dict[str, tuple[UUID, ...]] = {}
        self._event_sequence_keys: dict[tuple[str, int], UUID] = {}
        self._arm_results: dict[tuple[str, str], PersistedArmResult] = {}
        self._comparisons: dict[UUID, PolicyComparisonReport] = {}
        self._comparisons_by_hash: dict[str, UUID] = {}
        self._criteria: dict[UUID, GateCriteriaVersion] = {}
        self._evaluations: dict[UUID, GateEvaluation] = {}
        self._evaluations_by_hash: dict[str, UUID] = {}
        self._decisions: dict[UUID, PolicyGovernanceDecision] = {}
        self._decisions_by_evaluation: dict[UUID, tuple[UUID, ...]] = {}

    def _append_idempotent(
        self,
        *,
        store: dict[UUID, T],
        key: UUID,
        value: T,
        content_hash: str | None,
        existing_hash: str | None,
        label: str,
    ) -> T:
        if key in store:
            if content_hash is not None and existing_hash is not None:
                if existing_hash == content_hash:
                    return store[key]
            elif store[key].model_dump_json() == value.model_dump_json():
                return store[key]
            raise PolicyReplayStoreConflict(f"{label} {key} exists with different content")
        store[key] = value
        return value

    def _track_run_event(self, event: ReplayRunEvent) -> None:
        linked = self._events_by_run.get(event.run_id, ())
        if event.event_id not in linked:
            self._events_by_run[event.run_id] = (*linked, event.event_id)

    def append_manifest(
        self,
        manifest: ReplayInputManifest,
        *,
        recorded_at: datetime,
    ) -> PersistedManifest:
        """Insert manifest; dedupe on ``manifest_content_hash``."""
        stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
        existing = self._manifests_by_hash.get(manifest.manifest_content_hash)
        if existing is not None:
            return existing
        record_id = uuid4()
        envelope = PersistedManifest(record_id=record_id, manifest=manifest, recorded_at=stamp)
        self._manifests_by_hash[manifest.manifest_content_hash] = envelope
        self._manifests_by_id[record_id] = envelope
        return envelope

    def append_pair(
        self,
        pair: ReplayPairSpec,
        *,
        recorded_at: datetime,
    ) -> PersistedPair:
        """Insert pair; requires stored shared manifest and identical arm hashes."""
        stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
        manifest_hash = pair.shared_manifest.manifest_content_hash
        if pair.incumbent.manifest_content_hash != manifest_hash:
            raise PolicyReplayStoreError("incumbent must reference identical shared manifest")
        if pair.challenger.manifest_content_hash != manifest_hash:
            raise PolicyReplayStoreError("challenger must reference identical shared manifest")
        if pair.incumbent.manifest_content_hash != pair.challenger.manifest_content_hash:
            raise PolicyReplayStoreError("paired arms require identical shared manifest")
        if manifest_hash not in self._manifests_by_hash:
            raise PolicyReplayStoreError(
                f"pair references unknown manifest_content_hash {manifest_hash}"
            )

        existing = self._pairs_by_hash.get(pair.pair_content_hash)
        if existing is not None:
            return existing

        record_id = uuid4()
        envelope = PersistedPair(
            record_id=record_id,
            pair=pair,
            shared_manifest_content_hash=manifest_hash,
            recorded_at=stamp,
        )
        self._pairs_by_hash[pair.pair_content_hash] = envelope
        self._pairs_by_id[record_id] = envelope
        return envelope

    def append_run_event(self, event: ReplayRunEvent) -> ReplayRunEvent:
        """Append one lifecycle event; exact retry is a no-op."""
        require_utc_datetime(event.recorded_at, field_name="recorded_at")
        known_pairs = {row.pair.pair_id for row in self._pairs_by_hash.values()}
        if event.pair_id not in known_pairs:
            raise PolicyReplayStoreError(f"run event references unknown pair_id {event.pair_id}")
        seq_key = (event.run_id, event.sequence)
        existing_seq = self._event_sequence_keys.get(seq_key)
        if existing_seq is not None and existing_seq != event.event_id:
            raise PolicyReplayStoreConflict(
                f"run event sequence already exists for run={event.run_id} sequence={event.sequence}"
            )
        stored = self._append_idempotent(
            store=self._events,
            key=event.event_id,
            value=event,
            content_hash=None,
            existing_hash=None,
            label="event_id",
        )
        self._track_run_event(stored)
        self._event_sequence_keys[(stored.run_id, stored.sequence)] = stored.event_id
        return stored

    def list_run_events(self, run_id: str) -> tuple[ReplayRunEvent, ...]:
        """Events for one run ordered by sequence."""
        event_ids = self._events_by_run.get(run_id, ())
        rows = [self._events[eid] for eid in event_ids if eid in self._events]
        rows.sort(key=lambda item: item.sequence)
        return tuple(rows)

    def run_status_from_events(self, run_id: str) -> str:
        """Derive coarse status from append-only events (no mutable row)."""
        events = self.list_run_events(run_id)
        if not events:
            return "unknown"
        kinds = {event.event_kind for event in events}
        if ReplayRunEventKind.RUN_FAILED in kinds:
            return "failed"
        if ReplayRunEventKind.RUN_COMPLETED in kinds:
            return "completed"
        if ReplayRunEventKind.RUN_STARTED in kinds:
            return "in_progress"
        return "unknown"

    def append_arm_result(
        self,
        *,
        run_id: str,
        arm_id: str,
        result: PortfolioReplayResult,
        recorded_at: datetime,
    ) -> PersistedArmResult:
        """Persist one immutable final arm result."""
        stamp = require_utc_datetime(recorded_at, field_name="recorded_at")
        key = (run_id, arm_id)
        existing = self._arm_results.get(key)
        if existing is not None:
            if existing.result.model_dump_json() == result.model_dump_json():
                return existing
            raise PolicyReplayStoreConflict(
                f"arm result for run={run_id} arm={arm_id} exists with different content"
            )
        record_id = uuid4()
        envelope = PersistedArmResult(
            record_id=record_id,
            run_id=run_id,
            arm_id=arm_id,
            result=result,
            recorded_at=stamp,
        )
        self._arm_results[key] = envelope
        return envelope

    def append_comparison(self, report: PolicyComparisonReport) -> PolicyComparisonReport:
        """Insert immutable comparison report."""
        require_utc_datetime(report.recorded_at, field_name="recorded_at")
        if report.pair_content_hash not in self._pairs_by_hash:
            raise PolicyReplayStoreError(
                f"comparison references unknown pair_content_hash {report.pair_content_hash}"
            )
        pair_row = self._pairs_by_hash[report.pair_content_hash]
        if report.shared_manifest_content_hash != pair_row.shared_manifest_content_hash:
            raise PolicyReplayStoreError(
                "comparison shared_manifest_content_hash must match stored pair"
            )
        existing_id = self._comparisons_by_hash.get(report.report_content_hash)
        if existing_id is not None:
            existing = self._comparisons[existing_id]
            if existing.model_dump_json() == report.model_dump_json():
                return existing
            raise PolicyReplayStoreConflict(
                f"report_content_hash {report.report_content_hash} exists with different content"
            )
        if report.comparison_id in self._comparisons:
            stored = self._comparisons[report.comparison_id]
            if stored.model_dump_json() == report.model_dump_json():
                return stored
            raise PolicyReplayStoreConflict(
                f"comparison_id {report.comparison_id} exists with different content"
            )
        self._comparisons[report.comparison_id] = report
        self._comparisons_by_hash[report.report_content_hash] = report.comparison_id
        return report

    def append_criteria(self, criteria: GateCriteriaVersion) -> GateCriteriaVersion:
        """Insert criteria version; supersession requires parent present."""
        _require_parent(
            label="GateCriteriaVersion",
            parent_id=criteria.supersedes_version_id,
            present=(
                criteria.supersedes_version_id is None
                or criteria.supersedes_version_id in self._criteria
            ),
        )
        existing = self._criteria.get(criteria.criteria_version_id)
        return self._append_idempotent(
            store=self._criteria,
            key=criteria.criteria_version_id,
            value=criteria,
            content_hash=criteria.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="criteria_version_id",
        )

    def append_evaluation(self, evaluation: GateEvaluation) -> GateEvaluation:
        """Insert immutable gate evaluation."""
        require_utc_datetime(evaluation.recorded_at, field_name="recorded_at")
        if evaluation.comparison_id not in self._comparisons:
            raise PolicyReplayStoreError(
                f"evaluation references missing comparison_id {evaluation.comparison_id}"
            )
        if evaluation.criteria_version_id not in self._criteria:
            raise PolicyReplayStoreError(
                f"evaluation references missing criteria_version_id {evaluation.criteria_version_id}"
            )
        existing_id = self._evaluations_by_hash.get(evaluation.evaluation_content_hash)
        if existing_id is not None:
            existing = self._evaluations[existing_id]
            if existing.model_dump_json() == evaluation.model_dump_json():
                return existing
            raise PolicyReplayStoreConflict(
                f"evaluation_content_hash {evaluation.evaluation_content_hash} "
                "exists with different content"
            )
        if evaluation.evaluation_id in self._evaluations:
            stored = self._evaluations[evaluation.evaluation_id]
            if stored.model_dump_json() == evaluation.model_dump_json():
                return stored
            raise PolicyReplayStoreConflict(
                f"evaluation_id {evaluation.evaluation_id} exists with different content"
            )
        self._evaluations[evaluation.evaluation_id] = evaluation
        self._evaluations_by_hash[evaluation.evaluation_content_hash] = evaluation.evaluation_id
        return evaluation

    def get_pair_by_content_hash(self, pair_content_hash: str) -> PersistedPair | None:
        """Return a stored pair envelope by content hash, or ``None``."""
        return self._pairs_by_hash.get(pair_content_hash)

    def get_pair_by_pair_id(self, pair_id: str) -> PersistedPair | None:
        """Return the first stored pair matching logical ``pair_id``, or ``None``."""
        for row in self._pairs_by_hash.values():
            if row.pair.pair_id == pair_id:
                return row
        return None

    def get_comparison(self, comparison_id: UUID) -> PolicyComparisonReport | None:
        """Return a stored comparison envelope by id, or ``None``."""
        return self._comparisons.get(comparison_id)

    def list_arm_ids_for_run(self, run_id: str) -> tuple[str, ...]:
        """Arm ids that have an immutable result for ``run_id``."""
        arms = sorted(arm_id for (rid, arm_id) in self._arm_results if rid == run_id)
        return tuple(arms)

    def get_evaluation(self, evaluation_id: UUID) -> GateEvaluation | None:
        """Return a stored evaluation by id, or ``None`` if absent."""
        return self._evaluations.get(evaluation_id)

    def list_decisions_for_evaluation(
        self, evaluation_id: UUID
    ) -> tuple[PolicyGovernanceDecision, ...]:
        """Decisions linked to one evaluation, ordered by recorded_at."""
        decision_ids = self._decisions_by_evaluation.get(evaluation_id, ())
        rows = [self._decisions[did] for did in decision_ids if did in self._decisions]
        rows.sort(key=lambda item: item.recorded_at)
        return tuple(rows)

    def append_decision(self, decision: PolicyGovernanceDecision) -> PolicyGovernanceDecision:
        """Insert immutable human governance decision."""
        require_utc_datetime(decision.recorded_at, field_name="recorded_at")
        if decision.evaluation_id not in self._evaluations:
            raise PolicyReplayStoreError(
                f"decision references missing evaluation_id {decision.evaluation_id}"
            )
        _require_parent(
            label="PolicyGovernanceDecision",
            parent_id=decision.supersedes_decision_id,
            present=(
                decision.supersedes_decision_id is None
                or decision.supersedes_decision_id in self._decisions
            ),
        )
        existing = self._decisions.get(decision.decision_id)
        stored = self._append_idempotent(
            store=self._decisions,
            key=decision.decision_id,
            value=decision,
            content_hash=decision.decision_content_hash,
            existing_hash=None if existing is None else existing.decision_content_hash,
            label="decision_id",
        )
        linked = self._decisions_by_evaluation.get(decision.evaluation_id, ())
        if decision.decision_id not in linked:
            self._decisions_by_evaluation[decision.evaluation_id] = (*linked, decision.decision_id)
        return stored

    def select_criteria_as_of(
        self,
        *,
        criteria_key: str,
        as_of: datetime,
    ) -> GateCriteriaVersion | None:
        """Newest eligible criteria version visible at ``as_of``."""
        bound = require_utc_datetime(as_of, field_name="as_of")
        candidates = [
            row
            for row in self._criteria.values()
            if row.criteria_key == criteria_key and row.effective_at <= bound
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.effective_at, item.recorded_at), reverse=True)
        return candidates[0]

    def select_manifest_as_of(
        self,
        *,
        manifest_id: str,
        as_of: datetime,
    ) -> ReplayInputManifest | None:
        """Newest stored manifest with matching logical id visible at replay cutoff."""
        bound = require_utc_datetime(as_of, field_name="as_of")
        candidates: list[PersistedManifest] = []
        for row in self._manifests_by_hash.values():
            if row.manifest.manifest_id != manifest_id:
                continue
            if row.manifest.replay_as_of > bound:
                continue
            candidates.append(row)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (item.manifest.replay_as_of, item.recorded_at), reverse=True
        )
        return candidates[0].manifest

    def load_gate_evidence(self, evaluation_id: UUID) -> LoadedGateEvidence:
        """Reconstruct full gate lineage from immutable IDs — never fabricates rows."""
        evaluation = self._evaluations.get(evaluation_id)
        if evaluation is None:
            raise PolicyReplayStoreMissingError(f"evaluation_id {evaluation_id} not found")
        comparison = self._comparisons.get(evaluation.comparison_id)
        if comparison is None:
            raise PolicyReplayStoreError(
                f"evaluation {evaluation_id} references missing comparison "
                f"{evaluation.comparison_id}"
            )
        criteria = self._criteria.get(evaluation.criteria_version_id)
        if criteria is None:
            raise PolicyReplayStoreError(
                f"evaluation {evaluation_id} references missing criteria "
                f"{evaluation.criteria_version_id}"
            )
        pair_row = self._pairs_by_hash.get(comparison.pair_content_hash)
        if pair_row is None:
            raise PolicyReplayStoreError(
                f"comparison {comparison.comparison_id} references missing pair "
                f"{comparison.pair_content_hash}"
            )
        manifest_row = self._manifests_by_hash.get(comparison.shared_manifest_content_hash)
        if manifest_row is None:
            raise PolicyReplayStoreError(
                f"comparison {comparison.comparison_id} references missing manifest "
                f"{comparison.shared_manifest_content_hash}"
            )
        decision_ids = self._decisions_by_evaluation.get(evaluation_id, ())
        decisions: list[PolicyGovernanceDecision] = []
        for decision_id in decision_ids:
            decision = self._decisions.get(decision_id)
            if decision is None:
                raise PolicyReplayStoreError(
                    f"evaluation {evaluation_id} index references missing decision {decision_id}"
                )
            decisions.append(decision)
        decisions.sort(key=lambda item: item.recorded_at)
        return LoadedGateEvidence(
            evaluation=evaluation,
            comparison=comparison,
            criteria=criteria,
            pair=pair_row.pair,
            manifest=manifest_row.manifest,
            decisions=tuple(decisions),
        )

    def manifest_count(self) -> int:
        return len(self._manifests_by_hash)


__all__ = [
    "LoadedGateEvidence",
    "PersistedArmResult",
    "PersistedManifest",
    "PersistedPair",
    "PolicyReplayStore",
    "PolicyReplayStoreConflict",
    "PolicyReplayStoreError",
    "PolicyReplayStoreMissingError",
]
