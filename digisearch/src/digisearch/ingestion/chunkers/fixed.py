"""FixedSizeChunker - token/character count based."""

from __future__ import annotations

import uuid

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker


class FixedSizeChunker(Chunker):
    """Chunk by character count. Fast, uniform chunks."""

    def __init__(self, chunk_size: int = 512, overlap: int = 0) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

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
            cid = f"{doc.id}_{i}"
            chunks.append(
                Chunk(
                    id=cid,
                    content=content,
                    doc_id=doc.id,
                    embedding=None,
                    metadata={"chunk_index": i, "start": start, "end": end},
                )
            )
            start = end - self.overlap
            i += 1
        return chunks
