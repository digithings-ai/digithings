"""LightRAG-backed :class:`~digisearch.retrieval.backend.RetrievalBackend`.

Upgrade path (#402). Activates via ``DIGISEARCH_RETRIEVAL_BACKEND=lightrag``.
Uses Postgres storage when a DSN is available; embedding defaults to a local /
free model (Ollama ``nomic-embed-text`` or all-MiniLM) — never OpenAI unless
the operator explicitly opts in.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

from digisearch.core.models import Document
from digisearch.retrieval.backend import RetrievalResult
from digisearch.retrieval.pgvector import postgres_env_from_dsn, resolve_pgvector_dsn

logger = logging.getLogger(__name__)

# Local / free embedding defaults — override with DIGISEARCH_LIGHTRAG_EMBEDDING_*.
DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"
DEFAULT_EMBEDDING_DIM = 768
DEFAULT_WORKING_DIR = ".lightrag"


class LightRAGClient(Protocol):
    """Minimal async surface we need from LightRAG (real or test double)."""

    async def initialize_storages(self) -> None: ...

    async def ainsert(
        self,
        input: str | list[str],
        ids: str | list[str] | None = None,
        file_paths: str | list[str] | None = None,
    ) -> Any: ...

    async def aquery(self, query: str, param: Any | None = None) -> Any: ...

    async def adelete_by_doc_id(self, doc_ids: list[str]) -> Any: ...


def _default_embedding_env() -> None:
    """Ensure LightRAG does not silently fall back to OpenAI embeddings."""
    os.environ.setdefault("EMBEDDING_BINDING", "ollama")
    os.environ.setdefault("EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBED_MODEL)
    os.environ.setdefault("EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))
    # Prefer Ollama host if unset; operators may point at a local MiniLM proxy.
    os.environ.setdefault("EMBEDDING_BINDING_HOST", "http://127.0.0.1:11434")


def _apply_postgres_env(dsn: str | None) -> None:
    if not dsn:
        return
    for key, value in postgres_env_from_dsn(dsn).items():
        os.environ.setdefault(key, value)


def _build_default_lightrag(*, working_dir: str, use_postgres: bool) -> Any:
    try:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
    except ImportError as exc:
        raise ImportError(
            "Install digisearch[lightrag] (lightrag-hku) for LightRAGBackend"
        ) from exc

    _default_embedding_env()

    # Prefer a injectable embedding func that wraps digisearch MiniLM when
    # DIGISEARCH_LIGHTRAG_EMBEDDING=minilm (local, no Ollama required for tests).
    embed_mode = os.environ.get("DIGISEARCH_LIGHTRAG_EMBEDDING", "ollama").strip().lower()
    embedding_func: Any | None = None
    if embed_mode in {"minilm", "all-minilm", "all-minilm-l6-v2"}:
        from digisearch.embedding.providers.minilm import (
            MINILM_DIMENSIONS,
            get_default_minilm_embedder,
        )

        embedder = get_default_minilm_embedder()

        async def _minilm_embed(texts: list[str]) -> list[list[float]]:
            return embedder.embed(list(texts))

        embedding_func = EmbeddingFunc(
            embedding_dim=MINILM_DIMENSIONS,
            max_token_size=8192,
            func=_minilm_embed,
        )

    kwargs: dict[str, Any] = {"working_dir": working_dir}
    if embedding_func is not None:
        kwargs["embedding_func"] = embedding_func
    if use_postgres:
        kwargs.update(
            {
                "kv_storage": "PGKVStorage",
                "vector_storage": "PGVectorStorage",
                "graph_storage": "PGTableGraphStorage",
                "doc_status_storage": "PGDocStatusStorage",
            }
        )

    # LLM is required by LightRAG for graph extraction; operators must configure
    # a local/free binding (Ollama). We do not default to OpenAI.
    os.environ.setdefault("LLM_BINDING", "ollama")
    os.environ.setdefault("LLM_MODEL", "llama3.2")
    os.environ.setdefault("LLM_BINDING_HOST", "http://127.0.0.1:11434")

    return LightRAG(**kwargs)


def _results_from_lightrag_response(response: Any, top_k: int) -> list[RetrievalResult]:
    """Normalize LightRAG query output into :class:`RetrievalResult` rows."""
    if response is None:
        return []
    if isinstance(response, str):
        if not response.strip():
            return []
        return [
            RetrievalResult(
                document_id="lightrag",
                content=response,
                score=1.0,
                metadata={"backend": "lightrag"},
            )
        ]
    if isinstance(response, dict):
        chunks = (
            response.get("chunks")
            or response.get("data")
            or response.get("references")
            or response.get("entities")
            or []
        )
        if isinstance(chunks, list) and chunks:
            out: list[RetrievalResult] = []
            for idx, item in enumerate(chunks[:top_k]):
                if isinstance(item, dict):
                    content = str(
                        item.get("content") or item.get("text") or item.get("description") or item
                    )
                    doc_id = str(
                        item.get("document_id")
                        or item.get("doc_id")
                        or item.get("id")
                        or f"lightrag-{idx}"
                    )
                    score = float(item.get("score", item.get("similarity", 1.0 - idx * 0.01)))
                    out.append(
                        RetrievalResult(
                            document_id=doc_id,
                            content=content,
                            score=score,
                            metadata={
                                k: v for k, v in item.items() if k not in {"content", "text"}
                            },
                        )
                    )
                else:
                    out.append(
                        RetrievalResult(
                            document_id=f"lightrag-{idx}",
                            content=str(item),
                            score=1.0 - idx * 0.01,
                            metadata={"backend": "lightrag"},
                        )
                    )
            return out
        # Fallback: stringify the dict
        return [
            RetrievalResult(
                document_id="lightrag",
                content=str(response),
                score=1.0,
                metadata={"backend": "lightrag"},
            )
        ]
    return [
        RetrievalResult(
            document_id="lightrag",
            content=str(response),
            score=1.0,
            metadata={"backend": "lightrag"},
        )
    ]


class LightRAGBackend:
    """Graph-enhanced retrieval via LightRAG (optional ``[lightrag]`` extra)."""

    name = "lightrag"

    def __init__(
        self,
        *,
        client: LightRAGClient | None = None,
        dsn: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        self._dsn = resolve_pgvector_dsn(dsn)
        self._working_dir = (
            working_dir
            or os.environ.get("DIGISEARCH_LIGHTRAG_WORKING_DIR", "").strip()
            or DEFAULT_WORKING_DIR
        )
        self._client = client
        self._initialized = False

    async def _rag(self) -> LightRAGClient:
        if self._client is None:
            _apply_postgres_env(self._dsn)
            self._client = _build_default_lightrag(
                working_dir=self._working_dir,
                use_postgres=bool(self._dsn),
            )
        if not self._initialized:
            await self._client.initialize_storages()
            self._initialized = True
        return self._client

    async def index(self, documents: list[Document]) -> None:
        if not documents:
            return
        rag = await self._rag()
        texts = [doc.content for doc in documents]
        ids = [doc.id for doc in documents]
        paths = [doc.source or doc.id for doc in documents]
        await rag.ainsert(texts, ids=ids, file_paths=paths)

    async def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        rag = await self._rag()
        param: Any = None
        try:
            from lightrag import QueryParam

            param = QueryParam(mode="hybrid", top_k=top_k, chunk_top_k=top_k)
        except ImportError:
            param = None
        # Prefer data-only query when available (no LLM synthesis).
        if hasattr(rag, "aquery_data"):
            response = await rag.aquery_data(query, param=param)  # type: ignore[attr-defined]
        else:
            response = await rag.aquery(query, param=param)
        return _results_from_lightrag_response(response, top_k)

    async def delete(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        rag = await self._rag()
        if hasattr(rag, "adelete_by_doc_id"):
            await rag.adelete_by_doc_id(document_ids)
            return
        raise NotImplementedError(
            "LightRAG client has no adelete_by_doc_id; cannot honor RetrievalBackend.delete"
        )

    async def health(self) -> bool:
        try:
            await self._rag()
            return True
        except Exception:
            logger.exception("LightRAGBackend health check failed")
            return False
