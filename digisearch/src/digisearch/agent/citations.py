"""RAG citation items aligned with DigiGraph ``rag_sources_from_results`` / trace UI."""

from __future__ import annotations

from typing import Any


def rag_sources_from_hits(
    results: list[dict[str, Any]],
    *,
    max_items: int = 20,
    snippet_len: int = 400,
) -> list[dict[str, Any]]:
    """Build citation dicts with ``source_id`` (``doc_id#rank``), snippet, and normative metadata."""
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
        chunk_id = r.get("chunk_id")
        source_id: str | None = None
        if doc_id is not None and chunk_id:
            source_id = f"{doc_id}#{chunk_id}"
        elif doc_id is not None and rank is not None:
            source_id = f"{doc_id}#{rank}"
        elif doc_id is not None:
            source_id = str(doc_id)
        item: dict[str, Any] = {
            "source_id": source_id,
            "doc_id": str(doc_id) if doc_id is not None else None,
            "chunk_id": str(chunk_id) if chunk_id else None,
            "score": sc,
            "snippet": snip or None,
            "metadata": {k: meta[k] for k in list(meta.keys())[:16]},
        }
        out.append({k: v for k, v in item.items() if v is not None})
    return out
