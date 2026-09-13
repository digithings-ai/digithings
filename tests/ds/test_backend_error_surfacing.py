"""Configured backend failures must surface, not collapse into an empty result (#3909).

Covers defect 1: Chroma and Azure swallowed backend exceptions and returned an empty
``[]``/``SearchResponse`` (HTTP 200, indistinguishable from an empty corpus), and the
``_stub`` router wrappers silently fell through to the next backend. The new
``SearchBackendError`` follows the ``VectorizeBackendError`` pattern: it is deliberately
outside ``_BACKEND_ERRORS`` so it propagates out of ``query_index``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from digisearch.core.models import Query
from digisearch.search import _stub as stub_mod


class _StubProvider:
    """Minimal embedding provider so Chroma never loads MiniLM in these tests."""

    def __init__(self, dims: int = 8) -> None:
        self.model_id = "stub-model"
        self.version = "1"
        self._dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self._dims for _ in texts]

    @property
    def dimensions(self) -> int:
        return self._dims


@pytest.mark.unit
def test_backend_error_type_is_not_a_backend_error_member() -> None:
    """The fix hinges on this: a member of ``_BACKEND_ERRORS`` would be swallowed."""
    from digisearch.indexes.backends.backend_errors import SearchBackendError

    assert not issubclass(SearchBackendError, stub_mod._BACKEND_ERRORS)


@pytest.mark.unit
def test_chroma_query_raises_instead_of_returning_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.indexes.backends import chroma as chroma_mod
    from digisearch.indexes.backends.backend_errors import SearchBackendError

    monkeypatch.setattr(chroma_mod, "_CHROMA_AVAILABLE", True)
    collection = MagicMock()
    collection.query.side_effect = RuntimeError("hnsw exploded")
    with patch.object(chroma_mod, "chromadb") as chromadb_mod:
        chromadb_mod.Client.return_value.get_or_create_collection.return_value = collection
        backend = chroma_mod.ChromaBackend("boom-index", embedding_provider=_StubProvider())

    with pytest.raises(SearchBackendError, match="hnsw exploded"):
        backend.query(Query(text="anything", top_k=3, embedding=[0.1] * 8))


@pytest.mark.unit
def test_chroma_healthy_empty_result_still_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A healthy backend with no matches must keep returning an empty list."""
    from digisearch.indexes.backends import chroma as chroma_mod

    monkeypatch.setattr(chroma_mod, "_CHROMA_AVAILABLE", True)
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    with patch.object(chroma_mod, "chromadb") as chromadb_mod:
        chromadb_mod.Client.return_value.get_or_create_collection.return_value = collection
        backend = chroma_mod.ChromaBackend("ok-index", embedding_provider=_StubProvider())

    assert backend.query(Query(text="x", top_k=3, embedding=[0.1] * 8)) == []


@pytest.mark.unit
def test_query_index_propagates_chroma_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the real dispatcher: a failing configured Chroma must raise, not fall through."""
    from digisearch.indexes.backends import chroma as chroma_mod
    from digisearch.indexes.backends.backend_errors import SearchBackendError

    monkeypatch.setenv("CHROMA_PATH", "/tmp/chroma-does-not-matter")
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.setattr(stub_mod, "_resolved_embedding_provider", lambda: _StubProvider())

    class _BoomChroma:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def query(self, _q: Query) -> list[object]:
            raise SearchBackendError("chroma query failed: boom")

    monkeypatch.setattr(chroma_mod, "ChromaBackend", _BoomChroma, raising=True)

    with pytest.raises(SearchBackendError, match="boom"):
        stub_mod.query_index(Query(text="x", top_k=3, embedding=[0.1] * 8), "idx")


@pytest.mark.unit
def test_azure_query_raises_instead_of_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.indexes.backends import azure_search as azure_mod
    from digisearch.indexes.backends.backend_errors import SearchBackendError

    class _BoomClient:
        def search(self, **kwargs: object) -> object:
            raise RuntimeError("azure 503")

    monkeypatch.setattr(azure_mod, "_get_client", lambda: _BoomClient())

    with pytest.raises(SearchBackendError, match="503"):
        azure_mod.query_azure(Query(text="x", top_k=3))


@pytest.mark.unit
def test_azure_healthy_empty_result_still_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.indexes.backends import azure_search as azure_mod

    class _EmptyClient:
        def search(self, **kwargs: object) -> list[object]:
            return []

    monkeypatch.setattr(azure_mod, "_get_client", lambda: _EmptyClient())

    resp = azure_mod.query_azure(Query(text="x", top_k=3))
    assert resp.results == []


@pytest.mark.unit
def test_azure_failure_does_not_fall_through_to_chroma(monkeypatch: pytest.MonkeyPatch) -> None:
    """Azure is tried first; a configured Azure that fails must not be answered by Chroma."""
    from digisearch.indexes.backends import azure_search as azure_mod
    from digisearch.indexes.backends import chroma as chroma_mod
    from digisearch.indexes.backends.backend_errors import SearchBackendError

    monkeypatch.setenv("CHROMA_PATH", "/tmp/chroma")
    monkeypatch.setattr(stub_mod, "_resolved_embedding_provider", lambda: _StubProvider())
    monkeypatch.setattr(azure_mod, "is_azure_configured", lambda: True)

    def _boom(_q: Query, _index_name: str | None = None) -> object:
        raise SearchBackendError("azure query failed: 503")

    monkeypatch.setattr(azure_mod, "query_azure", _boom, raising=True)

    chroma_constructed = False

    class _ShouldNotConstruct:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal chroma_constructed
            chroma_constructed = True

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(chroma_mod, "ChromaBackend", _ShouldNotConstruct, raising=True)

    with pytest.raises(SearchBackendError, match="503"):
        stub_mod.query_index(Query(text="x", top_k=3), "idx")

    assert chroma_constructed is False, "Chroma must not be constructed on Azure failure"
