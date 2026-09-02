"""Versioned trace events for digigraph streaming (digichat, observability)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TraceEventType = Literal[
    "graph_step",
    "tool_call",
    "tool_result",
    "rag_sources",
    "code_block",
    "span",
    "graph_update",
    "round_boundary",
]


# Matches digichat ``MAX_NOTE_BODY_CHARS`` — DocumentPane needs the full note (#3419).
MAX_RAG_SOURCE_BODY_CHARS = 80_000


class RagSourceItem(BaseModel):
    """One citation from digisearch-style results."""

    source_id: str | None = Field(
        default=None,
        description="Stable id for citations in ResearchBrief (e.g. doc_id#rank).",
    )
    doc_id: str | None = None
    score: float | None = None
    snippet: str | None = Field(
        default=None, description="Short content preview; not full row payload."
    )
    body: str | None = Field(
        default=None,
        description=(
            "Full note markdown for digichat DocumentPane (#3419). "
            "Only set on digivault_get_note paths; capped at MAX_RAG_SOURCE_BODY_CHARS."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


def rag_sources_from_results(
    results: list[dict[str, Any]],
    *,
    max_items: int = 20,
    snippet_len: int = 400,
    include_body: bool = False,
    body_max: int = MAX_RAG_SOURCE_BODY_CHARS,
) -> list[dict[str, Any]]:
    """Build RAG citation list for trace/UI from digisearch result dicts (redacted size).

    Pass ``include_body=True`` for digivault_get_note so digichat can render the
    full note in DocumentPane. Locate tools keep snippet-only items (no body).
    """
    out: list[dict[str, Any]] = []
    for r in results[:max_items]:
        if not isinstance(r, dict):
            continue
        content = r.get("content")
        snip = str(content).strip() if content is not None else ""
        if len(snip) > snippet_len:
            snip = snip[: snippet_len - 1].rstrip() + "…"
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        score = r.get("score")
        sc: float | None = float(score) if isinstance(score, (int, float)) else None
        doc_id = r.get("doc_id")
        rank = r.get("rank")
        source_id: str | None = None
        if doc_id is not None and rank is not None:
            source_id = f"{doc_id}#{rank}"
        elif doc_id is not None:
            source_id = str(doc_id)
        body: str | None = None
        if include_body:
            raw_body = r.get("body")
            if not isinstance(raw_body, str) or not raw_body.strip():
                raw_body = r.get("body_markdown")
            if not isinstance(raw_body, str) or not raw_body.strip():
                raw_body = content if content is not None else None
            if isinstance(raw_body, str) and raw_body.strip():
                text = raw_body.strip()
                body = text if len(text) <= body_max else text[:body_max]
        item = RagSourceItem(
            source_id=source_id,
            doc_id=str(doc_id) if doc_id is not None else None,
            score=sc,
            snippet=snip or None,
            body=body,
            metadata={k: meta[k] for k in list(meta.keys())[:16]},
        )
        out.append(item.model_dump(exclude_none=True))
    return out


def merge_rag_sources_accumulator(
    acc: list[dict[str, Any]], new_items: list[dict[str, Any]] | None
) -> None:
    """Append *new_items* to *acc*, de-duplicating by source_id then doc_id."""
    if not new_items:
        return
    seen = {
        x.get("source_id") or x.get("doc_id") for x in acc if x.get("source_id") or x.get("doc_id")
    }
    for item in new_items:
        if not isinstance(item, dict):
            continue
        key = item.get("source_id") or item.get("doc_id")
        if key is None:
            acc.append(item)
            continue
        ks = str(key)
        if ks in seen:
            continue
        seen.add(ks)
        acc.append(item)


class TraceEventV1(BaseModel):
    """Canonical trace envelope (v1). Transport may wrap in SSE or message deltas."""

    v: Literal[1] = 1
    type: TraceEventType
    workflow_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
