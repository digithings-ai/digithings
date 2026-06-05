"""ChromaDB backend for DigiSearch. Implements DigiIndex."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from digisearch.core.chroma_where import structured_filters_to_chroma_where
from digisearch.core.evidence_metadata import normalize_metadata_for_chroma
from digisearch.core.filter_apply import chunk_metadata_matches
from digisearch.core.models import Chunk, Query, Result
from digisearch.core.workspace_filter import chunk_matches_workspace
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
        *,
        chroma_host: str | None = None,
        chroma_port: int = 8000,
    ) -> None:
        if not _CHROMA_AVAILABLE:
            raise ImportError("Install digisearch[chroma] for ChromaDB backend")
        self.name = name
        self.embedding_provider = embedding_provider
        self._persist_path = str(persist_path) if persist_path else None
        if chroma_host and not self._persist_path:
            self._client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        elif self._persist_path:
            self._client = chromadb.PersistentClient(path=self._persist_path)
        else:
            self._client = chromadb.Client(Settings(anonymized_telemetry=False))
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: list[Chunk]) -> None:
        start = time.perf_counter()
        if not chunks:
            return
        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        embeddings = [c.embedding for c in chunks if c.embedding is not None]
        if len(embeddings) != len(chunks):
            embeddings = None
        metadatas = [
            {"doc_id": c.doc_id, **normalize_metadata_for_chroma(c.metadata)} for c in chunks
        ]
        try:
            if embeddings:
                self._collection.add(
                    ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
                )
            else:
                self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        except (OSError, RuntimeError, TypeError, ValueError):
            logger.exception(
                "chroma index failed",
                extra={
                    "operation": "chroma_index",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "collection": self.name,
                    "chunk_count": len(chunks),
                },
            )
            raise
        logger.info(
            "chroma index done",
            extra={
                "operation": "chroma_index",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "collection": self.name,
                "chunk_count": len(chunks),
                "with_embeddings": bool(embeddings),
            },
        )

    def query(self, query: Query) -> list[Result]:
        perf_start = time.perf_counter()
        n = min(query.top_k, 100)
        filters_dict = query.filters or {}
        structured = (
            filters_dict.get("structured")
            if isinstance(filters_dict.get("structured"), list)
            else None
        )
        chroma_where = structured_filters_to_chroma_where(structured)
        fetch_n = min(100, max(n, n * 25)) if structured else n
        q_kw: dict[str, Any] = {
            "n_results": fetch_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if chroma_where:
            q_kw["where"] = chroma_where
        try:
            if query.embedding:
                results = self._collection.query(
                    query_embeddings=[query.embedding],
                    **q_kw,
                )
            else:
                results = self._collection.query(
                    query_texts=[query.text],
                    **q_kw,
                )
        except (OSError, RuntimeError, TypeError, ValueError):
            logger.error(
                "ChromaDB query failed for collection %r",
                self.name,
                exc_info=True,
                extra={
                    "operation": "chroma_query",
                    "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                    "outcome": "error",
                    "collection": self.name,
                    "top_k": n,
                },
            )
            return []
        out: list[Result] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        rank = 0
        for cid, doc, meta, dist in zip(ids, docs, metas, dists):
            meta = meta or {}
            if structured and not chunk_metadata_matches(structured, meta):
                continue
            if not chunk_matches_workspace(meta, query.workspace_id):
                continue
            doc_id = meta.get("doc_id", cid)
            chunk = Chunk(id=cid, content=doc or "", doc_id=doc_id, embedding=None, metadata=meta)
            score = 1.0 - (dist / 2.0) if dist is not None else 1.0
            rank += 1
            out.append(Result(chunk=chunk, score=score, rank=rank))
            if len(out) >= n:
                break
        logger.info(
            "chroma query done",
            extra={
                "operation": "chroma_query",
                "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                "outcome": "ok",
                "collection": self.name,
                "top_k": n,
                "result_count": len(out),
            },
        )
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
