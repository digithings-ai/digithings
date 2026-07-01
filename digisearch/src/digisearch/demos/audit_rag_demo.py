"""Audit RAG demo for assertion-driven, corroborated DigiSearch workflows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from digisearch.core.models import Chunk, Query, Result
from digisearch.search import add_chunks, get_stub_index, query_index


class Verdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNCONFIRMED = "UNCONFIRMED"


@dataclass(frozen=True)
class AuditAssertion:
    step_id: str
    title: str
    query: str
    required_doc_types: tuple[str, ...]
    min_evidence: int = 1


@dataclass(frozen=True)
class Citation:
    doc_id: str
    chunk_id: str
    score: float


@dataclass(frozen=True)
class Finding:
    assertion: AuditAssertion
    verdict: Verdict
    evidence_count: int
    doc_types_covered: tuple[str, ...]
    top_citation: Citation | None
    gaps: tuple[str, ...]


def _is_stub_mode() -> bool:
    return os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in {"1", "true", "yes"}


def _stub_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="fs-1",
            doc_id="financials-2025-q4",
            content=(
                "Related-party loan approved by the board was disclosed in financial statement "
                "note 14 with amount and maturity details."
            ),
            metadata={"doc_type": "financial_statement", "chunk_id": "fs-1"},
        ),
        Chunk(
            id="bm-1",
            doc_id="board-minutes-2025-11-04",
            content=(
                "Board minutes confirm the related-party loan approved, including rationale "
                "and conflict-of-interest disclosures."
            ),
            metadata={"doc_type": "board_minutes", "chunk_id": "bm-1"},
        ),
        Chunk(
            id="bm-2",
            doc_id="board-minutes-2025-09-15",
            content=(
                "Revenue recognition policy changed for bundled contracts after audit committee "
                "review."
            ),
            metadata={"doc_type": "board_minutes", "chunk_id": "bm-2"},
        ),
    ]


def _extract_doc_type(result: Result) -> str:
    metadata = result.chunk.metadata
    for key in ("doc_type", "document_type", "sourceType", "source_type", "type"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _top_citation(results: list[Result]) -> Citation | None:
    if not results:
        return None
    best = max(results, key=lambda item: item.score)
    chunk_id = str(best.chunk.metadata.get("chunk_id") or best.chunk.id)
    return Citation(doc_id=best.chunk.doc_id, chunk_id=chunk_id, score=best.score)


def evaluate_assertion(assertion: AuditAssertion, index_name: str) -> Finding:
    response = query_index(Query(text=assertion.query, top_k=8), index_name=index_name)
    results = response.results
    evidence_count = len(results)
    doc_types_seen = sorted({_extract_doc_type(hit) for hit in results})

    gaps: list[str] = []
    missing_types = sorted(set(assertion.required_doc_types).difference(doc_types_seen))
    if evidence_count == 0:
        gaps.append("No evidence matched the assertion query.")
    if evidence_count < assertion.min_evidence:
        gaps.append(
            f"Need at least {assertion.min_evidence} evidence chunk(s); found {evidence_count}."
        )
    if missing_types:
        missing_joined = ", ".join(missing_types)
        gaps.append(f"Missing corroboration from doc type(s): {missing_joined}.")

    if evidence_count == 0:
        verdict = Verdict.UNCONFIRMED
    elif missing_types or evidence_count < assertion.min_evidence:
        verdict = Verdict.INCONCLUSIVE
    else:
        verdict = Verdict.CONFIRMED

    return Finding(
        assertion=assertion,
        verdict=verdict,
        evidence_count=evidence_count,
        doc_types_covered=tuple(doc_types_seen),
        top_citation=_top_citation(results),
        gaps=tuple(gaps),
    )


def _render_findings(findings: list[Finding]) -> None:
    for finding in findings:
        print(f"\n[{finding.assertion.step_id}] {finding.assertion.title}")
        print(f"  verdict: {finding.verdict}")
        print(f"  evidence_count: {finding.evidence_count}")
        covered = ", ".join(finding.doc_types_covered) if finding.doc_types_covered else "-"
        print(f"  doc_types_covered: {covered}")
        if finding.top_citation is None:
            print("  top_citation: none")
        else:
            print(
                "  top_citation: "
                f"doc_id={finding.top_citation.doc_id}, "
                f"chunk_id={finding.top_citation.chunk_id}, "
                f"score={finding.top_citation.score:.3f}"
            )
        if finding.gaps:
            print(f"  gap_messages: {'; '.join(finding.gaps)}")
        else:
            print("  gap_messages: none")


def _render_summary(findings: list[Finding]) -> None:
    action_items = [finding for finding in findings if finding.verdict != Verdict.CONFIRMED]
    print("\nAction-required summary (non-CONFIRMED only)")
    print("| Step | Verdict | Action required |")
    print("| --- | --- | --- |")
    if not action_items:
        print("| - | - | None |")
        return
    for finding in action_items:
        action = " ; ".join(finding.gaps) if finding.gaps else "Investigate evidence quality."
        print(f"| {finding.assertion.step_id} | {finding.verdict} | {action} |")


def _seed_stub_if_enabled(index_name: str) -> None:
    if not _is_stub_mode():
        return
    get_stub_index()[index_name] = []
    add_chunks(index_name, _stub_chunks())


def _assertions() -> list[AuditAssertion]:
    return [
        AuditAssertion(
            step_id="A-01",
            title="Related-party loan corroborated across key sources",
            query="related-party loan approved",
            required_doc_types=("financial_statement", "board_minutes"),
            min_evidence=2,
        ),
        AuditAssertion(
            step_id="A-02",
            title="Revenue recognition policy change corroborated",
            query="revenue recognition policy changed",
            required_doc_types=("financial_statement", "board_minutes"),
            min_evidence=2,
        ),
        AuditAssertion(
            step_id="A-03",
            title="Environmental fine contingency documented",
            query="environmental fine contingency reserve",
            required_doc_types=("financial_statement", "board_minutes"),
            min_evidence=1,
        ),
    ]


def main() -> int:
    index_name = os.environ.get("DIGISEARCH_DEMO_INDEX", "audit-rag-demo")
    mode = "stub" if _is_stub_mode() else "live"
    print(f"Audit RAG demo mode: {mode} (index={index_name})")
    print("Structured verdicts: CONFIRMED / INCONCLUSIVE / UNCONFIRMED")

    _seed_stub_if_enabled(index_name)
    findings = [evaluate_assertion(assertion, index_name=index_name) for assertion in _assertions()]

    _render_findings(findings)
    _render_summary(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
