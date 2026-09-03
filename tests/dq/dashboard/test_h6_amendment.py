"""WP11.4 — bounded H6 missing-fact amendment (#2908).

One validated proposal → targeted retrieval → append-only amendment. No generic
H6 web search; invalid/exhausted/failed requests never fall back to broad search.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from digiquant.dashboard.research_retrieval.evidence_bundle import build_h5_evidence_bundle
from digiquant.dashboard.research_retrieval.h6_amendment import (
    H6_AMENDMENT_POLICY_MAX_PER_BASE,
    H6AmendmentOutcome,
    attempt_h6_evidence_amendment,
    document_key_for_source_kind,
    validate_missing_fact_proposal,
)
from digiquant.dashboard.research_retrieval.models import (
    TypedProvenance,
    missing_fact_request_content_hash,
    missing_fact_request_id,
)
from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore
from digiquant.portfolio.models.deliberation import MissingFactProposal

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_STATE = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_PROV = TypedProvenance(
    source_run_id="run-h6-amend",
    attempt_id="attempt-1",
    artifact_id="artifact-h6",
)


def _base_bundle(*, evidence_count: int = 1):
    from digiquant.dashboard.research_retrieval.evidence_bundle import H5EvidenceFact

    facts = tuple(
        H5EvidenceFact(
            source=f"src-{index}",
            authority="analyst_doc",
            summary=f"fact {index}",
            event_time=_TS - timedelta(hours=1),
            effective_as_of=_TS - timedelta(minutes=30),
            known_at=_TS - timedelta(minutes=20),
        )
        for index in range(evidence_count)
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-h6-amend",
        attempt_id="attempt-1",
        state_version_id=_STATE,
        facts=facts,
        recorded_at=_TS,
        provenance=_PROV,
    )
    return built.bundle, built.evidence


def _proposal(*, claim_id: str, source_kind: str = "analyst") -> MissingFactProposal:
    return MissingFactProposal(
        claim_id=claim_id,
        question="When is the next earnings date?",
        source_kind=source_kind,  # type: ignore[arg-type]
        reason="PM challenge requires dated catalyst",
    )


def test_validate_requires_claim_in_base_bundle() -> None:
    bundle, evidence = _base_bundle()
    ok = validate_missing_fact_proposal(_proposal(claim_id=str(evidence[0].evidence_id)), bundle)
    assert ok is None
    assert validate_missing_fact_proposal(_proposal(claim_id="not-in-base"), bundle) == (
        "claim_id_not_in_base_bundle"
    )


def test_validate_rejects_empty_fields() -> None:
    bundle, evidence = _base_bundle()
    claim = str(evidence[0].evidence_id)
    empty_question = MissingFactProposal.model_construct(
        claim_id=claim,
        question="",
        source_kind="analyst",
        reason="need date",
    )
    assert validate_missing_fact_proposal(empty_question, bundle) == "missing_question"
    empty_reason = MissingFactProposal.model_construct(
        claim_id=claim,
        question="q?",
        source_kind="analyst",
        reason="",
    )
    assert validate_missing_fact_proposal(empty_reason, bundle) == "missing_reason"


def test_document_key_for_source_kind_analyst_is_ticker_scoped() -> None:
    assert document_key_for_source_kind("analyst", "aapl") == "analyst/AAPL"
    assert document_key_for_source_kind("digest", "AAPL") == "digest"


def test_successful_amendment_links_request_evidence_and_amendment() -> None:
    store = EvidenceBundleStore()
    bundle, evidence = _base_bundle()
    store.append_base_bundle(bundle)
    proposal = _proposal(claim_id=str(evidence[0].evidence_id))

    def execute_tool(name: str, args: dict[str, object]) -> str:
        assert name == "query_research"
        assert args["document_key"] == "analyst/AAPL"
        return json.dumps(
            {
                "payload": {
                    "body": "Next earnings on 2026-10-28.",
                    "ticker": "AAPL",
                }
            }
        )

    result = attempt_h6_evidence_amendment(
        proposal=proposal,
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=execute_tool,
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert result.outcome is H6AmendmentOutcome.ACCEPTED
    assert result.base_content_hash == bundle.content_hash
    assert result.missing_fact_request is not None
    assert result.amendment is not None
    assert result.amendment.base_bundle_id == bundle.bundle_id
    assert result.amendment.missing_fact_request_id == result.missing_fact_request.request_id
    assert result.amendment.evidence_ids
    assert store.amendment_count_for_base(bundle.bundle_id) == 1


def test_policy_cap_refuses_second_amendment() -> None:
    store = EvidenceBundleStore()
    bundle, evidence = _base_bundle()
    store.append_base_bundle(bundle)
    proposal = _proposal(claim_id=str(evidence[0].evidence_id))

    def execute_tool(_name: str, _args: dict[str, object]) -> str:
        return json.dumps({"payload": {"body": "supplement"}})

    first = attempt_h6_evidence_amendment(
        proposal=proposal,
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=execute_tool,
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert first.outcome is H6AmendmentOutcome.ACCEPTED
    second = attempt_h6_evidence_amendment(
        proposal=proposal,
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=execute_tool,
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert second.outcome is H6AmendmentOutcome.POLICY_EXHAUSTED
    assert store.amendment_count_for_base(bundle.bundle_id) == H6_AMENDMENT_POLICY_MAX_PER_BASE


def test_retrieval_failure_records_outcome_without_broad_search() -> None:
    store = EvidenceBundleStore()
    bundle, evidence = _base_bundle()
    store.append_base_bundle(bundle)
    result = attempt_h6_evidence_amendment(
        proposal=_proposal(claim_id=str(evidence[0].evidence_id)),
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=None,
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert result.outcome is H6AmendmentOutcome.RETRIEVAL_FAILED
    assert result.amendment is None
    assert result.failure_reason == "retrieval_tools_unavailable"
    assert store.amendment_count_for_base(bundle.bundle_id) == 0


def test_invalid_proposal_never_persists_request() -> None:
    store = EvidenceBundleStore()
    bundle, _evidence = _base_bundle()
    store.append_base_bundle(bundle)
    result = attempt_h6_evidence_amendment(
        proposal=_proposal(claim_id="missing-claim"),
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=lambda _n, _a: "{}",
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert result.outcome is H6AmendmentOutcome.INVALID_REQUEST
    assert store.amendment_count_for_base(bundle.bundle_id) == 0
    assert len(store._requests) == 0  # type: ignore[attr-defined]


def test_missing_fact_request_id_is_deterministic() -> None:
    bundle, evidence = _base_bundle()
    proposal = _proposal(claim_id=str(evidence[0].evidence_id))
    rationale = (
        f"question={proposal.question.strip()}; reason={proposal.reason.strip()}; "
        f"source_kind={proposal.source_kind}"
    )
    content_hash = missing_fact_request_content_hash(
        base_bundle_id=bundle.bundle_id,
        fact_key=proposal.claim_id.strip(),
        rationale=rationale,
    )
    expected = missing_fact_request_id(
        base_bundle_id=bundle.bundle_id,
        fact_key=proposal.claim_id.strip(),
        content_hash=content_hash,
    )
    store = EvidenceBundleStore()
    store.append_base_bundle(bundle)

    def execute_tool(_name: str, _args: dict[str, object]) -> str:
        return json.dumps({"payload": {"body": "dated catalyst"}})

    result = attempt_h6_evidence_amendment(
        proposal=proposal,
        base_bundle=bundle,
        ticker="AAPL",
        execute_tool=execute_tool,
        store=store,
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert result.missing_fact_request is not None
    assert result.missing_fact_request.request_id == expected
