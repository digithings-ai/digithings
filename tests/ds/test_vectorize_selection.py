"""Backend selection: Vectorize wins over Chroma when configured."""

from __future__ import annotations

import builtins

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
def test_vectorize_import_failure_wrapped_not_chroma_fallthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FINDING 1 (round 2) repro: an `ImportError` raised while importing
    `VectorizeBackend` itself -- not a query/HTTP failure -- is a second path into
    the same silent-fallthrough bug. `_BACKEND_ERRORS` includes `ImportError`, so if
    that import is not wrapped as `VectorizeBackendError`, `query_index` swallows it
    and falls through to Chroma, answering from a different corpus with no error.

    Simulated via `builtins.__import__` (matches the reviewer's own repro) rather
    than uninstalling a real dependency -- this repo's `vectorize.py` has no risky
    module-level imports today, so this is defence against *any* future import
    failure in that module, not a specific package going missing right now.
    """
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/should-never-be-touched")

    chroma_constructed = False

    class _ShouldNotConstruct:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal chroma_constructed
            chroma_constructed = True

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.chroma.ChromaBackend", _ShouldNotConstruct, raising=True
    )

    # Import before blocking `__import__` -- this is the real class `_stub.py` raises,
    # not a look-alike, and the assertion below must see the same object.
    from digisearch.indexes.backends.vectorize import VectorizeBackendError

    real_import = builtins.__import__

    def _blocking_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "digisearch.indexes.backends.vectorize":
            raise ImportError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    query = Query(text="hi", top_k=3, embedding=[0.0] * 384)
    with pytest.raises(VectorizeBackendError, match="simulated missing dependency"):
        _stub.query_index(query, "occ-help")

    assert chroma_constructed is False, (
        "ChromaBackend must not be constructed when the Vectorize import fails"
    )


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

    # Force a cold cache regardless of what earlier tests left behind.
    monkeypatch.setattr(minilm_module, "_default_minilm_singleton", None, raising=False)

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
    monkeypatch.setattr(minilm_module, "_default_minilm_singleton", None, raising=False)

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


# ── canonical CLOUDFLARE_*/legacy VECTORIZE_*/D1_* credential fallback (#2239
# credential rename) ─────────────────────────────────────────────────────────
@pytest.mark.unit
def test_vectorize_selected_with_canonical_cloudflare_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The canonical (wrangler-conventional) names alone must activate Vectorize --
    no legacy VECTORIZE_*/D1_* name needs to be set at all."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    captured: dict[str, object] = {}

    class _Stub:
        def __init__(self, name: str, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _Stub, raising=True
    )
    response = _stub._vectorize_backend(Query(text="hi", top_k=3), "occ-help")
    assert response is not None
    assert captured["kwargs"] == {"account_id": "acct", "api_token": "tok"}


@pytest.mark.unit
def test_vectorize_selected_with_legacy_d1_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-downtime property: the D1_* names (same account + token as Vectorize,
    per #2239) must keep activating Vectorize with no CLOUDFLARE_*/VECTORIZE_* name
    set at all -- this is what makes sharing one credential pair meaningful."""
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    class _Stub:
        def __init__(self, name: str, **kwargs: object) -> None:
            pass

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _Stub, raising=True
    )
    response = _stub._vectorize_backend(Query(text="hi", top_k=3), "occ-help")
    assert response is not None


@pytest.mark.unit
def test_vectorize_backend_canonical_wins_over_legacy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple names in the fallback chain are set to *different* values, the
    canonical CLOUDFLARE_* pair must win over both legacy VECTORIZE_* and D1_*."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "canonical-acct")
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "legacy-vectorize-acct")
    monkeypatch.setenv("D1_ACCOUNT_ID", "legacy-d1-acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "canonical-tok")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "legacy-vectorize-tok")
    monkeypatch.setenv("D1_API_TOKEN", "legacy-d1-tok")

    captured: dict[str, object] = {}

    class _Stub:
        def __init__(self, name: str, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _Stub, raising=True
    )
    _stub._vectorize_backend(Query(text="hi", top_k=3), "occ-help")
    assert captured["kwargs"] == {"account_id": "canonical-acct", "api_token": "canonical-tok"}


@pytest.mark.unit
def test_vectorize_registered_before_chroma() -> None:
    names = [fn.__name__ for fn in _stub._backends]
    assert "_vectorize_backend" in names
    assert names.index("_vectorize_backend") < names.index("_chroma_backend")


@pytest.mark.unit
def test_query_response_documents_vectorize_backend() -> None:
    from digisearch.server import QueryResponse

    field = QueryResponse.model_fields["backend"]
    assert "vectorize" in str(field.description)


@pytest.mark.unit
def test_real_backend_check_accepts_vectorize(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.server import _require_real_search_backend

    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    _require_real_search_backend()


@pytest.mark.unit
def test_real_backend_check_accepts_canonical_cloudflare_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This startup gate must use the same canonical-first, legacy-fallback
    precedence as `_vectorize_backend` (#2239 credential rename) -- else it could
    disagree with the backend it exists to gate."""
    from digisearch.server import _require_real_search_backend

    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    _require_real_search_backend()
