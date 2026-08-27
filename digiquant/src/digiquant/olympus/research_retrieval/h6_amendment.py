"""Bounded H6 missing-fact evidence supplement (#2908 / WP11.4).

Validated :class:`~digiquant.olympus.hermes.models.deliberation.MissingFactProposal`
→ targeted retrieval → append-only :class:`EvidenceBundleAmendment`. Generic H6 web
search is forbidden; invalid/exhausted/failed paths never fall back to broad search.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from digiquant.olympus.hermes.models.deliberation import MissingFactProposal
from digiquant.olympus.research_retrieval.blinding import research_document_allowed
from digiquant.olympus.research_retrieval.evidence_bundle import H5EvidenceFact
from digiquant.olympus.research_retrieval.models import (
    EvidenceBundleAmendment,
    EvidenceRecord,
    MissingFactRequest,
    NonEmptyStr,
    TickerEvidenceBundle,
    TypedProvenance,
    evidence_bundle_amendment_content_hash,
    evidence_bundle_amendment_id,
    evidence_content_hash,
    evidence_record_id,
    missing_fact_request_content_hash,
    missing_fact_request_id,
)
from digiquant.olympus.research_retrieval.store import EvidenceBundleStore

logger = logging.getLogger(__name__)

H6_AMENDMENT_POLICY_MAX_PER_BASE = 1
_H6_AMENDMENT_SOURCE = "h6:missing_fact"

ExecuteTool = Callable[[str, dict[str, Any]], str]


class H6AmendmentOutcome(StrEnum):
    """Result of one bounded missing-fact supplement attempt."""

    NONE = "none"
    ACCEPTED = "accepted"
    INVALID_REQUEST = "invalid_request"
    POLICY_EXHAUSTED = "policy_exhausted"
    RETRIEVAL_FAILED = "retrieval_failed"
    BLINDED_SOURCE = "blinded_source"


class H6AmendmentResult(BaseModel):
    """Audit record linking proposal → request → amendment (or failure)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: H6AmendmentOutcome
    base_bundle_id: UUID
    base_content_hash: NonEmptyStr
    missing_fact_request: MissingFactRequest | None = None
    amendment: EvidenceBundleAmendment | None = None
    failure_reason: str | None = None
    supplemental_evidence: tuple[EvidenceRecord, ...] = ()


def document_key_for_source_kind(source_kind: str, ticker: str) -> str:
    """Map one source kind to a blinded research document key."""
    kind = source_kind.strip().lower()
    sym = ticker.strip().upper()
    if kind == "analyst":
        return f"analyst/{sym}"
    if kind in {"digest", "macro", "equity", "institutional", "altdata", "sectors"}:
        return kind
    return kind


def _missing_fact_rationale(proposal: MissingFactProposal) -> str:
    return (
        f"question={proposal.question.strip()}; reason={proposal.reason.strip()}; "
        f"source_kind={proposal.source_kind.strip().lower()}"
    )


def validate_missing_fact_proposal(
    proposal: MissingFactProposal,
    base_bundle: TickerEvidenceBundle,
) -> str | None:
    """Return failure reason when the proposal is not eligible for retrieval."""
    if not proposal.claim_id.strip():
        return "missing_claim_id"
    if not proposal.question.strip():
        return "missing_question"
    if not proposal.reason.strip():
        return "missing_reason"
    if not proposal.source_kind.strip():
        return "missing_source_kind"
    claim = proposal.claim_id.strip()
    allowed = {str(item) for item in base_bundle.evidence_ids} | {str(base_bundle.bundle_id)}
    if claim not in allowed:
        return "claim_id_not_in_base_bundle"
    document_key = document_key_for_source_kind(proposal.source_kind, base_bundle.ticker)
    if not research_document_allowed("h6_deliberation", document_key):
        return "source_kind_blinded"
    return None


def _facts_from_research_payload(
    *,
    payload: dict[str, Any],
    document_key: str,
    knowledge_cutoff_at: datetime,
) -> tuple[H5EvidenceFact, ...]:
    """Extract at most one supplemental fact leaf from a targeted research row."""
    body = payload.get("body")
    if body is None:
        body = payload.get("summary") or payload.get("thesis") or payload.get("content")
    if not isinstance(body, str) or not body.strip():
        return ()
    summary = body.strip()[:500]
    return (
        H5EvidenceFact(
            source=document_key[:500],
            authority="h6_missing_fact",
            summary=summary,
            event_time=knowledge_cutoff_at,
            effective_as_of=knowledge_cutoff_at,
            known_at=knowledge_cutoff_at,
        ),
    )


def _materialize_supplemental_evidence(
    *,
    facts: tuple[H5EvidenceFact, ...],
    recorded_at: datetime,
    provenance: TypedProvenance,
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for fact in facts:
        digest = evidence_content_hash(
            source=fact.source,
            authority=fact.authority,
            summary=fact.summary,
        )
        evidence_id = evidence_record_id(
            source=fact.source,
            authority=fact.authority,
            content_hash=digest,
        )
        records.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                source=fact.source,
                authority=fact.authority,
                summary=fact.summary,
                event_time=fact.event_time,
                effective_as_of=fact.effective_as_of,
                known_at=fact.known_at,
                recorded_at=recorded_at,
                content_hash=digest,
                provenance=provenance,
            )
        )
    return tuple(records)


def retrieve_missing_fact_evidence(
    *,
    proposal: MissingFactProposal,
    ticker: str,
    execute_tool: ExecuteTool | None,
    knowledge_cutoff_at: datetime,
    provenance: TypedProvenance,
    recorded_at: datetime,
) -> tuple[tuple[EvidenceRecord, ...], str | None]:
    """Targeted document retrieval only — never generic web search."""
    if execute_tool is None:
        return (), "retrieval_tools_unavailable"
    document_key = document_key_for_source_kind(proposal.source_kind, ticker)
    if not research_document_allowed("h6_deliberation", document_key):
        return (), "source_kind_blinded"
    try:
        raw = execute_tool("query_research", {"document_key": document_key})
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "H6 missing-fact retrieval failed for %s (%s: %s)",
            document_key,
            type(exc).__name__,
            exc,
        )
        return (), "retrieval_failed"
    if not isinstance(parsed, dict):
        return (), "retrieval_empty"
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return (), "retrieval_empty"
    facts = _facts_from_research_payload(
        payload=payload,
        document_key=document_key,
        knowledge_cutoff_at=knowledge_cutoff_at,
    )
    if not facts:
        return (), "retrieval_empty"
    return _materialize_supplemental_evidence(
        facts=facts,
        recorded_at=recorded_at,
        provenance=provenance,
    ), None


def _materialize_missing_fact_request(
    *,
    proposal: MissingFactProposal,
    base_bundle: TickerEvidenceBundle,
    recorded_at: datetime,
    provenance: TypedProvenance,
) -> MissingFactRequest:
    rationale = _missing_fact_rationale(proposal)
    content_hash = missing_fact_request_content_hash(
        base_bundle_id=base_bundle.bundle_id,
        fact_key=proposal.claim_id.strip(),
        rationale=rationale,
    )
    return MissingFactRequest(
        request_id=missing_fact_request_id(
            base_bundle_id=base_bundle.bundle_id,
            fact_key=proposal.claim_id.strip(),
            content_hash=content_hash,
        ),
        base_bundle_id=base_bundle.bundle_id,
        ticker=base_bundle.ticker,
        fact_key=proposal.claim_id.strip(),
        rationale=rationale,
        event_time=base_bundle.event_time,
        effective_as_of=base_bundle.effective_as_of,
        known_at=base_bundle.known_at,
        recorded_at=recorded_at,
        content_hash=content_hash,
        provenance=provenance,
    )


def _materialize_amendment(
    *,
    base_bundle: TickerEvidenceBundle,
    request: MissingFactRequest,
    evidence: tuple[EvidenceRecord, ...],
    recorded_at: datetime,
    provenance: TypedProvenance,
) -> EvidenceBundleAmendment:
    evidence_ids = tuple(item.evidence_id for item in evidence)
    content_hash = evidence_bundle_amendment_content_hash(
        base_bundle_id=base_bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        evidence_ids=evidence_ids,
        source=_H6_AMENDMENT_SOURCE,
    )
    if evidence:
        event_time = min(item.event_time for item in evidence)
        effective_as_of = max(item.effective_as_of for item in evidence)
        known_at = max(item.known_at for item in evidence)
    else:
        event_time = recorded_at
        effective_as_of = recorded_at
        known_at = recorded_at
    return EvidenceBundleAmendment(
        amendment_id=evidence_bundle_amendment_id(
            base_bundle_id=base_bundle.bundle_id,
            missing_fact_request_id=request.request_id,
            content_hash=content_hash,
        ),
        base_bundle_id=base_bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        ticker=base_bundle.ticker,
        evidence_ids=evidence_ids,
        source=_H6_AMENDMENT_SOURCE,
        event_time=event_time,
        effective_as_of=effective_as_of,
        known_at=known_at,
        recorded_at=recorded_at,
        content_hash=content_hash,
        provenance=provenance,
    )


def attempt_h6_evidence_amendment(
    *,
    proposal: MissingFactProposal,
    base_bundle: TickerEvidenceBundle,
    ticker: str,
    execute_tool: ExecuteTool | None,
    store: EvidenceBundleStore | None,
    recorded_at: datetime,
    provenance: TypedProvenance,
) -> H6AmendmentResult:
    """Validate, retrieve, and optionally persist one H6 evidence amendment."""
    base_hash = base_bundle.content_hash
    if store is not None and (
        store.amendment_count_for_base(base_bundle.bundle_id) >= H6_AMENDMENT_POLICY_MAX_PER_BASE
    ):
        return H6AmendmentResult(
            outcome=H6AmendmentOutcome.POLICY_EXHAUSTED,
            base_bundle_id=base_bundle.bundle_id,
            base_content_hash=base_hash,
            failure_reason="amendment_policy_exhausted",
        )

    invalid = validate_missing_fact_proposal(proposal, base_bundle)
    if invalid is not None:
        return H6AmendmentResult(
            outcome=H6AmendmentOutcome.INVALID_REQUEST,
            base_bundle_id=base_bundle.bundle_id,
            base_content_hash=base_hash,
            failure_reason=invalid,
        )

    evidence, retrieval_error = retrieve_missing_fact_evidence(
        proposal=proposal,
        ticker=ticker,
        execute_tool=execute_tool,
        knowledge_cutoff_at=recorded_at,
        provenance=provenance,
        recorded_at=recorded_at,
    )
    if retrieval_error is not None:
        outcome = (
            H6AmendmentOutcome.BLINDED_SOURCE
            if retrieval_error == "source_kind_blinded"
            else H6AmendmentOutcome.RETRIEVAL_FAILED
        )
        return H6AmendmentResult(
            outcome=outcome,
            base_bundle_id=base_bundle.bundle_id,
            base_content_hash=base_hash,
            failure_reason=retrieval_error,
        )

    request = _materialize_missing_fact_request(
        proposal=proposal,
        base_bundle=base_bundle,
        recorded_at=recorded_at,
        provenance=provenance,
    )
    amendment = _materialize_amendment(
        base_bundle=base_bundle,
        request=request,
        evidence=evidence,
        recorded_at=recorded_at,
        provenance=provenance,
    )

    if store is not None:
        try:
            store.append_missing_fact_request(request)
            store.append_amendment(amendment)
        except Exception as exc:
            logger.warning(
                "H6 amendment store append failed for %s (%s: %s); continuing with base bundle",
                ticker,
                type(exc).__name__,
                exc,
            )
            return H6AmendmentResult(
                outcome=H6AmendmentOutcome.RETRIEVAL_FAILED,
                base_bundle_id=base_bundle.bundle_id,
                base_content_hash=base_hash,
                missing_fact_request=request,
                failure_reason="store_append_failed",
                supplemental_evidence=evidence,
            )

    return H6AmendmentResult(
        outcome=H6AmendmentOutcome.ACCEPTED,
        base_bundle_id=base_bundle.bundle_id,
        base_content_hash=base_hash,
        missing_fact_request=request,
        amendment=amendment,
        supplemental_evidence=evidence,
    )


__all__ = [
    "H6_AMENDMENT_POLICY_MAX_PER_BASE",
    "H6AmendmentOutcome",
    "H6AmendmentResult",
    "attempt_h6_evidence_amendment",
    "document_key_for_source_kind",
    "retrieve_missing_fact_evidence",
    "validate_missing_fact_proposal",
]
