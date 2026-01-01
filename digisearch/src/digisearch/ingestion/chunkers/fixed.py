"""Fixed-size character chunker."""

from __future__ import annotations

import logging
import time

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker

logger = logging.getLogger(__name__)


class FixedSizeChunker(Chunker):
    """Chunk by character count. Fast, uniform chunks."""

    def __init__(self, chunk_size: int = 512, overlap: int = 0) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc: Document) -> list[Chunk]:
        perf_start = time.perf_counter()
        text = doc.content
        if not text:
            logger.info(
                "fixed chunk empty doc",
                extra={
                    "operation": "chunk_fixed",
                    "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                    "outcome": "ok",
                    "doc_id": doc.id,
                    "chunk_count": 0,
                },
            )
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
        logger.info(
            "fixed chunk done",
            extra={
                "operation": "chunk_fixed",
                "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                "outcome": "ok",
                "doc_id": doc.id,
                "chunk_count": len(chunks),
                "chunk_size": self.chunk_size,
            },
        )
        return chunks
