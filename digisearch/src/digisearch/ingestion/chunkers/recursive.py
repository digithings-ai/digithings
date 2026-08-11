"""Recursive chunker with hierarchical delimiters."""

from __future__ import annotations

import logging
import time

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker

logger = logging.getLogger(__name__)

# ~512 tokens at a ~4-chars/token heuristic — the benchmarked default chunk size for
# general RAG. Deliberately character-based: no tokenizer dependency is introduced.
DEFAULT_CHUNK_CHARS = 2000
DEFAULT_CHUNK_OVERLAP = 250  # ~12.5%, holding the previous 64/512 ratio


class RecursiveChunker(Chunker):
    """Chunk by hierarchical delimiters: \\n\\n\\n, \\n\\n, \\n, space."""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
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
                        # Guard against non-progress: str.split on a non-empty
                        # separator that is actually present always yields parts
                        # strictly shorter than the input, so len(p) < len(text)
                        # here for every normal delimited split. The only way p
                        # comes back the same length as text is the separator
                        # search exhausting every real separator and falling
                        # through to sep="" (parts = [text] unchanged) — i.e. a
                        # delimiter-free run. Checking length directly (instead
                        # of trusting the separator list) means even a future
                        # edit to `_separators` can't reopen the infinite
                        # recursion from issue #2180: recursing on unreduced
                        # input is structurally impossible, not just unlikely.
                        if len(p) < len(text):
                            sub = self._split(p, doc_id, idx)
                        else:
                            sub = self._hard_split(p, doc_id, idx)
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

    def _hard_split(self, text: str, doc_id: str, chunk_index: int) -> list[Chunk]:
        """Force-split a delimiter-free run into fixed-size pieces at character
        boundaries. Reached only when `text` is longer than `chunk_size` and
        contains none of `_separators` — e.g. base64-embedded assets, minified
        JS/CSS, long unbroken table rows or hashes, or CJK text without spaces
        or punctuation (issue #2180). Content-aware splitting is impossible
        here, so this slices by character count instead, iteratively (never
        recursing into `_split`), which makes the loop's termination
        independent of chunk_size/chunk_overlap values."""
        step = max(1, self.chunk_size - self.chunk_overlap)
        chunks: list[Chunk] = []
        idx = chunk_index
        pos = 0
        n = len(text)
        while pos < n:
            piece = text[pos : pos + self.chunk_size].strip()
            if piece:
                chunks.append(
                    Chunk(
                        id=f"{doc_id}_{idx}",
                        content=piece,
                        doc_id=doc_id,
                        embedding=None,
                        metadata={"chunk_index": idx},
                    )
                )
                idx += 1
            pos += step
        return chunks
