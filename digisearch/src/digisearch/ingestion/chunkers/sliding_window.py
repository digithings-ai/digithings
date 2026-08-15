"""Sliding-window chunker with overlap."""

from __future__ import annotations

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker


class SlidingWindowChunker(Chunker):
    """Chunk with sliding window. Overlap preserves context continuity."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.step = max(1, chunk_size - overlap)

    def chunk(self, doc: Document) -> list[Chunk]:
        text = doc.content
        if not text:
            return []
        chunks: list[Chunk] = []
        start = 0
        i = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            content = text[start:end]
            chunks.append(
                Chunk(
                    id=f"{doc.id}_{i}",
                    content=content,
                    doc_id=doc.id,
                    embedding=None,
                    metadata={"chunk_index": i, "start": start, "end": end},
                )
            )
            start += self.step
            i += 1
        return chunks
