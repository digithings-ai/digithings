"""
DigiSearch × Autonomous Project Auditor — Presentation
-------------------------------------------------------
An interactive terminal deck to guide a conversation about how DigiSearch
serves as the retrieval intelligence layer for construction document auditing.

Usage:
    DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_presentation

    # Live Azure index:
    AZURE_SEARCH_ENDPOINT=https://... AZURE_SEARCH_API_KEY=... \\
    AZURE_SEARCH_INDEX_NAME=construction-audit-index \\
    python -m digisearch.demos.audit_presentation
"""

from __future__ import annotations

import os
import sys
import textwrap

from digisearch.demos.audit_rag_demo import (
    AUDIT_CHECKS,
    AlertType,
    _ALERT_SYMBOL,
    _demo_corpus,
    _demo_search,
    _judge,
)

# ── Layout constants ──────────────────────────────────────────────────────────

W = 72
DOUBLE = "═" * W
SINGLE = "─" * W
BLANK  = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause(label: str = "Press Enter for next slide") -> None:
    print()
    print(f"  \033[2m[{label}]\033[0m")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def c(text: str) -> str:
    """Centre text within slide width."""
    return text.center(W)


def wrap(text: str, indent: int = 4) -> str:
    pad = " " * indent
    return textwrap.fill(text, width=W - indent,
                         initial_indent=pad, subsequent_indent=pad)


def bullet(text: str, indent: int = 4, marker: str = "•") -> str:
    pad = " " * indent
    sub = " " * (indent + 2)
    return textwrap.fill(text, width=W - indent - 2,
                         initial_indent=f"{pad}{marker} ",
                         subsequent_indent=sub)


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def alert_color(alert: AlertType, text: str) -> str:
    codes = {
        AlertType.SEMANTIC_CONTRADICTION: "\033[91m",   # red
        AlertType.PROCESS_GAP:            "\033[93m",   # yellow
        AlertType.FINANCIAL_DRIFT:        "\033[33m",   # orange-ish
        AlertType.CLEAR:                  "\033[92m",   # green
    }
    return f"{codes.get(alert, '')}{text}\033[0m"


def slide_header(slide_num: int, total: int, title: str) -> None:
    print(DOUBLE)
    print(dim(f"  Slide {slide_num} / {total}").ljust(W))
    print()
    print(bold(c(title)))
    print()


def slide_footer(note: str = "") -> None:
    print()
    if note:
        print(dim(f"  {note}"))
    print(DOUBLE)


# ── Slides ────────────────────────────────────────────────────────────────────

TOTAL = 11


def slide_title() -> None:
    clear()
    print(DOUBLE)
    print()
    print(bold(c("DigiSearch")))
    print(bold(c("×")))
    print(bold(c("Autonomous Project Auditor")))
    print()
    print(c("How AI-powered document retrieval plugs into"))
    print(c("construction document control and auditing"))
    print()
    print(DOUBLE)
    print()
    print(c("Ganga River Bridge  ·  Sector 4  ·  Demo project"))
    print()
    pause("Press Enter to begin")


def slide_problem() -> None:
    clear()
    slide_header(1, TOTAL, "The Problem")

    print(bullet("Construction projects fail not because of changes in a single document —"))
    print(bullet("  but because of gaps between different documents.", indent=6, marker="→"))
    print()
    print(bullet("Information is scattered across Procore, SharePoint, email, daily logs."))
    print(bullet("Documents contradict each other and nobody notices."))
    print(bullet("Missing approvals go undetected until it is too late."))
    print()
    print(SINGLE)
    print()
    print(wrap("Real examples from construction project failures:"))
    print()
    print(bullet("A subcontractor email says Grade B steel was substituted.", indent=6))
    print(bullet("The monthly progress report to the client still says Grade A.", indent=6))
    print()
    print(bullet("The contract requires third-party inspection of all cable anchoring.", indent=6))
    print(bullet("Three RFIs document anchoring work. Zero inspection reports exist.", indent=6))
    print()
    print(bullet("Finance approves an invoice for 500 m³ of concrete.", indent=6))
    print(bullet("The engineering spec for the same pier requires 350 m³.", indent=6))
    print()
    print(wrap(
        "These are the \"Ugly Truths\" — hidden in plain sight across document systems "
        "that no one is actively connecting."
    ))
    print()
    slide_footer("Source: Autonomous Project Auditor deck, 2026-01")
    pause()


def slide_current_tools() -> None:
    clear()
    slide_header(2, TOTAL, "Why Existing Tools Miss This")

    print(wrap("Current construction software is a system of record — passive:"))
    print()
    print(bullet("Procore, Aconex, SharePoint: store and version documents."))
    print(bullet("They notify when a file changes — not when two files contradict."))
    print(bullet("Notification fatigue: every change looks the same. Budget title change"))
    print(bullet("  = budget amount change.", indent=6, marker=" "))
    print()
    print(SINGLE)
    print()
    print(wrap("LLMs help but have limits:"))
    print()
    print(bullet("Can classify, extract, summarise documents."))
    print(bullet("Cannot identify logical contradictions across documents."))
    print(bullet("Cannot apply implicit project rules (knowledge a controller carries in their head)."))
    print(bullet("Cannot detect what did NOT happen."))
    print()
    print(SINGLE)
    print()
    print(wrap(bold("The shift needed:") + "  from tracking  →  interrogating"))
    print()
    print(bullet(
        "Tracking:      \"The budget was updated from $1M to $1.2M. Notify the manager.\"",
        indent=6, marker=" "
    ))
    print(bullet(
        "Interrogating: \"Budget up 20%. Material Quality certs show 10% grade decrease. "
        "Possible Value Engineering. Alert: High Risk of Design Deviation.\"",
        indent=6, marker=" "
    ))
    print()
    slide_footer()
    pause()


def slide_digisearch_role() -> None:
    clear()
    slide_header(3, TOTAL, "Where DigiSearch Fits")

    print(wrap(
        "DigiSearch is the retrieval intelligence layer — the part of the system "
        "that answers structured questions about the document corpus."
    ))
    print()
    print(SINGLE)
    print()
    lines = [
        "  [Procore / SharePoint / Email / Daily Logs]",
        "              ↓  already indexed",
        "       [Azure AI Search index]",
        "              ↓  DigiSearch Azure backend",
        "       [DigiSearch  /query]",
        "              ↓  structured audit results",
        "  [Autonomous Project Auditor — reasoning layer]",
        "              ↓",
        "       [Alerts  ·  Dashboard  ·  Workflows]",
    ]
    for line in lines:
        print(line)
    print()
    print(SINGLE)
    print()
    print(wrap("What DigiSearch adds on top of raw Azure Search:"))
    print()
    print(bullet("Hybrid search  — keyword + semantic, finds relevant docs even when"))
    print(bullet("  terminology varies across document types.", indent=6, marker=" "))
    print(bullet("Metadata filters — scope queries to doc_type, project, sector, date_range."))
    print(bullet("Structured hits  — every result carries doc_id, chunk_id, score, preview."))
    print(bullet("No re-indexing   — connects to the existing Azure index as-is."))
    print()
    print(wrap(dim(
        "The auditing tool already has the index. DigiSearch plugs in and "
        "makes it answerable to structured audit questions."
    )))
    print()
    slide_footer()
    pause()


def slide_demo_intro() -> None:
    clear()
    slide_header(4, TOTAL, "Live Demo — Four Audit Checks")

    print(wrap(
        "The following four slides each run a real DigiSearch query against "
        "the document corpus and show how DigiSearch classifies the evidence."
    ))
    print()
    print(SINGLE)
    print()

    checks_summary = [
        ("MAT-01",  "SEMANTIC CONTRADICTION",  "Steel grade mismatch across documents"),
        ("INS-01",  "PROCESS GAP",             "Missing inspection reports for anchor work"),
        ("BUD-01",  "FINANCIAL DRIFT",         "Invoice vs. engineering spec discrepancy"),
        ("SAFE-01", "CLEAR",                   "Safety spec consistent with design drawings"),
    ]

    alert_map = {
        "SEMANTIC CONTRADICTION": AlertType.SEMANTIC_CONTRADICTION,
        "PROCESS GAP":            AlertType.PROCESS_GAP,
        "FINANCIAL DRIFT":        AlertType.FINANCIAL_DRIFT,
        "CLEAR":                  AlertType.CLEAR,
    }

    for check_id, alert_label, description in checks_summary:
        alert = alert_map[alert_label]
        sym   = _ALERT_SYMBOL[alert]
        col   = alert_color(alert, alert_label)
        print(f"  {sym}  {bold(check_id)}  {col}")
        print(f"       {description}")
        print()

    print(SINGLE)
    print()
    print(wrap(dim(
        "Stub mode: running against an in-memory corpus that mirrors "
        "the Ganga River Bridge documents described in the project deck."
    )))
    print()
    slide_footer()
    pause("Press Enter to run check MAT-01")


def slide_demo_check(idx: int, corpus: list) -> None:
    check  = AUDIT_CHECKS[idx]
    hits   = _demo_search(corpus, check.search_query)
    result = _judge(check, hits)

    clear()
    slide_header(4 + idx + 1, TOTAL, f"Check {check.id} — {check.title}")

    print(wrap(check.description))
    print()
    print(SINGLE)
    print()
    print(f"  {dim('Query →')}  \"{check.search_query}\"")
    scope = ", ".join(check.doc_types_in_scope)
    print(f"  {dim('Scope →')}  {scope}")
    print()
    print(SINGLE)
    print()

    # Evidence
    print(f"  {dim('Evidence retrieved:')}")
    for doc_id, content, score in result.evidence[:3]:
        print()
        print(f"    {dim(doc_id)}  ·  score {score}")
        preview = textwrap.fill(
            f'"{content}..."',
            width=W - 8,
            initial_indent="    ",
            subsequent_indent="    ",
        )
        print(preview)

    print()
    print(SINGLE)
    print()

    sym   = _ALERT_SYMBOL[result.alert]
    label = alert_color(result.alert, result.alert.value)
    print(f"  {sym}  {bold(label)}")
    print()
    finding = textwrap.fill(
        result.finding, width=W - 6, initial_indent="  ", subsequent_indent="  "
    )
    print(finding)
    print()
    slide_footer()

    next_labels = [
        "Press Enter to run check INS-01",
        "Press Enter to run check BUD-01",
        "Press Enter to run check SAFE-01",
        "Press Enter for summary",
    ]
    pause(next_labels[idx] if idx < len(next_labels) else "Press Enter to continue")


def slide_summary(corpus: list) -> None:
    clear()
    slide_header(9, TOTAL, "Audit Summary — Ganga River Bridge · Sector 4")

    results = [_judge(check, _demo_search(corpus, check.search_query))
               for check in AUDIT_CHECKS]

    print()
    for r in results:
        sym   = _ALERT_SYMBOL[r.alert]
        label = alert_color(r.alert, f"{r.alert.value:<28}")
        print(f"  {sym}  {label}  {r.check.id}")
        wrapped_finding = textwrap.fill(
            r.finding, width=W - 10, initial_indent="       ", subsequent_indent="       "
        )
        print(wrapped_finding)
        print()

    print(SINGLE)
    print()

    for alert_type, count_label in [
        (AlertType.SEMANTIC_CONTRADICTION, "Semantic contradictions"),
        (AlertType.PROCESS_GAP,            "Process gaps"),
        (AlertType.FINANCIAL_DRIFT,        "Financial drift"),
        (AlertType.CLEAR,                  "Clear"),
    ]:
        count = sum(1 for r in results if r.alert == alert_type)
        sym   = _ALERT_SYMBOL[alert_type]
        col   = alert_color(alert_type, f"{count_label}")
        print(f"  {sym}  {col:<40}  {count} / {len(results)}")

    print()
    print(SINGLE)
    print()
    print(wrap(
        "Three of four checks surface active issues. All findings are "
        "cited back to specific documents with relevance scores — "
        "ready for human review or automated workflow dispatch."
    ))
    print()
    slide_footer()
    pause("Press Enter for architectural paths")


def slide_architecture() -> None:
    clear()
    slide_header(10, TOTAL, "Where This Goes Next — Five Paths")

    paths = [
        (
            "A  Now",
            "Retrieval layer (today)",
            "DigiSearch answers structured questions. The auditing tool's LLM "
            "does the reasoning. Zero changes to DigiSearch needed.",
        ),
        (
            "B  Near-term",
            "Contradiction detection on /query",
            "Add an optional contradiction_check flag. DigiSearch compares "
            "retrieved chunks via LLM and returns a contradiction_score per pair.",
        ),
        (
            "C  Near-term",
            "Stored triggers + webhooks",
            "DigiSearch registers audit checks and re-runs them when new documents "
            "are indexed. Fires a webhook when a threshold is crossed — real-time "
            "monitoring instead of batch audits.",
        ),
        (
            "D  Medium-term",
            "Document lineage + sequence rules",
            "DigiSearch tracks expected document sequences: RFI → inspection_report "
            "→ approval. Surfaces gaps when a stage is skipped. Directly addresses "
            "missing audit trail detection.",
        ),
        (
            "E  Long-term",
            "Construction knowledge graph (Uniclass)",
            "Integrates the construction domain taxonomy so semantically related "
            "terms (anchor bolt, load-bearing joint, ASTM F3125) are searched "
            "together. Reduces false negatives from terminology inconsistency.",
        ),
    ]

    for tag, title, description in paths:
        print(f"  {bold(tag)}")
        print(f"  {title}")
        print(wrap(description, indent=4))
        print()

    slide_footer("Full detail: .cache/research/digisearch-auditing-architecture.md")
    pause("Press Enter for discussion points")


def slide_discussion() -> None:
    clear()
    slide_header(11, TOTAL, "Discussion")

    print(wrap("Key questions to explore with the team:"))
    print()

    questions = [
        "What does the current Azure AI Search index schema look like? "
        "Which fields are filterable — doc_type, project, sector, date?",

        "What document types are already indexed? "
        "How reliable is the doc_type classification today?",

        "Is the auditing pipeline batch (scheduled) or event-driven "
        "(triggered by new document ingestion)?",

        "Which of the four alert types — SEMANTIC CONTRADICTION, PROCESS GAP, "
        "FINANCIAL DRIFT — is the highest priority to detect first?",

        "What does the human-in-the-loop step look like? "
        "Who reviews the alerts, and what action do they take?",

        "Is the Uniclass taxonomy already in use for document classification, "
        "or would that be a new addition?",
    ]

    for i, q in enumerate(questions, 1):
        print(f"  {dim(str(i) + '.')} {wrap(q, indent=5).lstrip()}")
        print()

    print(SINGLE)
    print()
    print(wrap(
        "DigiSearch is backend-neutral — it adds the intelligence layer "
        "on top of whatever index the auditing tool already has. "
        "The goal is to make the index answerable to structured audit questions "
        "without changing the underlying infrastructure."
    ))
    print()
    slide_footer("End of presentation")
    print()
    print(c(dim("Run the audit engine standalone:")))
    print(c(dim("DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_rag_demo")))
    print()
    print(DOUBLE)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    using_azure = bool(
        os.environ.get("AZURE_SEARCH_ENDPOINT") and os.environ.get("AZURE_SEARCH_API_KEY")
    )
    using_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1", "true", "yes"
    )

    if not using_azure and not using_stub:
        print(
            "\nNo backend configured.\n\n"
            "  Stub mode:   DIGISEARCH_ALLOW_STUB=1 python -m digisearch.demos.audit_presentation\n"
            "  Live Azure:  AZURE_SEARCH_ENDPOINT=... AZURE_SEARCH_API_KEY=... \\\n"
            "               AZURE_SEARCH_INDEX_NAME=... "
            "python -m digisearch.demos.audit_presentation\n"
        )
        return

    corpus = _demo_corpus() if not using_azure else None

    slide_title()
    slide_problem()
    slide_current_tools()
    slide_digisearch_role()
    slide_demo_intro()

    for i in range(len(AUDIT_CHECKS)):
        slide_demo_check(i, corpus)

    slide_summary(corpus)
    slide_architecture()
    slide_discussion()


if __name__ == "__main__":
    main()
