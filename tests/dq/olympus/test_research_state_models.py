"""Frozen research-state contracts (#2841 / WP12.1).

Red coverage: frozen/extra-forbid, UTC temporal order, typed provenance,
immutable tuples, canonical IDs independent of input ordering, parent /
supersession validation, reconstructability from typed source/version IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.research_retrieval.models import (
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
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-abc",
    attempt_id="attempt-1",
    artifact_id="artifact-h5",
)


def _evidence(**overrides: object) -> EvidenceRecord:
    belief_a = UUID("11111111-1111-4111-8111-111111111111")
    belief_b = UUID("22222222-2222-4222-8222-222222222222")
    fields: dict[str, object] = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary="Filed 8-K item 2.02",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        provenance=_PROV,
        affected_belief_ids=(belief_b, belief_a),
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    fields.update(overrides)
    content_hash = evidence_content_hash(
        source=str(fields["source"]),
        authority=str(fields["authority"]),
        summary=str(fields["summary"]),
        affected_belief_ids=tuple(fields["affected_belief_ids"]),  # type: ignore[arg-type]
        novelty_of=tuple(fields["novelty_of"]),  # type: ignore[arg-type]
        contradiction_of=tuple(fields["contradiction_of"]),  # type: ignore[arg-type]
        supersedes_evidence_id=fields.get("supersedes_evidence_id"),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "evidence_id",
        evidence_record_id(
            source=str(fields["source"]),
            authority=str(fields["authority"]),
            content_hash=str(fields["content_hash"]),
        ),
    )
    return EvidenceRecord(**fields)


def _belief(**overrides: object) -> BeliefVersion:
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    ev = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    fields: dict[str, object] = dict(
        belief_id=belief_id,
        statement="USD soft-landing remains base case",
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(ev,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%", "unemployment > 5%"),
        supersedes_version_id=None,
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
        recorded_at=_TS,
        provenance=_PROV,
    )
    fields.update(overrides)
    content_hash = belief_content_hash(
        belief_id=fields["belief_id"],  # type: ignore[arg-type]
        statement=str(fields["statement"]),
        confidence=fields["confidence"],  # type: ignore[arg-type]
        horizon_sessions=int(fields["horizon_sessions"]),  # type: ignore[arg-type]
        status=fields["status"],  # type: ignore[arg-type]
        supporting_evidence_ids=tuple(fields["supporting_evidence_ids"]),  # type: ignore[arg-type]
        counter_evidence_ids=tuple(fields["counter_evidence_ids"]),  # type: ignore[arg-type]
        invalidation_rules=tuple(fields["invalidation_rules"]),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "belief_version_id",
        belief_version_id(
            belief_id=fields["belief_id"],  # type: ignore[arg-type]
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return BeliefVersion(**fields)


def _expected_event(**overrides: object) -> ExpectedEventVersion:
    event_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    fields: dict[str, object] = dict(
        expected_event_id=event_id,
        label="FOMC decision",
        status=ExpectedEventStatus.OPEN,
        event_time=_TS + timedelta(days=5),
        supporting_evidence_ids=(),
        supersedes_version_id=None,
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS,
        recorded_at=_TS + timedelta(minutes=1),
        provenance=_PROV,
    )
    fields.update(overrides)
    content_hash = expected_event_content_hash(
        expected_event_id=fields["expected_event_id"],  # type: ignore[arg-type]
        label=str(fields["label"]),
        status=fields["status"],  # type: ignore[arg-type]
        event_time=fields["event_time"],  # type: ignore[arg-type]
        supporting_evidence_ids=tuple(fields["supporting_evidence_ids"]),  # type: ignore[arg-type]
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "expected_event_version_id",
        expected_event_version_id(
            expected_event_id=fields["expected_event_id"],  # type: ignore[arg-type]
            content_hash=str(fields["content_hash"]),
            supersedes_version_id=fields.get("supersedes_version_id"),  # type: ignore[arg-type]
        ),
    )
    return ExpectedEventVersion(**fields)


def _patch(**overrides: object) -> ResearchPatch:
    fields: dict[str, object] = dict(
        target_kind=PatchTargetKind.SECTION,
        target_id="macro:rates",
        mode=PatchMode.SECTION_PATCH,
        summary="Refresh rates section after CPI",
        supersedes_patch_id=None,
        event_time=_TS - timedelta(hours=1),
        effective_as_of=_TS - timedelta(minutes=30),
        known_at=_TS - timedelta(minutes=10),
        recorded_at=_TS,
        provenance=_PROV,
    )
    fields.update(overrides)
    content_hash = research_patch_content_hash(
        target_kind=fields["target_kind"],  # type: ignore[arg-type]
        target_id=str(fields["target_id"]),
        mode=fields["mode"],  # type: ignore[arg-type]
        summary=str(fields["summary"]),
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "patch_id",
        research_patch_id(
            target_kind=fields["target_kind"].value,  # type: ignore[union-attr]
            target_id=str(fields["target_id"]),
            content_hash=str(fields["content_hash"]),
            supersedes_patch_id=fields.get("supersedes_patch_id"),  # type: ignore[arg-type]
        ),
    )
    return ResearchPatch(**fields)


def _manifest(**overrides: object) -> ResearchStateManifest:
    evidence = _evidence()
    belief = _belief()
    event = _expected_event()
    patch = _patch()
    legacy = LegacyDocumentRef(
        document_key="macro",
        as_of_date="2026-08-20",
        source_table="documents",
        source_hash="abc123",
        legacy_ref_id=legacy_document_ref_id(
            document_key="macro",
            as_of_date="2026-08-20",
            source_hash="abc123",
        ),
    )
    fields: dict[str, object] = dict(
        evidence_ids=(evidence.evidence_id,),
        belief_version_ids=(belief.belief_version_id,),
        expected_event_version_ids=(event.expected_event_version_id,),
        patch_ids=(patch.patch_id,),
        legacy_ref_ids=(legacy.legacy_ref_id,),
    )
    fields.update(overrides)
    fields.setdefault(
        "content_hash",
        manifest_content_hash(
            evidence_ids=tuple(fields["evidence_ids"]),  # type: ignore[arg-type]
            belief_version_ids=tuple(fields["belief_version_ids"]),  # type: ignore[arg-type]
            expected_event_version_ids=tuple(fields["expected_event_version_ids"]),  # type: ignore[arg-type]
            patch_ids=tuple(fields["patch_ids"]),  # type: ignore[arg-type]
            legacy_ref_ids=tuple(fields["legacy_ref_ids"]),  # type: ignore[arg-type]
        ),
    )
    return ResearchStateManifest(**fields)


def _state_version(**overrides: object) -> ResearchStateVersion:
    manifest = overrides.pop("manifest", None) if "manifest" in overrides else _manifest()
    fields: dict[str, object] = dict(
        manifest=manifest,
        parent_state_version_id=None,
        event_time=_TS - timedelta(hours=4),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
        recorded_at=_TS,
        provenance=_PROV,
    )
    fields.update(overrides)
    manifest_obj: ResearchStateManifest = fields["manifest"]  # type: ignore[assignment]
    parent = fields.get("parent_state_version_id")
    content_hash = content_digest(
        {
            "manifest_content_hash": manifest_obj.content_hash,
            "parent_state_version_id": None if parent is None else parent.hex,  # type: ignore[union-attr]
            "schema_version": int(fields.get("schema_version", 1)),
        }
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "state_version_id",
        research_state_version_id(
            manifest_content_hash=manifest_obj.content_hash,
            parent_id=parent,  # type: ignore[arg-type]
            schema_version=int(fields.get("schema_version", 1)),
        ),
    )
    return ResearchStateVersion(**fields)


class TestFrozenAndExtraForbid:
    def test_models_are_frozen(self) -> None:
        evidence = _evidence()
        with pytest.raises(ValidationError):
            evidence.summary = "mutated"  # type: ignore[misc]

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            TypedProvenance(
                source_run_id="r",
                attempt_id="a",
                artifact_id="x",
                unexpected="nope",  # type: ignore[call-arg]
            )


class TestTemporalOrder:
    def test_rejects_non_utc(self) -> None:
        from datetime import timezone

        eastern = timezone(timedelta(hours=-4))
        with pytest.raises(ValidationError, match="UTC"):
            _evidence(event_time=datetime(2026, 8, 26, 8, 0, tzinfo=eastern))

    def test_rejects_known_before_event(self) -> None:
        with pytest.raises(ValidationError, match="known_at"):
            _evidence(
                event_time=_TS,
                effective_as_of=_TS,
                known_at=_TS - timedelta(hours=1),
                recorded_at=_TS,
            )

    def test_expected_event_allows_future_event_time(self) -> None:
        event = _expected_event(event_time=_TS + timedelta(days=10))
        assert event.event_time > event.known_at


class TestCanonicalOrdering:
    def test_evidence_id_independent_of_belief_list_order(self) -> None:
        a = UUID("11111111-1111-4111-8111-111111111111")
        b = UUID("22222222-2222-4222-8222-222222222222")
        left = _evidence(affected_belief_ids=(a, b))
        right = _evidence(affected_belief_ids=(b, a))
        assert left.evidence_id == right.evidence_id
        assert left.content_hash == right.content_hash
        assert left.affected_belief_ids == (a, b)

    def test_manifest_hash_independent_of_input_order(self) -> None:
        e1, e2 = uuid4(), uuid4()
        left = _manifest(
            evidence_ids=(e1, e2),
            belief_version_ids=(),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
        )
        right = _manifest(
            evidence_ids=(e2, e1),
            belief_version_ids=(),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
        )
        assert left.content_hash == right.content_hash
        assert left.evidence_ids == tuple(sorted((e1, e2), key=lambda u: u.hex))


class TestSupersessionAndParent:
    def test_evidence_rejects_self_supersession(self) -> None:
        # Lineage is part of content_hash, so a helper-built child cannot collide
        # with its parent id. Hand-craft equal ids to exercise the lineage guard.
        fake_id = uuid4()
        content_hash = evidence_content_hash(
            source="ingest:sec_8k",
            authority="edgar",
            summary="Filed 8-K item 2.02",
            supersedes_evidence_id=fake_id,
        )
        with pytest.raises(ValidationError, match="cannot supersede itself"):
            EvidenceRecord(
                evidence_id=fake_id,
                source="ingest:sec_8k",
                authority="edgar",
                summary="Filed 8-K item 2.02",
                event_time=_TS - timedelta(hours=2),
                effective_as_of=_TS - timedelta(hours=1),
                known_at=_TS - timedelta(minutes=30),
                recorded_at=_TS,
                content_hash=content_hash,
                provenance=_PROV,
                supersedes_evidence_id=fake_id,
            )

    def test_state_version_rejects_self_parent(self) -> None:
        manifest = _manifest()
        fake_id = uuid4()
        content_hash = content_digest(
            {
                "manifest_content_hash": manifest.content_hash,
                "parent_state_version_id": fake_id.hex,
                "schema_version": 1,
            }
        )
        with pytest.raises(ValidationError, match="cannot supersede itself"):
            ResearchStateVersion(
                state_version_id=fake_id,
                parent_state_version_id=fake_id,
                manifest=manifest,
                event_time=_TS - timedelta(hours=4),
                effective_as_of=_TS - timedelta(hours=2),
                known_at=_TS - timedelta(hours=1),
                recorded_at=_TS,
                content_hash=content_hash,
                provenance=_PROV,
            )


class TestReconstructability:
    def test_entities_round_trip_from_typed_ids(self) -> None:
        evidence = _evidence()
        belief = _belief()
        event = _expected_event()
        patch = _patch()
        legacy = LegacyDocumentRef(
            document_key="macro",
            as_of_date="2026-08-20",
            source_table="documents",
            source_hash="abc123",
            legacy_ref_id=legacy_document_ref_id(
                document_key="macro",
                as_of_date="2026-08-20",
                source_hash="abc123",
            ),
        )
        assert evidence.evidence_id == evidence_record_id(
            source=evidence.source,
            authority=evidence.authority,
            content_hash=evidence.content_hash,
        )
        assert belief.belief_version_id == belief_version_id(
            belief_id=belief.belief_id,
            content_hash=belief.content_hash,
            supersedes_version_id=belief.supersedes_version_id,
        )
        assert event.expected_event_version_id == expected_event_version_id(
            expected_event_id=event.expected_event_id,
            content_hash=event.content_hash,
            supersedes_version_id=event.supersedes_version_id,
        )
        assert patch.patch_id == research_patch_id(
            target_kind=patch.target_kind.value,
            target_id=patch.target_id,
            content_hash=patch.content_hash,
            supersedes_patch_id=patch.supersedes_patch_id,
        )
        assert legacy.legacy_ref_id == legacy_document_ref_id(
            document_key=legacy.document_key,
            as_of_date=legacy.as_of_date,
            source_hash=legacy.source_hash,
        )
        assert legacy.known_at is None
        assert legacy.legacy_manifest_only is True

    def test_state_version_and_pin(self) -> None:
        version = _state_version()
        pin = ResearchStatePin(
            run_id="run-abc",
            attempt_id="attempt-1",
            state_version_id=version.state_version_id,
            knowledge_cutoff_at=_TS,
            requested_as_of=_TS - timedelta(minutes=5),
            pinned_at=_TS + timedelta(seconds=1),
        )
        assert pin.state_version_id == version.state_version_id
        assert version.provenance.source_run_id == "run-abc"
        dumped = version.model_dump(mode="json")
        restored = ResearchStateVersion.model_validate(dumped)
        assert restored == version


class TestNoRawDictBoundaries:
    def test_provenance_is_typed_model(self) -> None:
        evidence = _evidence()
        assert isinstance(evidence.provenance, TypedProvenance)
        assert isinstance(evidence.affected_belief_ids, tuple)


class TestIdentityHardening:
    """Regression for #2856 — PK/idempotency formulas must not collide."""

    def test_patch_id_includes_supersession_lineage(self) -> None:
        parent = uuid4()
        left = _patch(supersedes_patch_id=None)
        right = _patch(supersedes_patch_id=parent)
        assert left.patch_id != right.patch_id

    def test_state_version_id_includes_schema_version(self) -> None:
        v1 = _state_version(schema_version=1)
        v2 = _state_version(schema_version=2)
        assert v1.state_version_id != v2.state_version_id
        assert v1.content_hash != v2.content_hash

    def test_evidence_id_includes_supersedes_lineage(self) -> None:
        parent = uuid4()
        left = _evidence(supersedes_evidence_id=None)
        right = _evidence(supersedes_evidence_id=parent)
        assert left.evidence_id != right.evidence_id
        assert left.content_hash != right.content_hash

    def test_pin_rejects_requested_as_of_after_cutoff(self) -> None:
        version = _state_version()
        with pytest.raises(ValidationError, match="requested_as_of"):
            ResearchStatePin(
                run_id="run-abc",
                attempt_id="attempt-1",
                state_version_id=version.state_version_id,
                knowledge_cutoff_at=_TS,
                requested_as_of=_TS + timedelta(days=1),
                pinned_at=_TS + timedelta(seconds=1),
            )

    def test_manifest_dedupes_duplicate_ids(self) -> None:
        dup = uuid4()
        manifest = _manifest(
            evidence_ids=(dup, dup),
            belief_version_ids=(),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
        )
        assert manifest.evidence_ids == (dup,)
