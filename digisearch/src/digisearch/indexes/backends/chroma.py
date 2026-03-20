"""ChromaDB backend for DigiSearch. Implements DigiIndex."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from digisearch.core.models import Chunk, Query, Result
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings

    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


class ChromaBackend(DigiIndex):
    """ChromaDB-backed DigiIndex. Persistent or in-memory."""

    def __init__(
        self,
        name: str,
        persist_path: str | Path | None = None,
        embedding_provider: object | None = None,
    ) -> None:
        if not _CHROMA_AVAILABLE:
            raise ImportError("Install digisearch[chroma] for ChromaDB backend")
        self.name = name
        self.embedding_provider = embedding_provider
        self._persist_path = str(persist_path) if persist_path else None
        self._client = chromadb.PersistentClient(path=self._persist_path) if self._persist_path else chromadb.Client(Settings(anonymized_telemetry=False))
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        embeddings = [c.embedding for c in chunks if c.embedding is not None]
        if len(embeddings) != len(chunks):
            embeddings = None
        metadatas = [{"doc_id": c.doc_id, **c.metadata} for c in chunks]
        if embeddings:
            self._collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        else:
            self._collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, query: Query) -> list[Result]:
        n = min(query.top_k, 100)
        try:
            if query.embedding:
                results = self._collection.query(
                    query_embeddings=[query.embedding],
                    n_results=n,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                results = self._collection.query(
                    query_texts=[query.text],
                    n_results=n,
                    include=["documents", "metadatas", "distances"],
                )
        except Exception:
            logger.error("ChromaDB query failed for collection %r", self.name, exc_info=True)
            return []
        out: list[Result] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for i, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            meta = meta or {}
            doc_id = meta.get("doc_id", cid)
            chunk = Chunk(id=cid, content=doc or "", doc_id=doc_id, embedding=None, metadata=meta)
            score = 1.0 - (dist / 2.0) if dist is not None else 1.0
            out.append(Result(chunk=chunk, score=score, rank=i + 1))
        return out

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    def update(self, chunks: list[Chunk]) -> None:
        self.add(chunks)

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]

    def snapshot(self, path: str) -> None:
        """Export snapshot. For persistent client, copy to path."""
        import shutil

        if self._persist_path:
            shutil.copytree(self._persist_path, path, dirs_exist_ok=True)
        else:
            # In-memory: no-op (would need to re-add all docs to new persistent client)
            pass
