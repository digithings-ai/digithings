"""Semantic chunker using embedding cosine distance."""

from __future__ import annotations

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker
from digisearch.ingestion.chunkers.recursive import RecursiveChunker


class SemanticChunker(Chunker):
    """Chunk by semantic similarity. Splits when cosine distance exceeds threshold."""

    def __init__(
        self,
        embedder: object | None = None,
        threshold: float = 0.5,
        min_chunk_size: int = 100,
        fallback_chunk_size: int = 512,
    ) -> None:
        self.embedder = embedder
        self.threshold = threshold
        self.min_chunk_size = min_chunk_size
        self._fallback = RecursiveChunker(chunk_size=fallback_chunk_size)

    def _batch_embed(self, sentences: list[str]) -> list[list[float]]:
        """Embed *sentences* in one batch call.

        Tries ``embedder.embed_batch(sentences)`` first (explicit batch API),
        then ``embedder.embed(sentences)`` (list-accepting single method),
        then per-sentence ``embedder.embed(s)`` as a last resort for embedders
        that only handle a single string at a time.
        """
        if hasattr(self.embedder, "embed_batch"):
            return self.embedder.embed_batch(sentences)
        result = self.embedder.embed(sentences)  # type: ignore[union-attr]
        # If the embedder returned a flat vector instead of a list-of-vectors it
        # only handles one string at a time — fall back to sequential calls.
        if result and isinstance(result[0], (int, float)):
            return [self.embedder.embed(s) for s in sentences]  # type: ignore[union-attr]
        return result

    def chunk(self, doc: Document) -> list[Chunk]:
        if not self.embedder or (not hasattr(self.embedder, "embed") and not hasattr(self.embedder, "embed_batch")):
            return self._fallback.chunk(doc)
        text = doc.content
        if len(text) < self.min_chunk_size:
            return [
                Chunk(
                    id=f"{doc.id}_0",
                    content=text,
                    doc_id=doc.id,
                    embedding=None,
                    metadata={"chunk_index": 0},
                )
            ]
        try:
            sentences = text.replace("!", ".").replace("?", ".").split(".")
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) < 2:
                return self._fallback.chunk(doc)
            embs = self._batch_embed(sentences)
            chunks: list[Chunk] = []
            current = [sentences[0]]
            for i in range(1, len(sentences)):
                sim = self._cosine(embs[i - 1], embs[i])
                if sim < (1 - self.threshold) and sum(len(s) for s in current) >= self.min_chunk_size:
                    content = " ".join(current)
                    chunks.append(
                        Chunk(
                            id=f"{doc.id}_{len(chunks)}",
                            content=content,
                            doc_id=doc.id,
                            embedding=None,
                            metadata={"chunk_index": len(chunks)},
                        )
                    )
                    current = [sentences[i]]
                else:
                    current.append(sentences[i])
            if current:
                content = " ".join(current)
                chunks.append(
                    Chunk(
                        id=f"{doc.id}_{len(chunks)}",
                        content=content,
                        doc_id=doc.id,
                        embedding=None,
                        metadata={"chunk_index": len(chunks)},
                    )
                )
            return chunks
        except Exception:
            return self._fallback.chunk(doc)

    def _cosine(self, a: list[float], b: list[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
