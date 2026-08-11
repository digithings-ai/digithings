"""Backend selection: Vectorize wins over Chroma when configured."""

from __future__ import annotations

import pytest
from digisearch.core.models import Query
from digisearch.core.standard_hits import BACKEND_VECTORIZE
from digisearch.search import _stub


@pytest.mark.unit
def test_vectorize_failure_propagates_through_query_index_not_chroma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FINDING 1 repro: a configured Vectorize backend that fails must raise out of
    `query_index`, not be swallowed and fall through to Chroma.

    Verified through the real dispatcher (`_stub.query_index`), not `_vectorize_backend`
    in isolation -- that isolation is exactly how this defect got through review.
    """
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/should-never-be-touched")

    chroma_constructed = False

    class _FailingVectorize:
        def __init__(self, name: str, **kwargs: object) -> None:
            pass

        def query(self, _q: Query) -> list[object]:
            raise RuntimeError("vectorize query failed (500): boom")

    class _ShouldNotConstruct:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal chroma_constructed
            chroma_constructed = True

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _FailingVectorize, raising=True
    )
    monkeypatch.setattr(
        "digisearch.indexes.backends.chroma.ChromaBackend", _ShouldNotConstruct, raising=True
    )

    from digisearch.indexes.backends.vectorize import VectorizeBackendError

    query = Query(text="hi", top_k=3, embedding=[0.0] * 384)
    with pytest.raises(VectorizeBackendError, match="boom"):
        _stub.query_index(query, "occ-help")

    assert chroma_constructed is False, "ChromaBackend must not be constructed on Vectorize failure"


@pytest.mark.unit
def test_vectorize_backend_error_is_not_a_backend_error_member() -> None:
    """The whole fix hinges on this: if VectorizeBackendError were ever added to
    `_BACKEND_ERRORS`, `query_index` would swallow it again."""
    from digisearch.indexes.backends.vectorize import VectorizeBackendError

    assert not issubclass(VectorizeBackendError, _stub._BACKEND_ERRORS)


@pytest.mark.unit
def test_default_embedder_constructed_once_across_n_queries_via_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FINDING 2 repro: `_vectorize_backend` builds a fresh `VectorizeBackend` on every
    call (matching every production call site -- none inject `embedding_provider` or
    populate `Query.embedding`). N queries through the real dispatcher must still
    construct the default embedder exactly once, not once per query/instance.
    """
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)

    import digisearch.embedding.providers.minilm as minilm_module
    import digisearch.indexes.backends.vectorize as vectorize_module

    # Force a cold cache regardless of what earlier tests left behind.
    monkeypatch.setattr(vectorize_module, "_default_embedder_singleton", None, raising=False)

    construction_count = 0

    class _StubEmbedder:
        def __init__(self) -> None:
            nonlocal construction_count
            construction_count += 1

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.3] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    monkeypatch.setattr(minilm_module, "MiniLMEmbedder", _StubEmbedder, raising=True)

    class _RecordingPost:
        def __call__(
            self, url: str, headers: dict[str, str], body: bytes, content_type: str
        ) -> tuple[int, str]:
            return 200, '{"success": true, "result": {"matches": []}}'

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize._default_http_post", _RecordingPost()
    )

    for _ in range(3):
        response = _stub.query_index(Query(text="no embedding here", top_k=3), "occ-help")
        assert response.backend == BACKEND_VECTORIZE

    assert construction_count == 1, f"expected 1 construction, got {construction_count}"


@pytest.mark.unit
def test_vectorize_selected_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/should-be-ignored")

    captured: dict[str, object] = {}

    class _Stub:
        def __init__(self, name: str, **kwargs: object) -> None:
            captured["name"] = name
            captured["kwargs"] = kwargs

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _Stub, raising=True
    )
    query = Query(text="hi", top_k=3, embedding=[0.0] * 384)
    response = _stub._vectorize_backend(query, "occ-help")
    assert response is not None
    assert response.backend == BACKEND_VECTORIZE
    assert captured["name"] == "occ-help"


@pytest.mark.unit
def test_vectorize_inactive_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VECTORIZE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("VECTORIZE_API_TOKEN", raising=False)
    assert _stub._vectorize_backend(Query(text="hi", top_k=3), "i") is None


@pytest.mark.unit
def test_vectorize_registered_before_chroma() -> None:
    names = [fn.__name__ for fn in _stub._backends]
    assert "_vectorize_backend" in names
    assert names.index("_vectorize_backend") < names.index("_chroma_backend")
