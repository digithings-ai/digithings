"""Backend selection: Vectorize wins over Chroma when configured."""

from __future__ import annotations

import pytest
from digisearch.core.models import Query
from digisearch.core.standard_hits import BACKEND_VECTORIZE
from digisearch.search import _stub


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
