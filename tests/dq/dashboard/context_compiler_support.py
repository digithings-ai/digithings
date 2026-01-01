"""Shared builders for the research-retrieval context compiler tests.

The compile and wiring suites need the same evidence, belief, loaded state
and ticker bundle fixtures; they live here so both modules build identical
objects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from digiquant.dashboard.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceRecord,
    ExpectedEventVersion,
    LegacyDocumentRef,
    ResearchPatch,
    ResearchStateManifest,
    ResearchStateVersion,
    TickerEvidenceBundle,
    TypedProvenance,
    belief_content_hash,
    belief_version_id,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    manifest_content_hash,
    research_state_version_id,
    ticker_evidence_bundle_content_hash,
    ticker_evidence_bundle_id,
)
from digiquant.dashboard.research_retrieval.store import LoadedResearchState

_TS = datetime(2026, 8, 26, 18, 0, tzinfo=UTC)

_PROV = TypedProvenance(
    source_run_id="run-wp141",
    attempt_id="attempt-1",
    artifact_id="artifact-context",
)

_TICKER = "AAPL"


def _evidence(*, summary: str, belief_ids: tuple[UUID, ...] = ()) -> EvidenceRecord:
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary=summary,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        provenance=_PROV,
        affected_belief_ids=belief_ids,
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    digest = evidence_content_hash(
        source=fields["source"],
        authority=fields["authority"],
        summary=fields["summary"],
        affected_belief_ids=belief_ids,
        supersedes_evidence_id=None,
    )
    return EvidenceRecord(
        evidence_id=evidence_record_id(
            source=fields["source"],
            authority=fields["authority"],
            content_hash=digest,
        ),
        content_hash=digest,
        **fields,
    )


def _belief(*, evidence: EvidenceRecord, statement: str) -> BeliefVersion:
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    digest = belief_content_hash(
        belief_id=belief_id,
        statement=statement,
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%",),
    )
    return BeliefVersion(
        belief_version_id=belief_version_id(
            belief_id=belief_id,
            content_hash=digest,
            supersedes_version_id=None,
        ),
        belief_id=belief_id,
        statement=statement,
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%",),
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )


def _loaded_state(
    *,
    evidence: tuple[EvidenceRecord, ...],
    beliefs: tuple[BeliefVersion, ...] = (),
    events: tuple[ExpectedEventVersion, ...] = (),
    patches: tuple[ResearchPatch, ...] = (),
    legacy_refs: tuple[LegacyDocumentRef, ...] = (),
) -> LoadedResearchState:
    manifest = ResearchStateManifest(
        evidence_ids=tuple(item.evidence_id for item in evidence),
        belief_version_ids=tuple(item.belief_version_id for item in beliefs),
        expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
        patch_ids=tuple(item.patch_id for item in patches),
        legacy_ref_ids=tuple(item.legacy_ref_id for item in legacy_refs),
        content_hash=manifest_content_hash(
            evidence_ids=tuple(item.evidence_id for item in evidence),
            belief_version_ids=tuple(item.belief_version_id for item in beliefs),
            expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
            patch_ids=tuple(item.patch_id for item in patches),
            legacy_ref_ids=tuple(item.legacy_ref_id for item in legacy_refs),
        ),
    )
    version = ResearchStateVersion(
        state_version_id=research_state_version_id(
            manifest_content_hash=manifest.content_hash,
            parent_id=None,
            schema_version=1,
        ),
        parent_state_version_id=None,
        manifest=manifest,
        event_time=_TS - timedelta(hours=4),
        effective_as_of=_TS - timedelta(hours=3),
        known_at=_TS - timedelta(hours=2),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_digest(
            {
                "manifest_content_hash": manifest.content_hash,
                "parent_state_version_id": None,
                "schema_version": 1,
            }
        ),
        provenance=_PROV,
    )
    return LoadedResearchState(
        version=version,
        evidence=evidence,
        beliefs=beliefs,
        expected_events=events,
        patches=patches,
        legacy_refs=legacy_refs,
    )


def _bundle(*, state_version_id: UUID, ticker: str = _TICKER) -> TickerEvidenceBundle:
    ev = UUID("11111111-1111-4111-8111-111111111111")
    digest = ticker_evidence_bundle_content_hash(
        ticker=ticker,
        state_version_id=state_version_id,
        evidence_ids=(ev,),
        source="h5:grounding",
    )
    return TickerEvidenceBundle(
        bundle_id=ticker_evidence_bundle_id(
            source_run_id="run-wp141",
            ticker=ticker,
            content_hash=digest,
        ),
        ticker=ticker,
        source_run_id="run-wp141",
        attempt_id="attempt-1",
        state_version_id=state_version_id,
        evidence_ids=(ev,),
        source="h5:grounding",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )
