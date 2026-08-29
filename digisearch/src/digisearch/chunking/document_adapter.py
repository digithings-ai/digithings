"""Adapt a text :class:`~digisearch.chunking.backend.ChunkerBackend` to Document chunking."""

from __future__ import annotations

from digisearch.chunking.backend import ChunkerBackend
from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker


class BackendDocumentChunker(Chunker):
    """Document-facing :class:`~digisearch.ingestion.chunkers.base.Chunker` over a text backend."""

    def __init__(self, backend: ChunkerBackend) -> None:
        self.backend = backend

    def chunk(self, doc: Document) -> list[Chunk]:
        chunks = self.backend.chunk(doc.content)
        for i, c in enumerate(chunks):
            c.id = f"{doc.id}_{i}"
            c.doc_id = doc.id
            meta = dict(c.metadata or {})
            meta["chunk_index"] = i
            c.metadata = meta
        return chunks
