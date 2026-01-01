"""WP12.5 compiled research-state prose views (#2877).

Covers determinism after newer rows, embedded IDs/hash/schema, sorted entities,
and fail-closed publish when structured write did not succeed.
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
    ResearchStateManifest,
    ResearchStateVersion,
    TypedProvenance,
    belief_content_hash,
    belief_version_id,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    expected_event_content_hash,
    expected_event_version_id,
    manifest_content_hash,
    research_state_version_id,
)
from digiquant.dashboard.research_retrieval.store import ResearchStateStore
from digiquant.dashboard.research_retrieval.views import (
    COMPILED_BRIEF_DOCUMENT_KEY,
    COMPILED_DIGEST_DOCUMENT_KEY,
    VIEW_SCHEMA_VERSION,
    ResearchViewKind,
    ResearchViewPublishBlocked,
    compile_research_brief,
    compile_research_digest,
    compile_views_from_store,
    document_key_for_view,
    publish_compiled_views,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-wp125",
    attempt_id="attempt-1",
    artifact_id="artifact-views",
)


def _evidence(*, summary: str) -> EvidenceRecord:
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary=summary,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
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
        supersedes_evidence_id=None,
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


def _belief(*, evidence: EvidenceRecord, statement: str) -> BeliefVersion:
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
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
        supersedes_version_id=None,
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _event(*, evidence: EvidenceRecord, label: str) -> ExpectedEventVersion:
    event_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    content_hash = expected_event_content_hash(
        expected_event_id=event_id,
        label=label,
        status=ExpectedEventStatus.OPEN,
        event_time=_TS + timedelta(days=5),
        supporting_evidence_ids=(evidence.evidence_id,),
    )
    return ExpectedEventVersion(
        expected_event_version_id=expected_event_version_id(
            expected_event_id=event_id,
            content_hash=content_hash,
            supersedes_version_id=None,
        ),
        expected_event_id=event_id,
        label=label,
        status=ExpectedEventStatus.OPEN,
        event_time=_TS + timedelta(days=5),
        supporting_evidence_ids=(evidence.evidence_id,),
        supersedes_version_id=None,
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _version(
    *,
    evidence: tuple[EvidenceRecord, ...],
    beliefs: tuple[BeliefVersion, ...],
    events: tuple[ExpectedEventVersion, ...],
) -> ResearchStateVersion:
    manifest_hash = manifest_content_hash(
        evidence_ids=tuple(item.evidence_id for item in evidence),
        belief_version_ids=tuple(item.belief_version_id for item in beliefs),
        expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
    )
    manifest = ResearchStateManifest(
        evidence_ids=tuple(item.evidence_id for item in evidence),
        belief_version_ids=tuple(item.belief_version_id for item in beliefs),
        expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
        patch_ids=(),
        legacy_ref_ids=(),
        content_hash=manifest_hash,
    )
    state_hash = content_digest(
        {
            "manifest_content_hash": manifest.content_hash,
            "parent_state_version_id": None,
            "schema_version": 1,
        }
    )
    return ResearchStateVersion(
        state_version_id=research_state_version_id(
            manifest_content_hash=manifest.content_hash,
            parent_id=None,
            schema_version=1,
        ),
        parent_state_version_id=None,
        manifest=manifest,
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=state_hash,
        provenance=_PROV,
    )


def _seed_store() -> tuple[ResearchStateStore, ResearchStateVersion]:
    store = ResearchStateStore()
    e_a = _evidence(summary="Filed 8-K item 2.02 A")
    e_b = _evidence(summary="Filed 8-K item 2.02 B")
    # Insert in reverse UUID order so compiler must re-sort.
    for record in (e_b, e_a):
        store.append_evidence(record)
    belief = _belief(evidence=e_a, statement="Soft-landing remains base case")
    store.append_belief(belief)
    event = _event(evidence=e_a, label="FOMC decision")
    store.append_expected_event(event)
    version = _version(evidence=(e_a, e_b), beliefs=(belief,), events=(event,))
    store.append_state_version(version)
    return store, version


def test_compile_brief_embeds_state_ids_hash_and_schema() -> None:
    store, version = _seed_store()
    loaded = store.load_state_version(version.state_version_id, strict=True)
    view = compile_research_brief(loaded)

    assert view.kind is ResearchViewKind.BRIEF
    assert view.state_version_id == version.state_version_id
    assert view.state_content_hash == version.content_hash
    assert view.state_schema_version == version.schema_version
    assert view.manifest_content_hash == version.manifest.content_hash
    assert view.view_schema_version == VIEW_SCHEMA_VERSION
    assert f"state_version_id: {version.state_version_id}" in view.markdown
    assert f"state_content_hash: {version.content_hash}" in view.markdown
    assert f"state_schema_version: {version.schema_version}" in view.markdown
    assert f"view_schema_version: {VIEW_SCHEMA_VERSION}" in view.markdown
    assert view.content_hash == content_digest(
        {
            "kind": "brief",
            "state_version_id": version.state_version_id.hex,
            "state_content_hash": version.content_hash,
            "state_schema_version": version.schema_version,
            "manifest_content_hash": version.manifest.content_hash,
            "view_schema_version": VIEW_SCHEMA_VERSION,
            "markdown": view.markdown,
        }
    )


def test_same_version_compiles_byte_identically_after_newer_rows() -> None:
    store, version = _seed_store()
    brief_a, digest_a = compile_views_from_store(store, version.state_version_id)

    newer = _evidence(summary=f"Later filing {uuid4()}")
    store.append_evidence(newer)
    later_hash = manifest_content_hash(evidence_ids=(newer.evidence_id,))
    later_manifest = ResearchStateManifest(
        evidence_ids=(newer.evidence_id,),
        belief_version_ids=(),
        expected_event_version_ids=(),
        patch_ids=(),
        legacy_ref_ids=(),
        content_hash=later_hash,
    )
    later_state_hash = content_digest(
        {
            "manifest_content_hash": later_manifest.content_hash,
            "parent_state_version_id": version.state_version_id.hex,
            "schema_version": 1,
        }
    )
    store.append_state_version(
        ResearchStateVersion(
            state_version_id=research_state_version_id(
                manifest_content_hash=later_manifest.content_hash,
                parent_id=version.state_version_id,
                schema_version=1,
            ),
            parent_state_version_id=version.state_version_id,
            manifest=later_manifest,
            event_time=_TS,
            effective_as_of=_TS,
            known_at=_TS,
            recorded_at=_TS + timedelta(minutes=1),
            schema_version=1,
            content_hash=later_state_hash,
            provenance=_PROV,
        )
    )

    brief_b, digest_b = compile_views_from_store(store, version.state_version_id)
    assert brief_a.markdown.encode("utf-8") == brief_b.markdown.encode("utf-8")
    assert digest_a.markdown.encode("utf-8") == digest_b.markdown.encode("utf-8")
    assert brief_a.content_hash == brief_b.content_hash
    assert digest_a.content_hash == digest_b.content_hash


def test_entities_sorted_by_id_in_compiled_markdown() -> None:
    store, version = _seed_store()
    loaded = store.load_state_version(version.state_version_id, strict=True)
    # Deliberately shuffle bags before compile.
    shuffled = loaded.__class__(
        version=loaded.version,
        evidence=tuple(reversed(loaded.evidence)),
        beliefs=loaded.beliefs,
        expected_events=loaded.expected_events,
        patches=loaded.patches,
        legacy_refs=loaded.legacy_refs,
    )
    view = compile_research_brief(shuffled)
    evidence_ids = [item.evidence_id.hex for item in shuffled.evidence]
    assert evidence_ids != sorted(evidence_ids)
    ordered = sorted(shuffled.evidence, key=lambda item: item.evidence_id.hex)
    positions = [view.markdown.index(str(item.evidence_id)) for item in ordered]
    assert positions == sorted(positions)


def test_publish_fail_closed_when_structured_write_failed() -> None:
    store, version = _seed_store()
    brief, digest = compile_views_from_store(store, version.state_version_id)
    published: list[str] = []

    with pytest.raises(ResearchViewPublishBlocked, match="structured research-state write failed"):
        publish_compiled_views(
            views=(brief, digest),
            structured_write_ok=False,
            publisher=lambda view: published.append(view.kind.value),
        )
    assert published == []


def test_publish_succeeds_when_structured_path_safe() -> None:
    store, version = _seed_store()
    brief, digest = compile_views_from_store(store, version.state_version_id)
    published: list[str] = []
    out = publish_compiled_views(
        views=(brief, digest),
        structured_write_ok=True,
        publisher=lambda view: published.append(document_key_for_view(view.kind)),
    )
    assert published == [COMPILED_BRIEF_DOCUMENT_KEY, COMPILED_DIGEST_DOCUMENT_KEY]
    assert out == (brief, digest)


def test_digest_embeds_exact_state_version() -> None:
    store, version = _seed_store()
    loaded = store.load_state_version(version.state_version_id, strict=True)
    view = compile_research_digest(loaded)
    assert view.kind is ResearchViewKind.DIGEST
    assert f"state_version_id: {version.state_version_id}" in view.markdown
    assert "beliefs: 1" in view.markdown
    assert "evidence: 2" in view.markdown
