"""
DigiSearch — Construction Document Audit Demo

Illustrates how DigiSearch serves as the retrieval intelligence layer
for a construction document auditing system.

The auditing tool already indexes documents into Azure AI Search
(daily logs, RFIs, contracts, invoices, specs, emails).
DigiSearch connects to that existing index and answers structured
audit questions — no re-indexing, no migration.

Four audit patterns demonstrated (from the Autonomous Project Auditor deck):
  1. SEMANTIC CONTRADICTION  — same fact stated differently across documents
  2. PROCESS GAP             — required document or approval is absent
  3. FINANCIAL DRIFT         — what is billed does not match what is specified
  4. CLEAR                   — evidence consistent, no issues found

Usage
-----
Stub mode (no Azure required, illustrative demo corpus):

    DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_rag_demo

Live mode (point at the auditing tool's existing Azure index):

    AZURE_SEARCH_ENDPOINT=https://<service>.search.windows.net \\
    AZURE_SEARCH_API_KEY=<key> \\
    AZURE_SEARCH_INDEX_NAME=<index> \\
    python -m digisearch.demos.audit_rag_demo
"""

from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass
from enum import Enum

from digisearch.core.models import Chunk, Query, Result


# ── Alert types (mirrors the Autonomous Project Auditor dashboard) ─────────────

class AlertType(str, Enum):
    CLEAR                  = "CLEAR"
    SEMANTIC_CONTRADICTION = "SEMANTIC CONTRADICTION"
    PROCESS_GAP            = "PROCESS GAP"
    FINANCIAL_DRIFT        = "FINANCIAL DRIFT"


_ALERT_SYMBOL = {
    AlertType.CLEAR:                  "✓",
    AlertType.SEMANTIC_CONTRADICTION:  "⚡",
    AlertType.PROCESS_GAP:            "⚠",
    AlertType.FINANCIAL_DRIFT:        "⊘",
}

_ALERT_COLOR_LABEL = {
    AlertType.CLEAR:                  "CLEAR",
    AlertType.SEMANTIC_CONTRADICTION: "SEMANTIC CONTRADICTION",
    AlertType.PROCESS_GAP:           "PROCESS GAP",
    AlertType.FINANCIAL_DRIFT:       "FINANCIAL DRIFT",
}


# ── Audit check contract ──────────────────────────────────────────────────────

@dataclass
class AuditCheck:
    """
    One audit question the system needs to answer.

    DigiSearch fires `search_query` against the document index.
    The `evaluate` callable receives the retrieved chunks and
    returns a verdict + human-readable finding.
    """
    id: str
    title: str
    description: str
    search_query: str
    doc_types_in_scope: list[str]   # informational — shown in output


@dataclass
class AuditResult:
    check: AuditCheck
    alert: AlertType
    finding: str                    # one-sentence summary
    evidence: list[tuple[str, str, float]]  # (doc_id, content_preview, score)


# ── Demo corpus ───────────────────────────────────────────────────────────────
# Simulates what the auditing tool has already indexed in Azure AI Search.
# In production this section is absent — chunks come from the live index.

def _demo_corpus() -> list[Chunk]:
    return [
        # --- CHECK 1: Material integrity ---
        # Contradiction: subcontractor email says Grade B, progress report says Grade A
        Chunk(
            id="chunk-email-001", doc_id="subcontractor_email_2024_11_14",
            content=(
                "Hi team, due to supply chain delays from our primary supplier we have "
                "substituted Grade A steel with Grade B steel for the anchor bolt assembly "
                "on Sector 4. Please update your procurement records accordingly. "
                "Delivery scheduled for next Wednesday."
            ),
            metadata={"doc_type": "email", "project": "ganga-bridge", "sector": "4",
                      "date": "2024-11-14", "sender": "subcontractor"},
        ),
        Chunk(
            id="chunk-report-001", doc_id="monthly_progress_report_nov_2024",
            content=(
                "Material Status (November 2024): All structural steel components for "
                "Sector 4 have been delivered and meet Grade A specifications as per "
                "the approved Material Specification document MS-400. Quality certificates "
                "on file. No material substitutions reported this period."
            ),
            metadata={"doc_type": "progress_report", "project": "ganga-bridge",
                      "sector": "4", "date": "2024-11-30"},
        ),
        # --- CHECK 2: Inspection reports for cable anchoring ---
        # RFIs exist, but zero inspection reports uploaded
        Chunk(
            id="chunk-rfi-001", doc_id="RFI_402",
            content=(
                "RFI #402 — Cable Anchoring: Substituting Anchor Bolts Type A for Type C "
                "due to availability constraints. Type C has different load tolerance. "
                "Requesting engineering review and approval before proceeding with "
                "installation on Pier 7 and Pier 8."
            ),
            metadata={"doc_type": "rfi", "project": "ganga-bridge",
                      "rfi_number": "402", "date": "2024-10-05"},
        ),
        Chunk(
            id="chunk-rfi-002", doc_id="RFI_415",
            content=(
                "RFI #415 — Cable Anchoring Torque Values: Requesting clarification on "
                "required torque specification for Type C anchor bolts on Piers 9–12. "
                "Current spec references Type A values only. Site crew awaiting updated "
                "installation procedure."
            ),
            metadata={"doc_type": "rfi", "project": "ganga-bridge",
                      "rfi_number": "415", "date": "2024-10-19"},
        ),
        Chunk(
            id="chunk-rfi-003", doc_id="RFI_428",
            content=(
                "RFI #428 — Third-Party Inspection: Confirming that third-party inspector "
                "from CertBuild Inc. will attend Pier 7 anchor installation next week. "
                "Inspection scope: bolt placement, torque verification, load test witness."
            ),
            metadata={"doc_type": "rfi", "project": "ganga-bridge",
                      "rfi_number": "428", "date": "2024-11-02"},
        ),
        # NOTE: No inspection_report chunks exist — that is intentional (the gap)

        # --- CHECK 3: Concrete volume — invoice vs. spec ---
        Chunk(
            id="chunk-invoice-001", doc_id="invoice_992",
            content=(
                "Invoice #992 — Additional Excavation and Concrete Supply. "
                "Line item: Ready-mix concrete, high-strength 35 MPa. "
                "Quantity: 500 cubic metres. Unit price: $185/m³. "
                "Total: $92,500. Approved by finance department 2024-11-20."
            ),
            metadata={"doc_type": "invoice", "project": "ganga-bridge",
                      "invoice_number": "992", "date": "2024-11-20"},
        ),
        Chunk(
            id="chunk-spec-001", doc_id="engineering_spec_pier7_concrete",
            content=(
                "Pier 7 Concrete Pour Specification (Rev 3): Total concrete volume "
                "required for Pier 7 foundation and column: 350 cubic metres of "
                "35 MPa ready-mix. Any volume exceeding 360 m³ requires a Change Order "
                "approved by the project engineer prior to placement."
            ),
            metadata={"doc_type": "engineering_spec", "project": "ganga-bridge",
                      "revision": "3", "date": "2024-09-15"},
        ),
        # --- CHECK 4: Safety specs consistent across design docs (CLEAR) ---
        Chunk(
            id="chunk-spec-002", doc_id="structural_safety_spec_v2",
            content=(
                "Structural Safety Specification v2 (Load-Bearing Joints): "
                "All load-bearing joint connections shall use Type A anchor bolts "
                "conforming to ASTM F3125 Grade A325. Type B and Type C bolts are "
                "prohibited for primary load-bearing applications. Updated 2024-10-01."
            ),
            metadata={"doc_type": "safety_spec", "project": "ganga-bridge",
                      "version": "2", "date": "2024-10-01"},
        ),
        Chunk(
            id="chunk-spec-003", doc_id="design_drawing_pier_connections",
            content=(
                "Design Drawing D-447 — Pier Connection Details: Anchor bolt specification "
                "reference: ASTM F3125 Grade A325 (Type A) as per Structural Safety "
                "Specification v2. Connection torque: 490 ft-lbs minimum. "
                "Third-party inspection mandatory prior to concrete encasement."
            ),
            metadata={"doc_type": "design_drawing", "project": "ganga-bridge",
                      "drawing_number": "D-447", "date": "2024-10-10"},
        ),
    ]


# ── Audit check definitions ───────────────────────────────────────────────────

AUDIT_CHECKS: list[AuditCheck] = [
    AuditCheck(
        id="MAT-01",
        title="Material Integrity — Steel Grade Consistency",
        description=(
            "Verify that the steel grade reported in subcontractor communications "
            "matches what is declared in progress reports to the client."
        ),
        search_query="steel grade anchor bolt material specification subcontractor supply",
        doc_types_in_scope=["email", "progress_report", "engineering_spec"],
    ),
    AuditCheck(
        id="INS-01",
        title="Regulatory Compliance — Cable Anchoring Inspection Reports",
        description=(
            "Contract requires third-party inspection of all cable anchoring work. "
            "Verify inspection reports exist for the RFIs that triggered anchor changes."
        ),
        search_query="cable anchoring inspection report third party certification pier",
        doc_types_in_scope=["rfi", "inspection_report", "daily_log"],
    ),
    AuditCheck(
        id="BUD-01",
        title="Budget Alignment — Concrete Volume",
        description=(
            "Verify that the concrete volume invoiced matches the volume specified "
            "in the engineering documents for Pier 7."
        ),
        search_query="concrete cubic metres volume pier invoice specification",
        doc_types_in_scope=["invoice", "engineering_spec", "change_order"],
    ),
    AuditCheck(
        id="SAFE-01",
        title="Specification Consistency — Anchor Bolt Type Across Design Docs",
        description=(
            "Verify that anchor bolt type and grade are consistently specified "
            "across safety specs and design drawings."
        ),
        search_query="anchor bolt type grade load bearing ASTM specification drawing",
        doc_types_in_scope=["safety_spec", "design_drawing", "engineering_spec"],
    ),
]


# ── Verdict logic ─────────────────────────────────────────────────────────────

_STOP = {"a", "an", "the", "and", "or", "of", "in", "to", "for", "is", "are",
         "was", "were", "be", "been", "that", "this", "with", "at", "by", "on",
         "all", "are", "from", "as", "per", "not", "no"}


def _demo_search(corpus: list[Chunk], query: str, top_k: int = 6) -> list[Result]:
    """Word-overlap scorer for stub/demo mode only."""
    words = {w for w in query.lower().split() if w not in _STOP}
    scored: list[tuple[float, Chunk]] = []
    for chunk in corpus:
        content_words = set(re.findall(r"\b\w+\b", chunk.content.lower()))
        hits = sum(1 for w in words if w in content_words)
        if hits == 0:
            continue
        scored.append((hits / len(words), chunk))
    scored.sort(key=lambda x: -x[0])
    return [Result(chunk=c, score=round(s, 3), rank=i + 1)
            for i, (s, c) in enumerate(scored[:top_k])]


def _judge(check: AuditCheck, results: list[Result]) -> AuditResult:
    """
    Apply simple verdict logic per check ID.

    In production this would be an LLM call comparing retrieved chunks
    for contradictions, counting required document types, comparing values.
    Here we use the demo corpus structure to simulate each pattern.
    """
    evidence = [
        (r.chunk.doc_id,
         r.chunk.content[:180].replace("\n", " "),
         r.score)
        for r in results if r.score >= 0.12
    ]
    doc_types_found = {r.chunk.metadata.get("doc_type") for r in results if r.score >= 0.12}

    if check.id == "MAT-01":
        # Contradiction: email says Grade B, report says Grade A, no substitution noted
        if "email" in doc_types_found and "progress_report" in doc_types_found:
            return AuditResult(
                check=check,
                alert=AlertType.SEMANTIC_CONTRADICTION,
                finding=(
                    "Subcontractor email (2024-11-14) confirms Grade B steel substitution "
                    "for Sector 4 anchor bolts. Monthly progress report (Nov 2024) declares "
                    "Grade A compliance with no substitutions. Documents are contradictory."
                ),
                evidence=evidence[:3],
            )

    if check.id == "INS-01":
        # Three RFIs about cable anchoring — zero inspection reports indexed
        rfi_count = sum(1 for r in results if r.chunk.metadata.get("doc_type") == "rfi"
                        and r.score >= 0.12)
        insp_count = sum(1 for r in results
                         if r.chunk.metadata.get("doc_type") == "inspection_report")
        if rfi_count >= 1 and insp_count == 0:
            return AuditResult(
                check=check,
                alert=AlertType.PROCESS_GAP,
                finding=(
                    f"{rfi_count} RFI(s) found referencing cable anchoring work on Sector 4. "
                    "Zero third-party inspection reports indexed. Contract requires inspection "
                    "prior to concrete encasement — stage may have been skipped."
                ),
                evidence=evidence[:3],
            )

    if check.id == "BUD-01":
        # Invoice: 500 m³ — Spec: 350 m³
        if "invoice" in doc_types_found and "engineering_spec" in doc_types_found:
            return AuditResult(
                check=check,
                alert=AlertType.FINANCIAL_DRIFT,
                finding=(
                    "Invoice #992 approved for 500 m³ of concrete. "
                    "Engineering Spec (Pier 7, Rev 3) requires 350 m³. "
                    "150 m³ discrepancy ($27,750) with no Change Order found."
                ),
                evidence=evidence[:3],
            )

    if check.id == "SAFE-01":
        # Both safety spec and design drawing agree on Type A / ASTM F3125
        if "safety_spec" in doc_types_found and "design_drawing" in doc_types_found:
            return AuditResult(
                check=check,
                alert=AlertType.CLEAR,
                finding=(
                    "Safety Specification v2 and Design Drawing D-447 are consistent: "
                    "both specify ASTM F3125 Grade A325 (Type A) for all load-bearing "
                    "anchor connections."
                ),
                evidence=evidence[:2],
            )

    # Fallback: not enough evidence
    return AuditResult(
        check=check,
        alert=AlertType.PROCESS_GAP,
        finding="Insufficient evidence retrieved from the index to render a verdict.",
        evidence=evidence[:2],
    )


# ── Runner ────────────────────────────────────────────────────────────────────

def run_audit(
    corpus: list[Chunk] | None,
    index_name: str,
    checks: list[AuditCheck] = AUDIT_CHECKS,
) -> list[AuditResult]:
    from digisearch.search._stub import query_index

    results_out: list[AuditResult] = []
    for check in checks:
        if corpus is not None:
            hits = _demo_search(corpus, check.search_query)
        else:
            q = Query(text=check.search_query, top_k=8, mode="hybrid")
            hits = query_index(q, index_name=index_name).results
        results_out.append(_judge(check, hits))
    return results_out


# ── Report renderer ───────────────────────────────────────────────────────────

_W = 72


def print_report(
    project: str,
    backend: str,
    results: list[AuditResult],
) -> None:
    issues = [r for r in results if r.alert != AlertType.CLEAR]

    print()
    print("DigiSearch — Autonomous Project Auditor".center(_W))
    print(f"Project: {project}".center(_W))
    print(f"Backend: {backend}".center(_W))
    print("═" * _W)
    print()

    for r in results:
        sym = _ALERT_SYMBOL[r.alert]
        label = _ALERT_COLOR_LABEL[r.alert]
        print(f"  [{r.check.id}]  {r.check.title}")
        print(f"         {r.check.description}")
        scope = ", ".join(r.check.doc_types_in_scope)
        print(f"         Scope  → {scope}")
        print()
        print(f"         {sym}  {label}")
        wrapped = textwrap.fill(
            r.finding,
            width=_W - 12,
            initial_indent=" " * 12,
            subsequent_indent=" " * 12,
        )
        print(wrapped)
        if r.evidence:
            print()
            top_doc, top_content, top_score = r.evidence[0]
            preview = textwrap.fill(
                f'"{top_content}..."',
                width=_W - 14,
                initial_indent=" " * 14,
                subsequent_indent=" " * 14,
            )
            print(preview)
            print(f"              [{top_doc}  ·  score {top_score}]")
        print()
        print("  " + "─" * (_W - 2))
        print()

    print("═" * _W)
    print(f"  AUDIT SUMMARY  —  {project}")
    print()
    for alert_type in [AlertType.SEMANTIC_CONTRADICTION,
                       AlertType.PROCESS_GAP,
                       AlertType.FINANCIAL_DRIFT,
                       AlertType.CLEAR]:
        count = sum(1 for r in results if r.alert == alert_type)
        if count:
            sym = _ALERT_SYMBOL[alert_type]
            print(f"  {sym}  {alert_type.value:<28}  {count} / {len(results)}")
    print()

    if issues:
        print("  Action required:")
        for r in issues:
            sym = _ALERT_SYMBOL[r.alert]
            print(f"    {sym}  [{r.check.id}] {r.check.title}")
            print(f"           → {r.finding[:100]}...")
        print()
    print("═" * _W)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    project    = "Ganga River Bridge — Sector 4"
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "construction-audit-index")

    using_azure = bool(
        os.environ.get("AZURE_SEARCH_ENDPOINT") and os.environ.get("AZURE_SEARCH_API_KEY")
    )
    using_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1", "true", "yes"
    )

    if using_azure:
        backend_label = f"Azure AI Search  →  index: {index_name}"
        corpus = None
    elif using_stub:
        backend_label = "stub  (in-memory demo corpus — illustrative only)"
        corpus = _demo_corpus()
    else:
        print(
            "\nNo backend configured.\n\n"
            "  Stub mode:   DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_rag_demo\n"
            "  Live Azure:  AZURE_SEARCH_ENDPOINT=... AZURE_SEARCH_API_KEY=... \\\n"
            "               AZURE_SEARCH_INDEX_NAME=... python -m digisearch.demos.audit_rag_demo\n"
        )
        return

    results = run_audit(corpus=corpus, index_name=index_name)
    print_report(project, backend_label, results)


if __name__ == "__main__":
    main()
