"""Frozen ticker evidence-bundle contracts (#2844 / WP11.1).

Red coverage: immutable base; amendment references one base + one missing-fact
request; ticker/run/state/evidence/known-time/source/hash lineage; no generic
blob fields; UUID5 identity independent of evidence-list ordering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from digiquant.dashboard.research_retrieval.models import (
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
from pydantic import ValidationError

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


def _bundle(**overrides: object) -> TickerEvidenceBundle:
    fields: dict[str, object] = dict(
        ticker="AAPL",
        source_run_id="run-wp111",
        attempt_id="attempt-1",
        state_version_id=_STATE,
        evidence_ids=(_EV_B, _EV_A),
        source="h5:grounding",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        provenance=_PROV,
    )
    fields.update(overrides)
    evidence_ids = tuple(fields["evidence_ids"])  # type: ignore[arg-type]
    content_hash = ticker_evidence_bundle_content_hash(
        ticker=str(fields["ticker"]),
        state_version_id=fields["state_version_id"],  # type: ignore[arg-type]
        evidence_ids=evidence_ids,
        source=str(fields["source"]),
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "bundle_id",
        ticker_evidence_bundle_id(
            source_run_id=str(fields["source_run_id"]),
            ticker=str(fields["ticker"]),
            content_hash=str(fields["content_hash"]),
        ),
    )
    return TickerEvidenceBundle(**fields)


def _request(bundle: TickerEvidenceBundle, **overrides: object) -> MissingFactRequest:
    fields: dict[str, object] = dict(
        base_bundle_id=bundle.bundle_id,
        ticker=bundle.ticker,
        fact_key="next_earnings_date",
        rationale="H6 needs dated catalyst for challenge",
        event_time=bundle.event_time,
        effective_as_of=bundle.effective_as_of,
        known_at=bundle.known_at,
        recorded_at=bundle.recorded_at,
        provenance=_PROV,
    )
    fields.update(overrides)
    content_hash = missing_fact_request_content_hash(
        base_bundle_id=fields["base_bundle_id"],  # type: ignore[arg-type]
        fact_key=str(fields["fact_key"]),
        rationale=str(fields["rationale"]),
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "request_id",
        missing_fact_request_id(
            base_bundle_id=fields["base_bundle_id"],  # type: ignore[arg-type]
            fact_key=str(fields["fact_key"]),
            content_hash=str(fields["content_hash"]),
        ),
    )
    return MissingFactRequest(**fields)


def _amendment(
    bundle: TickerEvidenceBundle,
    request: MissingFactRequest,
    **overrides: object,
) -> EvidenceBundleAmendment:
    extra = UUID("33333333-3333-4333-8333-333333333333")
    fields: dict[str, object] = dict(
        base_bundle_id=bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        ticker=bundle.ticker,
        evidence_ids=(extra,),
        source="h6:missing_fact",
        event_time=_TS - timedelta(minutes=20),
        effective_as_of=_TS - timedelta(minutes=10),
        known_at=_TS - timedelta(minutes=5),
        recorded_at=_TS,
        provenance=_PROV,
    )
    fields.update(overrides)
    evidence_ids = tuple(fields["evidence_ids"])  # type: ignore[arg-type]
    content_hash = evidence_bundle_amendment_content_hash(
        base_bundle_id=fields["base_bundle_id"],  # type: ignore[arg-type]
        missing_fact_request_id=fields["missing_fact_request_id"],  # type: ignore[arg-type]
        evidence_ids=evidence_ids,
        source=str(fields["source"]),
    )
    fields.setdefault("content_hash", content_hash)
    fields.setdefault(
        "amendment_id",
        evidence_bundle_amendment_id(
            base_bundle_id=fields["base_bundle_id"],  # type: ignore[arg-type]
            missing_fact_request_id=fields["missing_fact_request_id"],  # type: ignore[arg-type]
            content_hash=str(fields["content_hash"]),
        ),
    )
    return EvidenceBundleAmendment(**fields)


def test_bundle_is_frozen_and_forbids_extra() -> None:
    bundle = _bundle()
    with pytest.raises(ValidationError):
        bundle.ticker = "MSFT"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        TickerEvidenceBundle(**{**bundle.model_dump(), "blob": {"x": 1}})


def test_bundle_sorts_evidence_ids_for_stable_identity() -> None:
    left = _bundle(evidence_ids=(_EV_A, _EV_B))
    right = _bundle(evidence_ids=(_EV_B, _EV_A))
    assert left.bundle_id == right.bundle_id
    assert left.content_hash == right.content_hash
    assert left.evidence_ids == (_EV_A, _EV_B)


def test_bundle_rejects_bad_hash_or_id() -> None:
    with pytest.raises(ValidationError, match="content_hash"):
        _bundle(content_hash="0" * 64)
    good = _bundle()
    with pytest.raises(ValidationError, match="bundle_id"):
        _bundle(bundle_id=uuid4(), content_hash=good.content_hash)


def test_bundle_requires_utc_temporal_lineage() -> None:
    naive = _TS.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        _bundle(known_at=naive)


def test_amendment_must_name_base_and_request() -> None:
    bundle = _bundle()
    request = _request(bundle)
    amendment = _amendment(bundle, request)
    assert amendment.base_bundle_id == bundle.bundle_id
    assert amendment.missing_fact_request_id == request.request_id
    with pytest.raises(ValidationError, match="content_hash|amendment_id"):
        _amendment(bundle, request, amendment_id=uuid4())


def test_request_and_amendment_carry_ticker_lineage_fields() -> None:
    bundle = _bundle()
    request = _request(bundle)
    amendment = _amendment(bundle, request)
    assert request.ticker == bundle.ticker
    assert amendment.ticker == bundle.ticker
    assert request.base_bundle_id == bundle.bundle_id
    assert amendment.base_bundle_id == bundle.bundle_id
