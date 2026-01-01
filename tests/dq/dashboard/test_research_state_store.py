"""Append-only research-state store (#2854 / WP12.2).

Covers content idempotency, changed-content append, as-of selection, run pins,
exact load after newer rows, child-parent checks, and strict exclusion of
future-known / legacy-null-known rows. Migration privacy contracts live in
``tests/dq/research/test_migration_088.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.dashboard.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceRecord,
    ExpectedEventStatus,
    ExpectedEventVersion,
    LegacyDocumentRef,
    PatchMode,
    PatchTargetKind,
    ResearchPatch,
    ResearchStateManifest,
    ResearchStatePin,
    ResearchStateVersion,
    TypedProvenance,
    belief_content_hash,
    belief_version_id,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    expected_event_content_hash,
    expected_event_version_id,
    legacy_document_ref_id,
    manifest_content_hash,
    research_patch_content_hash,
    research_patch_id,
    research_state_version_id,
)
from digiquant.dashboard.research_retrieval.store import (
    ResearchStateConflict,
    ResearchStateError,
    ResearchStateMissingError,
    ResearchStateStore,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-wp122",
    attempt_id="attempt-1",
    artifact_id="artifact-store",
)


def _evidence(
    *, summary: str = "Filed 8-K item 2.02", known_at: datetime | None = None
) -> EvidenceRecord:
    known = known_at if known_at is not None else _TS - timedelta(minutes=30)
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary=summary,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=known,
        recorded_at=max(known, _TS),
        provenance=_PROV,
        affected_belief_ids=(),
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    content_hash = evidence_content_hash(
        source=fields["source"],
        authority=fields["authority"],
        summary=fields["summary"],
        supersedes_evidence_id=fields.get("supersedes_evidence_id"),
    )
    return EvidenceRecord(
        evidence_id=evidence_record_id(
            source=fields["source"],
            authority=fields["authority"],
            content_hash=content_hash,
        ),
        content_hash=content_hash,
        **fields,
    )


def _belief(
    *,
    evidence: EvidenceRecord,
    statement: str = "USD soft-landing remains base case",
    supersedes_version_id: UUID | None = None,
    known_at: datetime | None = None,
) -> BeliefVersion:
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    known = known_at if known_at is not None else _TS - timedelta(hours=1)
    content_hash = belief_content_hash(
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
            content_hash=content_hash,
            supersedes_version_id=supersedes_version_id,
        ),
        belief_id=belief_id,
        statement=statement,
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%",),
        supersedes_version_id=supersedes_version_id,
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=known,
        recorded_at=max(known, _TS),
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _event(*, evidence: EvidenceRecord | None = None) -> ExpectedEventVersion:
    event_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    support = () if evidence is None else (evidence.evidence_id,)
    content_hash = expected_event_content_hash(
        expected_event_id=event_id,
        label="FOMC decision",
        status=ExpectedEventStatus.OPEN,
        event_time=_TS + timedelta(days=5),
        supporting_evidence_ids=support,
    )
    return ExpectedEventVersion(
        expected_event_version_id=expected_event_version_id(
            expected_event_id=event_id,
            content_hash=content_hash,
            supersedes_version_id=None,
        ),
        expected_event_id=event_id,
        label="FOMC decision",
        status=ExpectedEventStatus.OPEN,
        event_time=_TS + timedelta(days=5),
        supporting_evidence_ids=support,
        supersedes_version_id=None,
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS,
        recorded_at=_TS + timedelta(minutes=1),
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _patch(*, summary: str = "Refresh rates section after CPI") -> ResearchPatch:
    content_hash = research_patch_content_hash(
        target_kind=PatchTargetKind.SECTION,
        target_id="macro:rates",
        mode=PatchMode.SECTION_PATCH,
        summary=summary,
    )
    return ResearchPatch(
        patch_id=research_patch_id(
            target_kind=PatchTargetKind.SECTION.value,
            target_id="macro:rates",
            content_hash=content_hash,
            supersedes_patch_id=None,
        ),
        target_kind=PatchTargetKind.SECTION,
        target_id="macro:rates",
        mode=PatchMode.SECTION_PATCH,
        summary=summary,
        supersedes_patch_id=None,
        event_time=_TS - timedelta(hours=1),
        effective_as_of=_TS - timedelta(minutes=30),
        known_at=_TS - timedelta(minutes=10),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _legacy() -> LegacyDocumentRef:
    source_hash = "abc123def456"
    return LegacyDocumentRef(
        legacy_ref_id=legacy_document_ref_id(
            document_key="macro",
            as_of_date="2026-08-20",
            source_hash=source_hash,
        ),
        document_key="macro",
        as_of_date="2026-08-20",
        source_table="documents",
        source_hash=source_hash,
        known_at=None,
        legacy_manifest_only=True,
    )


def _version(
    *,
    evidence: tuple[EvidenceRecord, ...] = (),
    beliefs: tuple[BeliefVersion, ...] = (),
    events: tuple[ExpectedEventVersion, ...] = (),
    patches: tuple[ResearchPatch, ...] = (),
    legacy: tuple[LegacyDocumentRef, ...] = (),
    parent: UUID | None = None,
    known_at: datetime | None = None,
    effective_as_of: datetime | None = None,
) -> ResearchStateVersion:
    known = known_at if known_at is not None else _TS
    effective = effective_as_of if effective_as_of is not None else _TS - timedelta(minutes=5)
    manifest = ResearchStateManifest(
        evidence_ids=tuple(e.evidence_id for e in evidence),
        belief_version_ids=tuple(b.belief_version_id for b in beliefs),
        expected_event_version_ids=tuple(e.expected_event_version_id for e in events),
        patch_ids=tuple(p.patch_id for p in patches),
        legacy_ref_ids=tuple(r.legacy_ref_id for r in legacy),
        content_hash=manifest_content_hash(
            evidence_ids=tuple(e.evidence_id for e in evidence),
            belief_version_ids=tuple(b.belief_version_id for b in beliefs),
            expected_event_version_ids=tuple(e.expected_event_version_id for e in events),
            patch_ids=tuple(p.patch_id for p in patches),
            legacy_ref_ids=tuple(r.legacy_ref_id for r in legacy),
        ),
    )
    version_hash = content_digest(
        {
            "manifest_content_hash": manifest.content_hash,
            "parent_state_version_id": None if parent is None else parent.hex,
            "schema_version": 1,
        }
    )
    return ResearchStateVersion(
        state_version_id=research_state_version_id(
            manifest_content_hash=manifest.content_hash,
            parent_id=parent,
            schema_version=1,
        ),
        parent_state_version_id=parent,
        manifest=manifest,
        event_time=_TS - timedelta(hours=1),
        effective_as_of=effective,
        known_at=known,
        recorded_at=max(known, _TS),
        schema_version=1,
        content_hash=version_hash,
        provenance=_PROV,
    )


def _seed_base(
    store: ResearchStateStore,
) -> tuple[EvidenceRecord, BeliefVersion, ResearchStateVersion]:
    evidence = _evidence()
    belief = _belief(evidence=evidence)
    store.append_evidence(evidence)
    store.append_belief(belief)
    version = _version(evidence=(evidence,), beliefs=(belief,))
    store.append_state_version(version)
    return evidence, belief, version


def test_content_idempotency_skips_exact_retry() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    first = store.append_evidence(evidence)
    second = store.append_evidence(evidence)
    assert first is second
    assert len(store._evidence) == 1


def test_changed_content_appends_new_row() -> None:
    store = ResearchStateStore()
    a = _evidence(summary="First filing")
    b = _evidence(summary="Amended filing")
    assert a.evidence_id != b.evidence_id
    store.append_evidence(a)
    store.append_evidence(b)
    assert set(store._evidence) == {a.evidence_id, b.evidence_id}


def test_belief_supersession_requires_parent() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    child = _belief(
        evidence=evidence,
        statement="Soft-landing challenged",
        supersedes_version_id=uuid4(),
    )
    with pytest.raises(ResearchStateError, match="missing parent"):
        store.append_belief(child)


def test_belief_supersession_appends_child() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    parent = _belief(evidence=evidence)
    store.append_belief(parent)
    child = _belief(
        evidence=evidence,
        statement="Soft-landing challenged after CPI",
        supersedes_version_id=parent.belief_version_id,
    )
    store.append_belief(child)
    assert parent.belief_version_id in store._beliefs
    assert child.belief_version_id in store._beliefs


def test_state_version_requires_manifest_entities() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    version = _version(evidence=(evidence,))
    with pytest.raises(ResearchStateError, match="missing evidence"):
        store.append_state_version(version)


def test_state_version_requires_parent() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    orphan = _version(evidence=(evidence,), parent=uuid4())
    with pytest.raises(ResearchStateError, match="missing parent"):
        store.append_state_version(orphan)


def test_select_state_as_of_excludes_future_known() -> None:
    store = ResearchStateStore()
    _, _, early = _seed_base(store)
    later_evidence = _evidence(summary="Later filing")
    store.append_evidence(later_evidence)
    later_belief = _belief(
        evidence=later_evidence,
        statement="Updated after cutoff",
    )
    store.append_belief(later_belief)
    later = _version(
        evidence=(later_evidence,),
        beliefs=(later_belief,),
        known_at=_TS + timedelta(hours=2),
        effective_as_of=_TS + timedelta(hours=1),
        parent=early.state_version_id,
    )
    store.append_state_version(later)

    selected = store.select_state_as_of(
        requested_as_of=_TS + timedelta(hours=3),
        knowledge_cutoff_at=_TS + timedelta(minutes=30),
    )
    assert selected is not None
    assert selected.state_version_id == early.state_version_id


def test_select_state_as_of_skips_legacy_only_manifests() -> None:
    store = ResearchStateStore()
    legacy = _legacy()
    store.append_legacy_ref(legacy)
    legacy_only = _version(legacy=(legacy,))
    store.append_state_version(legacy_only)
    assert store.select_state_as_of(requested_as_of=_TS, knowledge_cutoff_at=_TS) is None


def test_pin_state_for_run_and_idempotent_retry() -> None:
    store = ResearchStateStore()
    _, _, version = _seed_base(store)
    pin = ResearchStatePin(
        run_id="run-1",
        attempt_id="attempt-1",
        state_version_id=version.state_version_id,
        knowledge_cutoff_at=_TS + timedelta(minutes=1),
        requested_as_of=_TS,
        pinned_at=_TS + timedelta(minutes=2),
    )
    first = store.pin_state_for_run(pin)
    second = store.pin_state_for_run(pin)
    assert first is second
    assert store.get_pin(run_id="run-1", attempt_id="attempt-1") == pin


def test_pin_rejects_future_known_version() -> None:
    store = ResearchStateStore()
    evidence = _evidence(summary="Cutoff envelope")
    belief = _belief(evidence=evidence)
    store.append_evidence(evidence)
    store.append_belief(belief)
    # effective_as_of stays within the pin's requested_as_of; known_at is after cutoff.
    version = _version(
        evidence=(evidence,),
        beliefs=(belief,),
        effective_as_of=_TS - timedelta(minutes=30),
        known_at=_TS,
    )
    store.append_state_version(version)
    pin = ResearchStatePin(
        run_id="run-1",
        attempt_id="attempt-1",
        state_version_id=version.state_version_id,
        knowledge_cutoff_at=_TS - timedelta(minutes=15),
        requested_as_of=_TS - timedelta(minutes=20),
        pinned_at=_TS - timedelta(minutes=15),
    )
    with pytest.raises(ResearchStateError, match="after knowledge_cutoff"):
        store.pin_state_for_run(pin)


def test_pin_rejects_effective_as_of_after_requested() -> None:
    store = ResearchStateStore()
    evidence = _evidence(summary="Future effective")
    belief = _belief(evidence=evidence, statement="Future-effective belief")
    store.append_evidence(evidence)
    store.append_belief(belief)
    future = _version(
        evidence=(evidence,),
        beliefs=(belief,),
        effective_as_of=_TS + timedelta(hours=2),
        known_at=_TS + timedelta(hours=2),
    )
    store.append_state_version(future)
    pin = ResearchStatePin(
        run_id="run-1",
        attempt_id="attempt-1",
        state_version_id=future.state_version_id,
        knowledge_cutoff_at=_TS + timedelta(hours=3),
        requested_as_of=_TS,
        pinned_at=_TS + timedelta(hours=3),
    )
    with pytest.raises(ResearchStateError, match="effective_as_of is after requested_as_of"):
        store.pin_state_for_run(pin)


def test_pin_rejects_future_known_child_even_when_envelope_ok() -> None:
    """Defense in depth when durable state was seeded inconsistently."""
    store = ResearchStateStore()
    early = _evidence(summary="Early", known_at=_TS - timedelta(minutes=45))
    late = _evidence(summary="Late", known_at=_TS + timedelta(hours=1))
    store.append_evidence(early)
    store.append_evidence(late)
    version = _version(evidence=(early, late), known_at=_TS + timedelta(hours=1))
    store.append_state_version(version)
    # Simulate durable drift: child known_at moved past cutoff after append.
    drifted = EvidenceRecord.model_construct(**late.model_dump())
    object.__setattr__(drifted, "known_at", _TS + timedelta(hours=3))
    store._evidence[late.evidence_id] = drifted

    pin = ResearchStatePin(
        run_id="run-1",
        attempt_id="attempt-1",
        state_version_id=version.state_version_id,
        knowledge_cutoff_at=_TS + timedelta(hours=2),
        requested_as_of=_TS,
        pinned_at=_TS + timedelta(hours=2),
    )
    with pytest.raises(ResearchStateError, match="evidence .* after knowledge_cutoff"):
        store.pin_state_for_run(pin)


def test_append_state_version_rejects_child_after_version_known_at() -> None:
    store = ResearchStateStore()
    early = _evidence(summary="Early", known_at=_TS - timedelta(minutes=45))
    late = _evidence(summary="Late", known_at=_TS + timedelta(hours=2))
    store.append_evidence(early)
    store.append_evidence(late)
    version = _version(evidence=(early, late), known_at=_TS)
    with pytest.raises(ResearchStateError, match="after state version known_at"):
        store.append_state_version(version)


def test_pin_conflict_on_different_content() -> None:
    store = ResearchStateStore()
    evidence, belief, version = _seed_base(store)
    other_evidence = _evidence(summary="Sibling filing")
    store.append_evidence(other_evidence)
    other_belief = _belief(evidence=other_evidence, statement="Sibling belief")
    store.append_belief(other_belief)
    other = _version(
        evidence=(other_evidence,),
        beliefs=(other_belief,),
        parent=version.state_version_id,
        known_at=_TS + timedelta(minutes=1),
    )
    store.append_state_version(other)

    store.pin_state_for_run(
        ResearchStatePin(
            run_id="run-1",
            attempt_id="attempt-1",
            state_version_id=version.state_version_id,
            knowledge_cutoff_at=_TS + timedelta(hours=1),
            requested_as_of=_TS,
            pinned_at=_TS + timedelta(hours=1),
        )
    )
    with pytest.raises(ResearchStateConflict):
        store.pin_state_for_run(
            ResearchStatePin(
                run_id="run-1",
                attempt_id="attempt-1",
                state_version_id=other.state_version_id,
                knowledge_cutoff_at=_TS + timedelta(hours=1),
                requested_as_of=_TS,
                pinned_at=_TS + timedelta(hours=1),
            )
        )


def test_exact_version_round_trip_after_newer_rows() -> None:
    store = ResearchStateStore()
    evidence, belief, version = _seed_base(store)
    original_bytes = store.exact_version_bytes(version.state_version_id)

    later_evidence = _evidence(summary="Post-pin filing")
    store.append_evidence(later_evidence)
    later_belief = _belief(evidence=later_evidence, statement="Post-pin belief")
    store.append_belief(later_belief)
    later = _version(
        evidence=(later_evidence,),
        beliefs=(later_belief,),
        parent=version.state_version_id,
        known_at=_TS + timedelta(hours=3),
        effective_as_of=_TS + timedelta(hours=2),
    )
    store.append_state_version(later)

    loaded = store.load_state_version(version.state_version_id, strict=True)
    assert loaded.version == version
    assert loaded.evidence == (evidence,)
    assert loaded.beliefs == (belief,)
    assert loaded.legacy_refs == ()
    assert store.exact_version_bytes(version.state_version_id) == original_bytes
    assert loaded.version.model_dump_json().encode("utf-8") == original_bytes


def test_strict_load_excludes_legacy_refs() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    legacy = _legacy()
    store.append_legacy_ref(legacy)
    version = _version(evidence=(evidence,), legacy=(legacy,))
    store.append_state_version(version)

    strict = store.load_state_version(version.state_version_id, strict=True)
    assert strict.legacy_refs == ()
    assert strict.evidence == (evidence,)

    loose = store.load_state_version(version.state_version_id, strict=False)
    assert loose.legacy_refs == (legacy,)


def test_strict_load_excludes_future_known_entities() -> None:
    store = ResearchStateStore()
    # Children must be known by the version envelope; cutoff may still be stricter.
    early = _evidence(summary="Early", known_at=_TS - timedelta(minutes=45))
    late = _evidence(summary="Late", known_at=_TS + timedelta(hours=2))
    store.append_evidence(early)
    store.append_evidence(late)
    version = _version(evidence=(early, late), known_at=_TS + timedelta(hours=2))
    store.append_state_version(version)

    loaded = store.load_state_version(
        version.state_version_id,
        strict=True,
        knowledge_cutoff_at=_TS,
    )
    assert [e.evidence_id for e in loaded.evidence] == [early.evidence_id]


def test_load_missing_raises() -> None:
    store = ResearchStateStore()
    with pytest.raises(ResearchStateMissingError):
        store.load_state_version(uuid4())


def test_conflict_on_seeded_hash_mismatch() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    # Simulate durable drift: same PK already stored under a different hash.
    tainted = EvidenceRecord.model_construct(**evidence.model_dump())
    object.__setattr__(tainted, "content_hash", "0" * 64)
    store._evidence[evidence.evidence_id] = tainted
    with pytest.raises(ResearchStateConflict):
        store.append_evidence(evidence)


def test_append_patch_and_event_round_trip() -> None:
    store = ResearchStateStore()
    evidence = _evidence()
    store.append_evidence(evidence)
    event = _event(evidence=evidence)
    patch = _patch()
    store.append_expected_event(event)
    store.append_patch(patch)
    version = _version(evidence=(evidence,), events=(event,), patches=(patch,))
    store.append_state_version(version)
    loaded = store.load_state_version(version.state_version_id)
    assert loaded.expected_events == (event,)
    assert loaded.patches == (patch,)
