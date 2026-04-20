"""RecursiveChunker - hierarchical delimiter splits. LangChain-style."""

from __future__ import annotations

import logging
import time

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker

logger = logging.getLogger(__name__)


class RecursiveChunker(Chunker):
    """Chunk by hierarchical delimiters: \\n\\n\\n, \\n\\n, \\n, space."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._separators = ["\n\n\n", "\n\n", "\n", ". ", " ", ""]

    def chunk(self, doc: Document) -> list[Chunk]:
        start = time.perf_counter()
        try:
            chunks = self._split(doc.content, doc.id, 0)
        except Exception:
            logger.exception(
                "recursive chunk failed",
                extra={
                    "operation": "chunk_recursive",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "doc_id": doc.id,
                },
            )
            raise
        logger.info(
            "recursive chunk done",
            extra={
                "operation": "chunk_recursive",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "doc_id": doc.id,
                "chunk_count": len(chunks),
                "chunk_size": self.chunk_size,
            },
        )
        return chunks

    def _split(self, text: str, doc_id: str, chunk_index: int) -> list[Chunk]:
        if not text.strip():
            return []
        if len(text) <= self.chunk_size:
            return [
                Chunk(
                    id=f"{doc_id}_{chunk_index}",
                    content=text.strip(),
                    doc_id=doc_id,
                    embedding=None,
                    metadata={"chunk_index": chunk_index},
                )
            ]
        sep = self._separators[0]
        for s in self._separators[1:]:
            if s in text:
                sep = s
                break
        parts = text.split(sep) if sep else [text]
        chunks: list[Chunk] = []
        current = ""
        idx = chunk_index
        for i, p in enumerate(parts):
            candidate = current + (sep if current and sep else "") + p
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(
                        Chunk(
                            id=f"{doc_id}_{idx}",
                            content=current.strip(),
                            doc_id=doc_id,
                            embedding=None,
                            metadata={"chunk_index": idx},
                        )
                    )
                    idx += 1
                    overlap = current[-self.chunk_overlap :] if self.chunk_overlap else ""
                    current = overlap + (sep if sep else "") + p
                else:
                    if len(p) > self.chunk_size:
                        sub = self._split(p, doc_id, idx)
                        chunks.extend(sub)
                        idx += len(sub)
                    else:
                        chunks.append(
                            Chunk(
                                id=f"{doc_id}_{idx}",
                                content=p.strip(),
                                doc_id=doc_id,
                                embedding=None,
                                metadata={"chunk_index": idx},
                            )
                        )
                        idx += 1
                    current = ""
        if current.strip():
            chunks.append(
                Chunk(
                    id=f"{doc_id}_{idx}",
                    content=current.strip(),
                    doc_id=doc_id,
                    embedding=None,
                    metadata={"chunk_index": idx},
                )
            )
        return chunks
