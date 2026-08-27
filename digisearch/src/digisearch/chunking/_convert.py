"""Shared conversion from Chonkie chunk objects to digisearch Chunks."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — Chonkie chunk objects are duck-typed

from digisearch.core.models import Chunk


def chonkie_chunks_to_digisearch(chonkie_chunks: list[Any]) -> list[Chunk]:
    """Map Chonkie ``Chunk`` objects (``.text``, indices, token_count) to digisearch Chunks.

    ``doc_id`` is left empty; :class:`~digisearch.chunking.document_adapter.BackendDocumentChunker`
    fills ids after a Document is available.
    """
    out: list[Chunk] = []
    for i, raw in enumerate(chonkie_chunks):
        text = getattr(raw, "text", None)
        if text is None:
            text = str(raw)
        if not str(text).strip():
            continue
        start = getattr(raw, "start_index", None)
        end = getattr(raw, "end_index", None)
        token_count = getattr(raw, "token_count", None)
        meta: dict[str, Any] = {"chunk_index": i, "chunker": "chonkie"}
        if start is not None:
            meta["start"] = int(start)
        if end is not None:
            meta["end"] = int(end)
        if token_count is not None:
            meta["token_count"] = int(token_count)
        out.append(
            Chunk(
                id=f"chunk_{len(out)}",
                content=str(text),
                doc_id="",
                embedding=None,
                metadata=meta,
            )
        )
    # Re-number after skipping empties so chunk_index is dense.
    for i, chunk in enumerate(out):
        chunk.id = f"chunk_{i}"
        chunk.metadata["chunk_index"] = i
    return out
