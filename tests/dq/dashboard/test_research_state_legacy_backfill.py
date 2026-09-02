"""WP12.4 legacy research-state inventory backfill (#2870).

Covers dry-run / apply / idempotency / count reconciliation / strict exclusion
of legacy inventory from ResearchStateStore strict loads. Never fabricates
evidence, beliefs, events, or known_at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from digiquant.olympus.research_retrieval.legacy_backfill import (
    BackfillCounts,
    LegacySourceDocument,
    backfill_legacy_manifests,
    build_legacy_document_ref,
)
from digiquant.olympus.research_retrieval.models import (
    EvidenceRecord,
    ResearchStateManifest,
    ResearchStateVersion,
    TypedProvenance,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    legacy_document_ref_id,
    manifest_content_hash,
    research_state_version_id,
)
from digiquant.olympus.research_retrieval.store import ResearchStateStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 20, 15, 0, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-backfill",
    attempt_id="1",
    artifact_id="art-backfill",
    writer_role="olympus",
)
_DEFAULT_PAYLOAD = {"title": "macro", "body": "legacy prose"}


def _source(
    *,
    key: str = "macro",
    as_of: str = "2026-08-20",
    payload: object | None = ...,  # type: ignore[assignment]
    source_table: str = "documents",
) -> LegacySourceDocument:
    body: object | None
    if payload is ...:
        body = dict(_DEFAULT_PAYLOAD)
    else:
        body = payload
    return LegacySourceDocument(
        document_key=key,
        as_of_date=as_of,
        source_table=source_table,
        payload=body,
    )


def _evidence() -> EvidenceRecord:
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary="Filed 8-K item 2.02",
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


def _version_with_legacy(
    *,
    evidence: EvidenceRecord,
    legacy_ref_id,
) -> ResearchStateVersion:
    manifest = ResearchStateManifest(
        evidence_ids=(evidence.evidence_id,),
        belief_version_ids=(),
        expected_event_version_ids=(),
        patch_ids=(),
        legacy_ref_ids=(legacy_ref_id,),
        content_hash=manifest_content_hash(
            evidence_ids=(evidence.evidence_id,),
            belief_version_ids=(),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(legacy_ref_id,),
        ),
    )
    version_hash = content_digest(
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
        event_time=_TS - timedelta(hours=1),
        effective_as_of=_TS - timedelta(minutes=5),
        known_at=_TS,
        recorded_at=_TS,
        schema_version=1,
        content_hash=version_hash,
        provenance=_PROV,
    )


def test_build_legacy_ref_hashes_payload_and_forces_null_known_at() -> None:
    source = _source(payload={"k": "v"})
    ref = build_legacy_document_ref(source)
    assert ref is not None
    assert ref.known_at is None
    assert ref.legacy_manifest_only is True
    assert ref.source_hash == content_digest({"k": "v"})
    assert ref.legacy_ref_id == legacy_document_ref_id(
        document_key="macro",
        as_of_date="2026-08-20",
        source_hash=ref.source_hash,
    )


@pytest.mark.parametrize(
    "source",
    [
        _source(key="", payload={"a": 1}),
        _source(as_of="not-a-date", payload={"a": 1}),
        _source(payload=None),
    ],
)
def test_build_legacy_ref_unverifiable(source: LegacySourceDocument) -> None:
    assert build_legacy_document_ref(source) is None


def test_dry_run_counts_without_writing() -> None:
    store = ResearchStateStore()
    sources = [_source(key="a"), _source(key="b"), _source(payload=None)]
    counts = backfill_legacy_manifests(sources, store, apply=False)
    assert counts == BackfillCounts(source=3, inserted=2, skipped=0, unverifiable=1)
    expected_id = legacy_document_ref_id(
        document_key="a",
        as_of_date="2026-08-20",
        source_hash=content_digest(_DEFAULT_PAYLOAD),
    )
    assert store.get_legacy_ref(expected_id) is None
    assert store._evidence == {}
    assert store._beliefs == {}
    assert store._expected_events == {}


def test_apply_inserts_legacy_only_and_reconciles() -> None:
    store = ResearchStateStore()
    sources = [
        _source(key="macro"),
        _source(key="digest"),
        _source(key="", payload={"x": 1}),
    ]
    counts = backfill_legacy_manifests(sources, store, apply=True)
    assert counts == BackfillCounts(source=3, inserted=2, skipped=0, unverifiable=1)
    assert len(store._legacy_refs) == 2
    assert store._evidence == {}
    assert store._beliefs == {}
    assert store._expected_events == {}
    assert store._patches == {}


def test_apply_is_idempotent() -> None:
    store = ResearchStateStore()
    sources = [_source(key="macro"), _source(key="digest")]
    first = backfill_legacy_manifests(sources, store, apply=True)
    second = backfill_legacy_manifests(sources, store, apply=True)
    assert first == BackfillCounts(source=2, inserted=2, skipped=0, unverifiable=0)
    assert second == BackfillCounts(source=2, inserted=0, skipped=2, unverifiable=0)
    assert len(store._legacy_refs) == 2


def test_strict_readers_exclude_legacy_inventory() -> None:
    store = ResearchStateStore()
    counts = backfill_legacy_manifests([_source(key="macro")], store, apply=True)
    assert counts.inserted == 1

    ref = next(iter(store._legacy_refs.values()))
    evidence = _evidence()
    store.append_evidence(evidence)
    version = _version_with_legacy(evidence=evidence, legacy_ref_id=ref.legacy_ref_id)
    store.append_state_version(version)

    strict = store.load_state_version(version.state_version_id, strict=True)
    assert strict.legacy_refs == ()
    assert strict.evidence == (evidence,)

    loose = store.load_state_version(version.state_version_id, strict=False)
    assert loose.legacy_refs == (ref,)


def test_backfill_counts_reject_irreconcilable() -> None:
    with pytest.raises(ValueError, match="reconcile"):
        BackfillCounts(source=2, inserted=1, skipped=0, unverifiable=0)


def test_conflict_different_content_is_unverifiable() -> None:
    from digiquant.olympus.research_retrieval.models import LegacyDocumentRef

    store = ResearchStateStore()
    first = backfill_legacy_manifests([_source(payload={"v": 1})], store, apply=True)
    assert first.inserted == 1
    planted = build_legacy_document_ref(_source(payload={"v": 2}))
    assert planted is not None
    # Corrupt store to simulate same id / different content (bypasses model validators).
    store._legacy_refs[planted.legacy_ref_id] = LegacyDocumentRef.model_construct(
        legacy_ref_id=planted.legacy_ref_id,
        document_key=planted.document_key,
        as_of_date=planted.as_of_date,
        source_table=planted.source_table,
        source_hash="deadbeef" * 8,
        known_at=None,
        legacy_manifest_only=True,
    )
    counts = backfill_legacy_manifests([_source(payload={"v": 2})], store, apply=True)
    assert counts == BackfillCounts(source=1, inserted=0, skipped=0, unverifiable=1)
