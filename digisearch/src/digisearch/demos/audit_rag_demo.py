"""
DigiSearch — Audit RAG Demo

Shows how DigiSearch serves as a structured RAG engine for auditing workflows.
Key differences from generic RAG:

  - Assertion-driven queries  : each audit step maps to targeted search queries
                                with metadata filters (doc_type, period, entity)
  - Multi-source corroboration: verdicts require evidence across required doc types
  - Structured verdicts       : CONFIRMED / INCONCLUSIVE / UNCONFIRMED with citations
  - Completeness checking     : gaps reported explicitly, not silently swallowed
  - Full audit trail          : every finding is cited (doc_id, chunk_id, score)

Usage
-----
Stub mode — no Azure required, uses an in-memory demo corpus:

    DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_rag_demo

Live mode — point at your existing Azure AI Search index:

    AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net \\
    AZURE_SEARCH_API_KEY=<your-key> \\
    AZURE_SEARCH_INDEX_NAME=<your-index> \\
    python -m digisearch.demos.audit_rag_demo
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from enum import Enum

from digisearch.core.models import Chunk, Query, Result


# ── Verdict ──────────────────────────────────────────────────────────────────


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNCONFIRMED = "UNCONFIRMED"


_VERDICT_SYMBOL = {
    Verdict.CONFIRMED: "✓",
    Verdict.INCONCLUSIVE: "⚠",
    Verdict.UNCONFIRMED: "✗",
}


# ── Audit data contracts ──────────────────────────────────────────────────────


@dataclass
class AuditAssertion:
    """One step in an audit program — what the auditor needs to confirm."""

    id: str
    category: str
    description: str
    search_query: str          # natural-language query sent to DigiSearch
    required_doc_types: list[str]  # evidence must span these doc_type values
    min_evidence_count: int = 2    # fewer chunks → INCONCLUSIVE
    filters: dict = field(default_factory=dict)


@dataclass
class EvidenceItem:
    chunk_id: str
    doc_id: str
    doc_type: str
    content_preview: str
    score: float


@dataclass
class AuditFinding:
    assertion: AuditAssertion
    verdict: Verdict
    evidence: list[EvidenceItem]
    gaps: list[str]


# ── Audit program (illustrative — swap in your real audit steps) ──────────────

AUDIT_PROGRAM: list[AuditAssertion] = [
    AuditAssertion(
        id="REV-01",
        category="Revenue Recognition",
        description="Confirm revenue is recognized per ASC 606 performance obligations",
        search_query="revenue recognition performance obligations transfer of control ASC 606",
        required_doc_types=["financial_statement", "policy_memo"],
        min_evidence_count=2,
    ),
    AuditAssertion(
        id="AR-01",
        category="Accounts Receivable",
        description="Verify AR allowance for doubtful accounts is adequately estimated",
        search_query="allowance for doubtful accounts aging schedule bad debt provision",
        required_doc_types=["financial_statement"],
        min_evidence_count=2,
    ),
    AuditAssertion(
        id="IC-01",
        category="Internal Controls",
        description="Confirm privileged access reviews and segregation of duties are documented",
        search_query="privileged access review segregation of duties IT general controls",
        required_doc_types=["it_controls_report"],
        min_evidence_count=2,
    ),
    AuditAssertion(
        id="GC-01",
        category="Going Concern",
        description="Assess whether material uncertainties about going concern are disclosed",
        search_query="going concern material uncertainty liquidity capital adequacy",
        required_doc_types=["financial_statement", "board_minutes"],
        min_evidence_count=2,
    ),
    AuditAssertion(
        id="RPT-01",
        category="Related Party Transactions",
        description="Verify all related party transactions are identified and disclosed",
        search_query="related party transactions intercompany pricing",
        required_doc_types=["related_party_disclosure"],
        min_evidence_count=1,
    ),
    AuditAssertion(
        id="INV-01",
        category="Inventory Valuation",
        description="Confirm inventory is valued at lower of cost or net realizable value",
        search_query="inventory valuation cost NRV net realizable value write-down obsolescence",
        required_doc_types=["financial_statement", "inventory_report"],
        min_evidence_count=2,
    ),
]


# ── Demo corpus (stub mode only) ──────────────────────────────────────────────
# In production this section is absent — chunks come from the live Azure index.


def _demo_corpus() -> list[Chunk]:
    """Simulated audit document chunks for stub/demo mode."""
    return [
        # REV-01 — strong evidence across two doc types
        Chunk(
            id="chunk-fs-001", doc_id="annual_report_fy2024",
            content=(
                "Revenue Recognition Policy (ASC 606): The Company recognizes revenue when "
                "control of the promised goods or services is transferred to the customer, "
                "in an amount that reflects the consideration to which the entity expects to "
                "be entitled in exchange for those goods or services. Performance obligations "
                "are identified at contract inception and satisfied either at a point in time "
                "or over time."
            ),
            metadata={"doc_type": "financial_statement", "period": "FY2024", "section": "Note 2"},
        ),
        Chunk(
            id="chunk-pm-001", doc_id="revenue_policy_memo_2024",
            content=(
                "Policy Memo — Revenue Recognition Update (Q1 2024): Following our ASC 606 "
                "compliance review, contract modifications are treated as separate performance "
                "obligations when the added goods/services are distinct. Variable consideration "
                "is constrained using the expected value method. Transfer of control is assessed "
                "at the individual performance obligation level."
            ),
            metadata={"doc_type": "policy_memo", "period": "FY2024", "section": "Q1 Update"},
        ),
        Chunk(
            id="chunk-fs-002", doc_id="annual_report_fy2024",
            content=(
                "Disaggregation of Revenue (FY2024): SaaS subscription revenue $42.3M recognized "
                "ratably over contract term as performance obligations are satisfied; professional "
                "services $8.1M recognized over time as services are rendered; perpetual licenses "
                "$3.9M recognized at point of delivery. Remaining performance obligations totaling "
                "$61.2M will be recognized within 24 months."
            ),
            metadata={"doc_type": "financial_statement", "period": "FY2024", "section": "Note 3"},
        ),
        # AR-01 — only 1 chunk (deliberate → INCONCLUSIVE)
        Chunk(
            id="chunk-fs-003", doc_id="annual_report_fy2024",
            content=(
                "Accounts Receivable (FY2024): Gross AR of $14.7M less allowance for doubtful "
                "accounts of $1.1M equals net AR of $13.6M. The allowance is estimated using "
                "historical loss rates applied to an aging schedule of outstanding balances. "
                "Accounts over 180 days are reviewed individually and reserved at 80%."
            ),
            metadata={"doc_type": "financial_statement", "period": "FY2024", "section": "Note 5"},
        ),
        # IC-01 — two IT controls chunks
        Chunk(
            id="chunk-it-001", doc_id="it_controls_assessment_q4_2024",
            content=(
                "IT General Controls — Access Management: Privileged access reviews were completed "
                "quarterly for all production systems. Q3 2024 review identified 3 accounts with "
                "excessive permissions; all remediated within SLA. Segregation of duties matrix "
                "was updated to reflect the new ERP module configuration deployed in August 2024."
            ),
            metadata={"doc_type": "it_controls_report", "period": "FY2024", "section": "Access Controls"},
        ),
        Chunk(
            id="chunk-it-002", doc_id="it_controls_assessment_q4_2024",
            content=(
                "User Provisioning Controls: All joiners/movers/leavers are processed through "
                "automated HR integration. Deprovisioning SLA of 24 hours achieved in 97.3% of "
                "cases. Privileged service accounts are reviewed monthly; general access controls "
                "are attested by system owners on a quarterly basis. No segregation of duties "
                "conflicts remain open beyond 30 days."
            ),
            metadata={"doc_type": "it_controls_report", "period": "FY2024", "section": "Provisioning"},
        ),
        # GC-01 — financial statement + board minutes
        Chunk(
            id="chunk-fs-004", doc_id="annual_report_fy2024",
            content=(
                "Going Concern Assessment: Management has assessed the Company's ability to "
                "continue as a going concern for at least 12 months from the reporting date. "
                "The Company holds a $25M revolving credit facility (drawn: $8M) and generated "
                "positive operating cash flows of $11.4M in FY2024. No material uncertainties "
                "regarding liquidity or capital adequacy have been identified."
            ),
            metadata={"doc_type": "financial_statement", "period": "FY2024", "section": "Note 1"},
        ),
        Chunk(
            id="chunk-bm-001", doc_id="board_minutes_dec_2024",
            content=(
                "Board of Directors — December 2024: The CFO presented the annual going concern "
                "assessment. The Board reviewed 18-month liquidity projections and noted material "
                "headroom on all lending covenants. Capital adequacy ratios remain well above "
                "regulatory minimums. The Board resolved that no going concern disclosure or "
                "material uncertainty note is required in the FY2024 financial statements."
            ),
            metadata={"doc_type": "board_minutes", "period": "FY2024", "section": "Item 4"},
        ),
        # RPT-01 — NO chunks indexed (deliberate → UNCONFIRMED)
        # INV-01 — inventory valuation confirmed across two doc types
        Chunk(
            id="chunk-fs-005", doc_id="annual_report_fy2024",
            content=(
                "Inventory (FY2024): Inventories are stated at the lower of cost (FIFO) and "
                "net realizable value (NRV). A write-down of $0.4M was recognized in Q3 2024 "
                "for slow-moving components identified during the annual physical count. "
                "Total inventories: $9.2M (FY2023: $10.1M). No further NRV write-down "
                "is considered necessary based on current selling prices."
            ),
            metadata={"doc_type": "financial_statement", "period": "FY2024", "section": "Note 7"},
        ),
        Chunk(
            id="chunk-inv-001", doc_id="inventory_management_report_fy2024",
            content=(
                "Inventory NRV Assessment (FY2024): Independent review performed by the operations "
                "team in November 2024. 847 SKUs assessed; 23 flagged for obsolescence and "
                "included in the write-down provision. NRV valuation of $0.4M aligns with the "
                "auditor's independent estimate of $0.35–0.45M. No inventory line remains where "
                "cost exceeds net realizable value after the write-down."
            ),
            metadata={"doc_type": "inventory_report", "period": "FY2024", "section": "NRV Review"},
        ),
    ]


# ── Demo-mode search (word-overlap scoring) ───────────────────────────────────
# Used only when DIGISEARCH_ALLOW_STUB=1.  Azure mode calls query_index() directly.


def _demo_search(corpus: list[Chunk], query_text: str, top_k: int = 8) -> list[Result]:
    """Keyword-overlap scorer for stub/demo mode. Not for production use."""
    import re

    _STOP = {"a", "an", "the", "and", "or", "of", "in", "to", "for", "is",
              "are", "was", "were", "be", "been", "that", "this", "with", "at", "by", "on"}
    words = {w for w in query_text.lower().split() if w not in _STOP}
    scored: list[tuple[float, Chunk]] = []
    for chunk in corpus:
        # Split into actual words (word-boundary aware) to prevent substring false positives.
        content_words = set(re.findall(r"\b\w+\b", chunk.content.lower()))
        hits = sum(1 for w in words if w in content_words)
        if hits == 0:
            continue
        score = hits / len(words)
        scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [
        Result(chunk=c, score=round(s, 3), rank=i + 1)
        for i, (s, c) in enumerate(scored[:top_k])
    ]


# ── Evidence evaluation ───────────────────────────────────────────────────────

_SCORE_THRESHOLD = 0.15  # minimum word-overlap score for stub mode


def _evaluate(assertion: AuditAssertion, results: list[Result]) -> AuditFinding:
    """Map retrieved chunks onto a structured verdict for one audit assertion."""
    qualified = [r for r in results if r.score >= _SCORE_THRESHOLD]

    evidence = [
        EvidenceItem(
            chunk_id=r.chunk.id,
            doc_id=r.chunk.doc_id,
            doc_type=r.chunk.metadata.get("doc_type", "unknown"),
            content_preview=r.chunk.content[:220].replace("\n", " "),
            score=r.score,
        )
        for r in qualified
    ]

    covered_types = {e.doc_type for e in evidence}
    missing_types = [t for t in assertion.required_doc_types if t not in covered_types]
    gaps: list[str] = []

    if not evidence:
        verdict = Verdict.UNCONFIRMED
        for t in assertion.required_doc_types:
            gaps.append(f"No documents of type '{t}' found in index")
    elif len(evidence) < assertion.min_evidence_count:
        verdict = Verdict.INCONCLUSIVE
        gaps.append(
            f"Only {len(evidence)} piece(s) of evidence (required: {assertion.min_evidence_count})"
        )
        for t in missing_types:
            gaps.append(f"Missing evidence from doc_type='{t}'")
    elif missing_types:
        verdict = Verdict.INCONCLUSIVE
        for t in missing_types:
            gaps.append(f"No corroborating evidence from doc_type='{t}'")
    else:
        verdict = Verdict.CONFIRMED

    return AuditFinding(assertion=assertion, verdict=verdict, evidence=evidence, gaps=gaps)


# ── Audit runner ──────────────────────────────────────────────────────────────


def run_audit(
    corpus: list[Chunk] | None,
    index_name: str,
    program: list[AuditAssertion] = AUDIT_PROGRAM,
) -> list[AuditFinding]:
    """
    Run each assertion in *program* against DigiSearch.

    If *corpus* is provided, uses demo word-overlap search (stub mode).
    Otherwise delegates to the live backend via query_index().
    """
    from digisearch.search._stub import query_index

    findings: list[AuditFinding] = []
    for assertion in program:
        if corpus is not None:
            results = _demo_search(corpus, assertion.search_query)
        else:
            q = Query(text=assertion.search_query, top_k=8, mode="hybrid",
                      filters=assertion.filters or {})
            results = query_index(q, index_name=index_name).results

        findings.append(_evaluate(assertion, results))

    return findings


# ── Report renderer ───────────────────────────────────────────────────────────

_W = 72


def _hr() -> str:
    return "─" * _W


def print_report(company: str, period: str, backend: str, findings: list[AuditFinding]) -> None:
    confirmed    = [f for f in findings if f.verdict == Verdict.CONFIRMED]
    inconclusive = [f for f in findings if f.verdict == Verdict.INCONCLUSIVE]
    unconfirmed  = [f for f in findings if f.verdict == Verdict.UNCONFIRMED]

    print()
    print("DigiSearch — Audit RAG Demo".center(_W))
    print(f"Company: {company}  |  Period: {period}".center(_W))
    print(f"Backend: {backend}".center(_W))
    print("═" * _W)
    print()

    for i, finding in enumerate(findings, 1):
        a = finding.assertion
        sym = _VERDICT_SYMBOL[finding.verdict]

        print(f"  [{i}/{len(findings)}]  {a.id} — {a.category}")
        print(f"         {a.description}")
        q_display = a.search_query if len(a.search_query) <= 60 else a.search_query[:57] + "..."
        print(f"         Query  → \"{q_display}\"")
        req = ", ".join(a.required_doc_types)
        print(f"         Needs  → {req}  (min {a.min_evidence_count} chunk(s))")
        print()

        if finding.evidence:
            score_str = "  ".join(str(e.score) for e in finding.evidence[:4])
            print(f"         Found  → {len(finding.evidence)} chunk(s)   scores: {score_str}")
            top = finding.evidence[0]
            covered = ", ".join({e.doc_type for e in finding.evidence})
            print(f"         Types  → {covered}")
            print()
            print(f"         {sym}  {finding.verdict.value}")
            wrapped = textwrap.fill(
                f"\"{top.content_preview}...\"",
                width=_W - 12,
                initial_indent=" " * 12,
                subsequent_indent=" " * 12,
            )
            print(wrapped)
            print(f"            [{top.doc_id}  ·  {top.chunk_id}  ·  score {top.score}]")
        else:
            print("         Found  → 0 chunks")
            print()
            print(f"         {sym}  {finding.verdict.value}")

        if finding.gaps:
            print()
            for gap in finding.gaps:
                print(f"         Gap    → {gap}")

        print()
        print(f"  {_hr()}")
        print()

    print("═" * _W)
    print(f"  AUDIT SUMMARY  —  {company}  {period}")
    print()
    print(f"  {'CONFIRMED':<14}  {len(confirmed):>2} / {len(findings)}")
    print(f"  {'INCONCLUSIVE':<14}  {len(inconclusive):>2} / {len(findings)}")
    print(f"  {'UNCONFIRMED':<14}  {len(unconfirmed):>2} / {len(findings)}")
    print()

    action_items = [f for f in findings if f.verdict != Verdict.CONFIRMED]
    if action_items:
        print("  Action required:")
        for f in action_items:
            sym = _VERDICT_SYMBOL[f.verdict]
            print(f"    {sym}  [{f.assertion.id}] {f.assertion.category}")
            for gap in f.gaps:
                print(f"           → {gap}")
        print()

    print("═" * _W)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    company    = "Meridian Analytics Inc."
    period     = "FY 2024"
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "audit-meridian-fy2024")

    using_azure = bool(
        os.environ.get("AZURE_SEARCH_ENDPOINT") and os.environ.get("AZURE_SEARCH_API_KEY")
    )
    using_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in ("1", "true", "yes")

    if using_azure:
        backend_label = f"Azure AI Search  →  index: {index_name}"
        corpus = None
    elif using_stub:
        backend_label = "stub  (in-memory demo corpus — illustrative only)"
        corpus = _demo_corpus()
    else:
        print(
            "\nNo backend configured.\n\n"
            "  Stub mode (no Azure needed):\n"
            "    DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_rag_demo\n\n"
            "  Live Azure AI Search:\n"
            "    AZURE_SEARCH_ENDPOINT=https://... \\\n"
            "    AZURE_SEARCH_API_KEY=...          \\\n"
            "    AZURE_SEARCH_INDEX_NAME=...       \\\n"
            "    python -m digisearch.demos.audit_rag_demo\n"
        )
        return

    findings = run_audit(corpus=corpus, index_name=index_name)
    print_report(company, period, backend_label, findings)


if __name__ == "__main__":
    main()
