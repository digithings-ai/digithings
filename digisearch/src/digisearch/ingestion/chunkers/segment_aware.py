"""Segment-aware chunker. A structural segment is one chunk unless it exceeds the ceiling."""

from __future__ import annotations

from digisearch.core.models import Chunk, Document, Segment
from digisearch.ingestion.chunkers.base import Chunker
from digisearch.ingestion.chunkers.recursive import DEFAULT_CHUNK_CHARS, RecursiveChunker


class SegmentAwareChunker(Chunker):
    """Chunk within ``Document.segments``, never across them.

    A segment at or under ``max_segment_chars`` becomes exactly one chunk — page-level
    retrieval for the common case. Only oversized segments are sub-split, by ``inner``.
    Documents with no segments fall through to ``inner`` unchanged.
    """

    def __init__(
        self,
        inner: Chunker | None = None,
        *,
        max_segment_chars: int = DEFAULT_CHUNK_CHARS,
    ) -> None:
        self.inner = inner if inner is not None else RecursiveChunker()
        self.max_segment_chars = max_segment_chars

    def chunk(self, doc: Document) -> list[Chunk]:
        if not doc.segments:
            return self.inner.chunk(doc)
        chunks: list[Chunk] = []
        for segment in doc.segments:
            for content in self._segment_contents(doc, segment):
                chunks.append(
                    Chunk(
                        id=f"{doc.id}_{len(chunks)}",
                        content=content,
                        doc_id=doc.id,
                        embedding=None,
                        metadata={
                            "chunk_index": len(chunks),
                            "segment_label": segment.label,
                            "segment_index": segment.index,
                        },
                    )
                )
        return chunks

    def _segment_contents(self, doc: Document, segment: Segment) -> list[str]:
        """One string per chunk this segment yields: itself, or its sub-split parts."""
        text = segment.text.strip()
        if not text:
            return []
        if len(text) <= self.max_segment_chars:
            return [text]
        sub_doc = Document(
            id=doc.id,
            content=text,
            source=doc.source,
            doc_type=doc.doc_type,
            metadata=dict(doc.metadata),
        )
        return [c.content for c in self.inner.chunk(sub_doc) if c.content.strip()]
