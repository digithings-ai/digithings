"""Append-only ticker evidence-bundle store (#2844 / WP11.1).

Covers immutable base append, content-idempotent retry, run/ticker uniqueness,
amendment linkage to one base + one missing-fact request, and zero unlinked
amendments. Migration privacy contracts live in ``tests/dq/atlas/test_migration_090.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.research_retrieval.models import (
    EvidenceBundleAmendment,
    MissingFactRequest,
    TickerEvidenceBundle,
    TypedProvenance,
    evidence_bundle_amendment_content_hash,
    evidence_bundle_amendment_id,
    missing_fact_request_content_hash,
    missing_fact_request_id,
    ticker_evidence_bundle_content_hash,
    ticker_evidence_bundle_id,
)
from digiquant.olympus.research_retrieval.store import (
    EvidenceBundleConflict,
    EvidenceBundleError,
    EvidenceBundleMissingError,
    EvidenceBundleStore,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-wp111",
    attempt_id="attempt-1",
    artifact_id="artifact-h5-bundle",
)
_STATE = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_EV_A = UUID("11111111-1111-4111-8111-111111111111")
_EV_B = UUID("22222222-2222-4222-8222-222222222222")


def _bundle(
    *,
    ticker: str = "AAPL",
    run_id: str = "run-wp111",
    evidence_ids: tuple[UUID, ...] = (_EV_A, _EV_B),
    source: str = "h5:grounding",
) -> TickerEvidenceBundle:
    content_hash = ticker_evidence_bundle_content_hash(
        ticker=ticker,
        state_version_id=_STATE,
        evidence_ids=evidence_ids,
        source=source,
    )
    return TickerEvidenceBundle(
        bundle_id=ticker_evidence_bundle_id(
            source_run_id=run_id,
            ticker=ticker,
            content_hash=content_hash,
        ),
        ticker=ticker,
        source_run_id=run_id,
        attempt_id="attempt-1",
        state_version_id=_STATE,
        evidence_ids=evidence_ids,
        source=source,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV.model_copy(update={"source_run_id": run_id}),
    )


def _request(
    bundle: TickerEvidenceBundle, *, fact_key: str = "next_earnings_date"
) -> MissingFactRequest:
    content_hash = missing_fact_request_content_hash(
        base_bundle_id=bundle.bundle_id,
        fact_key=fact_key,
        rationale="H6 needs dated catalyst for challenge",
    )
    return MissingFactRequest(
        request_id=missing_fact_request_id(
            base_bundle_id=bundle.bundle_id,
            fact_key=fact_key,
            content_hash=content_hash,
        ),
        base_bundle_id=bundle.bundle_id,
        ticker=bundle.ticker,
        fact_key=fact_key,
        rationale="H6 needs dated catalyst for challenge",
        event_time=bundle.event_time,
        effective_as_of=bundle.effective_as_of,
        known_at=bundle.known_at,
        recorded_at=bundle.recorded_at,
        schema_version=1,
        content_hash=content_hash,
        provenance=bundle.provenance,
    )


def _amendment(
    bundle: TickerEvidenceBundle,
    request: MissingFactRequest,
    *,
    evidence_ids: tuple[UUID, ...] | None = None,
) -> EvidenceBundleAmendment:
    ids = (
        evidence_ids
        if evidence_ids is not None
        else (UUID("33333333-3333-4333-8333-333333333333"),)
    )
    content_hash = evidence_bundle_amendment_content_hash(
        base_bundle_id=bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        evidence_ids=ids,
        source="h6:missing_fact",
    )
    return EvidenceBundleAmendment(
        amendment_id=evidence_bundle_amendment_id(
            base_bundle_id=bundle.bundle_id,
            missing_fact_request_id=request.request_id,
            content_hash=content_hash,
        ),
        base_bundle_id=bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        ticker=bundle.ticker,
        evidence_ids=ids,
        source="h6:missing_fact",
        event_time=_TS - timedelta(minutes=20),
        effective_as_of=_TS - timedelta(minutes=10),
        known_at=_TS - timedelta(minutes=5),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=bundle.provenance,
    )


def test_exact_retry_of_base_bundle_is_idempotent() -> None:
    store = EvidenceBundleStore()
    bundle = _bundle()
    assert store.append_base_bundle(bundle) is store.append_base_bundle(bundle)
    assert store.load_base_bundle(bundle.bundle_id) == bundle


def test_second_base_for_same_run_ticker_different_content_conflicts() -> None:
    store = EvidenceBundleStore()
    store.append_base_bundle(_bundle(source="h5:grounding"))
    with pytest.raises(EvidenceBundleConflict, match="run/ticker"):
        store.append_base_bundle(_bundle(source="h5:alt"))


def test_metric_one_base_per_run_ticker_content() -> None:
    store = EvidenceBundleStore()
    a = store.append_base_bundle(_bundle(ticker="AAPL"))
    b = store.append_base_bundle(_bundle(ticker="MSFT"))
    assert (
        store.base_bundle_count_for(run_id="run-wp111", ticker="AAPL", content_hash=a.content_hash)
        == 1
    )
    assert (
        store.base_bundle_count_for(run_id="run-wp111", ticker="MSFT", content_hash=b.content_hash)
        == 1
    )
    assert store.unlinked_amendment_count() == 0


def test_amendment_requires_existing_base_and_request() -> None:
    store = EvidenceBundleStore()
    bundle = _bundle()
    request = _request(bundle)
    amendment = _amendment(bundle, request)
    with pytest.raises(EvidenceBundleError, match="missing base"):
        store.append_amendment(amendment)
    store.append_base_bundle(bundle)
    with pytest.raises(EvidenceBundleError, match="missing missing-fact request"):
        store.append_amendment(amendment)
    store.append_missing_fact_request(request)
    stored = store.append_amendment(amendment)
    assert stored.amendment_id == amendment.amendment_id
    assert store.unlinked_amendment_count() == 0


def test_request_must_reference_existing_base() -> None:
    store = EvidenceBundleStore()
    bundle = _bundle()
    with pytest.raises(EvidenceBundleError, match="missing base"):
        store.append_missing_fact_request(_request(bundle))
    store.append_base_bundle(bundle)
    store.append_missing_fact_request(_request(bundle))


def test_amendment_exact_retry_idempotent() -> None:
    store = EvidenceBundleStore()
    bundle = store.append_base_bundle(_bundle())
    request = store.append_missing_fact_request(_request(bundle))
    first = _amendment(bundle, request)
    assert store.append_amendment(first) is store.append_amendment(first)


def test_request_and_amendment_ticker_must_match_base() -> None:
    store = EvidenceBundleStore()
    bundle = store.append_base_bundle(_bundle(ticker="AAPL"))
    bad_request = _request(bundle).model_copy(update={"ticker": "MSFT"})
    with pytest.raises(EvidenceBundleError, match="ticker"):
        store.append_missing_fact_request(bad_request)
    request = store.append_missing_fact_request(_request(bundle))
    bad_amendment = _amendment(bundle, request).model_copy(update={"ticker": "MSFT"})
    with pytest.raises(EvidenceBundleError, match="ticker"):
        store.append_amendment(bad_amendment)


def test_load_missing_raises() -> None:
    store = EvidenceBundleStore()
    with pytest.raises(EvidenceBundleMissingError):
        store.load_base_bundle(uuid4())


def test_dump_snapshot_roundtrip_is_byte_equivalent() -> None:
    store = EvidenceBundleStore()
    bundle = store.append_base_bundle(_bundle(ticker="AAPL"))
    request = store.append_missing_fact_request(_request(bundle))
    store.append_amendment(_amendment(bundle, request))
    msft = store.append_base_bundle(_bundle(ticker="MSFT"))
    snapshot = store.dump_snapshot()
    reloaded = EvidenceBundleStore.from_snapshot(snapshot)
    assert reloaded.lineage_bytes() == snapshot
    assert reloaded.load_base_bundle(bundle.bundle_id) == bundle
    assert reloaded.load_base_bundle(msft.bundle_id) == msft
    assert reloaded.amendment_count_for_base(bundle.bundle_id) == 1
    assert reloaded.unlinked_amendment_count() == 0
