"""ChromaDB backend for digisearch. Implements DigiIndex."""

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
from digisearch.embedding.providers.minilm import get_default_minilm_embedder
from digisearch.indexes.backends.chroma_errors import EmbeddingModelMismatchError
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings

    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_META_MODEL_ID = "embedding_model_id"
_META_DIMENSIONS = "embedding_dimensions"
_META_VERSION = "embedding_version"


def _get_default_embedder() -> object:
    """Return the process-wide MiniLMEmbedder (Chroma's historical default model)."""
    return get_default_minilm_embedder()


def _provider_model_id(provider: object) -> str:
    mid = getattr(provider, "model_id", None)
    if isinstance(mid, str) and mid.strip():
        return mid.strip()
    from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder

    if isinstance(provider, MiniLMEmbedder):
        return MINILM_MODEL_ID
    return type(provider).__name__


def _provider_dimensions(provider: object) -> int:
    dims = getattr(provider, "dimensions", None)
    if isinstance(dims, int) and dims > 0:
        return dims
    from digisearch.embedding.providers.minilm import MINILM_DIMENSIONS, MiniLMEmbedder

    if isinstance(provider, MiniLMEmbedder):
        return MINILM_DIMENSIONS
    raise TypeError(f"embedding provider {type(provider)!r} has no dimensions")


def _provider_version(provider: object) -> str:
    ver = getattr(provider, "version", None)
    if isinstance(ver, str) and ver.strip():
        return ver.strip()
    return "1"


class ChromaBackend(DigiIndex):
    """ChromaDB-backed DigiIndex. Persistent or in-memory.

    Always embeds via an injected or default ``EmbeddingProvider`` (MiniLM by
    default — the same ONNX model Chroma previously used internally). Partial
    embedding batches raise instead of silently discarding supplied vectors and
    falling back to Chroma's bundled embedder (that discard path corrupted
    indexes when only some chunks carried precomputed embeddings).
    """

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
        provider = self._resolved_provider()
        create_meta: dict[str, Any] = {
            "hnsw:space": "cosine",
            _META_MODEL_ID: _provider_model_id(provider),
            _META_DIMENSIONS: _provider_dimensions(provider),
            _META_VERSION: _provider_version(provider),
        }
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata=create_meta,
        )
        self._assert_collection_model(provider)

    def _resolved_provider(self) -> object:
        return self.embedding_provider or _get_default_embedder()

    def _collection_count(self) -> int:
        count_fn = getattr(self._collection, "count", None)
        if callable(count_fn):
            try:
                return int(count_fn())
            except Exception:
                return 0
        return 0

    def _assert_collection_model(self, provider: object) -> None:
        meta = dict(getattr(self._collection, "metadata", None) or {})
        expected_id = _provider_model_id(provider)
        expected_dims = str(_provider_dimensions(provider))
        expected_ver = _provider_version(provider)
        checks = (
            (_META_MODEL_ID, expected_id),
            (_META_DIMENSIONS, expected_dims),
            (_META_VERSION, expected_ver),
        )
        present = [(key, str(meta.get(key) or "").strip(), exp) for key, exp in checks]
        if not any(existing for _, existing, _ in present):
            return
        for key, existing, exp in present:
            if existing and existing != exp:
                raise EmbeddingModelMismatchError(
                    f"Chroma collection {self.name!r} {key}={existing!r} "
                    f"does not match provider {exp!r}; re-index or use the original model"
                )

    def _stamp_collection_metadata(self, provider: object) -> None:
        meta = dict(getattr(self._collection, "metadata", None) or {})
        desired = {
            **meta,
            "hnsw:space": meta.get("hnsw:space") or "cosine",
            _META_MODEL_ID: _provider_model_id(provider),
            _META_DIMENSIONS: _provider_dimensions(provider),
            _META_VERSION: _provider_version(provider),
        }
        if all(
            str(meta.get(k) or "") == str(desired[k])
            for k in (
                _META_MODEL_ID,
                _META_DIMENSIONS,
                _META_VERSION,
            )
        ):
            return
        if not str(meta.get(_META_MODEL_ID) or "").strip() and self._collection_count() > 0:
            # Populated legacy collections may hold vectors from an unknown model;
            # stamping the current provider would invent false compatibility.
            logger.warning(
                "chroma collection %r has vectors but no embedding_model_id; "
                "refusing to auto-stamp (re-index or migrate metadata explicitly)",
                self.name,
            )
            return
        modify = getattr(self._collection, "modify", None)
        if callable(modify):
            modify(metadata=desired)
            # Keep in-memory mocks / clients consistent for subsequent asserts.
            try:
                self._collection.metadata = desired
            except Exception:
                # Some Chroma clients expose metadata as read-only.
                pass

    def add(self, chunks: list[Chunk]) -> None:
        start = time.perf_counter()
        if not chunks:
            return
        provider = self._resolved_provider()
        self._assert_collection_model(provider)
        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        have_emb = [c.embedding is not None for c in chunks]
        if any(have_emb) and not all(have_emb):
            missing = [c.id for c, ok in zip(chunks, have_emb, strict=True) if not ok]
            raise ValueError(
                "partial embedding batch refused: chunks missing precomputed embeddings "
                f"{missing!r}; supply embeddings for every chunk or for none "
                "(silent discard of supplied vectors previously fell through to "
                "Chroma's bundled embedder and corrupted the index)"
            )
        if all(have_emb):
            embeddings: list[list[float]] | None = [
                [float(v) for v in c.embedding]  # type: ignore[arg-type]
                for c in chunks
            ]
        else:
            raw = provider.embed([c.content for c in chunks])  # type: ignore[attr-defined]
            embeddings = [[float(v) for v in vec] for vec in raw]
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk.embedding = embedding
        metadatas = [
            {**normalize_metadata_for_chroma(c.metadata), "doc_id": c.doc_id} for c in chunks
        ]
        self._stamp_collection_metadata(provider)
        try:
            self._collection.upsert(
                ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
            )
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
                "with_embeddings": True,
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
        provider = self._resolved_provider()
        self._assert_collection_model(provider)
        try:
            if query.embedding:
                results = self._collection.query(
                    query_embeddings=[query.embedding],
                    **q_kw,
                )
            else:
                vector = provider.embed([query.text])[0]  # type: ignore[attr-defined]
                results = self._collection.query(
                    query_embeddings=[[float(v) for v in vector]],
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
            # In-memory: no-op (would need to re-add all docs to a new persistent client)
            pass
