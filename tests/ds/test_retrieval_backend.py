"""Unit tests for digisearch RetrievalBackend protocol + registry (#402)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from digisearch.core.models import Document
from digisearch.retrieval import (
    BACKENDS,
    DEFAULT_BACKEND_NAME,
    LightRAGBackend,
    PgvectorBackend,
    RetrievalBackend,
    RetrievalResult,
    clear_retrieval_backend_cache,
    get_retrieval_backend,
    resolve_retrieval_backend_name,
)
from digisearch.retrieval.pgvector import InMemoryVectorStore, PsycopgVectorStore


class _FakeEmbedder:
    """Deterministic bag-of-chars embedder — no chromadb / network."""

    dimensions = 8

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for i, ch in enumerate(text.lower()):
                vec[i % self.dimensions] += (ord(ch) % 31) / 31.0
            out.append(vec)
        return out


class _FakeLightRAG:
    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.initialized = False

    async def initialize_storages(self) -> None:
        self.initialized = True

    async def ainsert(
        self,
        input: str | list[str],
        ids: str | list[str] | None = None,
        file_paths: str | list[str] | None = None,
    ) -> str:
        del file_paths
        texts = [input] if isinstance(input, str) else list(input)
        if ids is None:
            id_list = [f"auto-{i}" for i in range(len(texts))]
        elif isinstance(ids, str):
            id_list = [ids]
        else:
            id_list = list(ids)
        for doc_id, text in zip(id_list, texts, strict=True):
            self.docs[doc_id] = text
        return "track"

    async def aquery(self, query: str, param: Any | None = None) -> dict[str, Any]:
        del param
        q = query.lower()
        hits = []
        for doc_id, text in self.docs.items():
            if any(tok in text.lower() for tok in q.split() if tok):
                hits.append({"document_id": doc_id, "content": text, "score": 0.9})
        return {"chunks": hits}

    async def adelete_by_doc_id(self, doc_ids: list[str]) -> None:
        for doc_id in doc_ids:
            self.docs.pop(doc_id, None)


@pytest.fixture(autouse=True)
def _clear_retrieval_cache() -> None:
    clear_retrieval_backend_cache()
    yield
    clear_retrieval_backend_cache()


def _doc(doc_id: str, content: str) -> Document:
    return Document(id=doc_id, content=content, source=f"/{doc_id}.txt", doc_type="txt")


@pytest.mark.unit
def test_retrieval_backend_default_is_pgvector() -> None:
    assert DEFAULT_BACKEND_NAME == "pgvector"
    assert resolve_retrieval_backend_name() == "pgvector"
    assert "pgvector" in BACKENDS
    assert "lightrag" in BACKENDS


@pytest.mark.unit
def test_resolve_retrieval_backend_name_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_RETRIEVAL_BACKEND", "lightrag")
    assert resolve_retrieval_backend_name() == "lightrag"
    assert resolve_retrieval_backend_name("pgvector") == "pgvector"
    monkeypatch.setenv("DIGISEARCH_RETRIEVAL_BACKEND", "postgres")
    assert resolve_retrieval_backend_name() == "pgvector"


@pytest.mark.unit
def test_get_retrieval_backend_switches_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_RETRIEVAL_BACKEND", raising=False)
    backend = get_retrieval_backend(
        use_cache=False,
        embedder=_FakeEmbedder(),
        store=InMemoryVectorStore(),
    )
    assert isinstance(backend, PgvectorBackend)
    assert isinstance(backend, RetrievalBackend)

    monkeypatch.setenv("DIGISEARCH_RETRIEVAL_BACKEND", "lightrag")
    lr = get_retrieval_backend(use_cache=False, client=_FakeLightRAG())
    assert isinstance(lr, LightRAGBackend)
    assert isinstance(lr, RetrievalBackend)


@pytest.mark.unit
def test_get_retrieval_backend_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown DIGISEARCH_RETRIEVAL_BACKEND"):
        get_retrieval_backend("nope")


@pytest.mark.unit
def test_pgvector_backend_index_retrieve_delete() -> None:
    async def _run() -> None:
        backend = PgvectorBackend(store=InMemoryVectorStore(), embedder=_FakeEmbedder())
        assert await backend.health() is True

        await backend.index(
            [
                _doc("a", "revenue growth accelerated in Q4"),
                _doc("b", "unrelated weather report"),
                _doc("c", "quarterly revenue and growth metrics"),
            ]
        )
        hits = await backend.retrieve("revenue growth", top_k=2)
        assert len(hits) == 2
        assert all(isinstance(h, RetrievalResult) for h in hits)
        assert hits[0].score >= hits[1].score
        assert {h.document_id for h in hits} <= {"a", "b", "c"}
        assert hits[0].document_id in {"a", "c"}

        await backend.delete(["a", "c"])
        after = await backend.retrieve("revenue growth", top_k=5)
        assert all(h.document_id != "a" for h in after)
        assert all(h.document_id != "c" for h in after)

    asyncio.run(_run())


@pytest.mark.unit
def test_lightrag_backend_index_retrieve_delete() -> None:
    async def _run() -> None:
        fake = _FakeLightRAG()
        backend = LightRAGBackend(client=fake)
        assert await backend.health() is True
        assert fake.initialized is True

        await backend.index(
            [
                _doc("d1", "graph enhanced retrieval with entities"),
                _doc("d2", "purely unrelated gardening tips"),
            ]
        )
        hits = await backend.retrieve("graph retrieval", top_k=5)
        assert len(hits) >= 1
        assert hits[0].document_id == "d1"
        assert isinstance(hits[0], RetrievalResult)

        await backend.delete(["d1"])
        after = await backend.retrieve("graph retrieval", top_k=5)
        assert all(h.document_id != "d1" for h in after)

    asyncio.run(_run())


@pytest.mark.unit
def test_pgvector_fails_closed_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_DATABASE_URL", raising=False)
    monkeypatch.delenv("DIGISEARCH_PGVECTOR_URL", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_MEMORY_RETRIEVAL", raising=False)
    with pytest.raises(ValueError, match="DIGISEARCH_DATABASE_URL"):
        PgvectorBackend(embedder=_FakeEmbedder())


@pytest.mark.unit
def test_pgvector_rejects_unsafe_table_name() -> None:
    with pytest.raises(ValueError, match="Invalid pgvector table name"):
        PsycopgVectorStore("postgresql://localhost/db", table="evil;drop")


@pytest.mark.unit
def test_lightrag_delete_raises_without_adelete() -> None:
    class _NoDelete:
        async def initialize_storages(self) -> None:
            return None

        async def ainsert(self, *args: Any, **kwargs: Any) -> str:
            del args, kwargs
            return "t"

        async def aquery(self, *args: Any, **kwargs: Any) -> str:
            del args, kwargs
            return ""

    async def _run() -> None:
        backend = LightRAGBackend(client=_NoDelete())  # type: ignore[arg-type]
        with pytest.raises(NotImplementedError, match="adelete_by_doc_id"):
            await backend.delete(["x"])

    asyncio.run(_run())


@pytest.mark.unit
def test_retrieval_backend_protocol_runtime_checkable() -> None:
    pg = PgvectorBackend(store=InMemoryVectorStore(), embedder=_FakeEmbedder())
    lr = LightRAGBackend(client=_FakeLightRAG())
    assert isinstance(pg, RetrievalBackend)
    assert isinstance(lr, RetrievalBackend)
