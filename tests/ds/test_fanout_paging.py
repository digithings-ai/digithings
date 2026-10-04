"""Unit tests for fan-out paging over capped backends (no network)."""

from __future__ import annotations

import pytest
from digisearch.core.models import Chunk, Query, Result, SearchResponse
from digisearch.core.standard_hits import (
    BACKEND_AZURE_AI_SEARCH,
    BACKEND_CHROMA,
    BACKEND_VECTORIZE,
)

pytestmark = pytest.mark.unit


def _chunk(cid: str, content: str = "alpha") -> Chunk:
    return Chunk(id=cid, content=content, doc_id="doc")


def _result(cid: str, rank: int = 1) -> Result:
    return Result(chunk=_chunk(cid), score=0.9, rank=rank)


def _install_fake(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    from digisearch.search import _stub

    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    monkeypatch.setattr(_stub, "_backends", [fn])


def test_vectorize_skip_propagates_in_fanout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fan-out must pass the caller's skip to Vectorize (skip>0 raises)."""
    from digisearch.indexes.backends.vectorize_errors import VectorizeBackendError
    from digisearch.search import _stub

    seen: list[int] = []

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        if index_name not in ("v1", "v2"):
            return None
        seen.append(int(query.skip or 0))
        if int(query.skip or 0) > 0:
            raise VectorizeBackendError(
                "VectorizeBackend.query does not support Query.skip; "
                "the Vectorize query API has no offset"
            )
        return SearchResponse(results=[_result(f"{index_name}-a")], backend=BACKEND_VECTORIZE)

    _install_fake(monkeypatch, _fake)
    with pytest.raises(VectorizeBackendError):
        _stub.query_index(Query(text="alpha", top_k=2, skip=2), index_name="v1,v2")
    assert 2 in seen


def test_clamped_vectorize_leg_has_no_fused_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 50-hit Vectorize page with top_k>50 is clamped, not exhaustive."""
    from digisearch.search import _stub

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        if index_name not in ("v1", "v2"):
            return None
        results = [_result(f"{index_name}-{i}", rank=i + 1) for i in range(50)]
        return SearchResponse(results=results, backend=BACKEND_VECTORIZE)

    _install_fake(monkeypatch, _fake)
    resp = _stub.query_index(
        Query(text="alpha", top_k=100, include_total_count=True), index_name="v1,v2"
    )
    assert resp.total_count is None
    assert len(resp.results) == 100


def test_chroma_later_page_is_not_first_page_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later Chroma fan-out page applies the backend offset (no zeroed skip)."""
    from digisearch.search import _stub

    corpus: dict[str, list[str]] = {
        "c1": [f"c1-{i}" for i in range(4)],
        "c2": [f"c2-{i}" for i in range(4)],
    }
    seen: list[tuple[int, int]] = []

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        if index_name not in corpus:
            return None
        seen.append((int(query.skip or 0), int(query.top_k or 0)))
        ids = corpus[index_name]
        start = max(int(query.skip or 0), 0)
        page = ids[start : start + max(int(query.top_k or 0), 0)]
        return SearchResponse(
            results=[_result(cid, rank=i + 1) for i, cid in enumerate(page)],
            backend=BACKEND_CHROMA,
        )

    _install_fake(monkeypatch, _fake)
    first = _stub.query_index(Query(text="alpha", top_k=2, skip=0), index_name="c1,c2")
    second = _stub.query_index(
        Query(text="alpha", top_k=2, skip=2, include_total_count=True),
        index_name="c1,c2",
    )
    assert [r.chunk.id for r in first.results] == ["c1-0", "c2-0"]
    # A zeroed-skip implementation would fuse the first pages and slice them,
    # returning c1-1/c2-1 here. The backend offset must win instead.
    assert [r.chunk.id for r in second.results] == ["c1-2", "c2-2"]
    # The later page is not the whole match set, so the fused total stays unset.
    assert second.total_count is None
    assert any(skip == 2 for skip, _ in seen)


def test_capped_chroma_leg_has_no_fused_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """skip+top_k past the 100 cap is a prefix even when the page is short."""
    from digisearch.search import _stub

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        if index_name not in ("c1", "c2"):
            return None
        # Over-fetch capped at 100 leaves 5 hits for a 95+10 window.
        results = [_result(f"{index_name}-{i}", rank=i + 1) for i in range(5)]
        return SearchResponse(results=results, backend=BACKEND_CHROMA)

    _install_fake(monkeypatch, _fake)
    resp = _stub.query_index(
        Query(text="alpha", top_k=10, skip=95, include_total_count=True),
        index_name="c1,c2",
    )
    assert resp.total_count is None


def test_incomplete_azure_fanout_has_no_fused_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """An Azure leg with total_count beyond the page is not complete."""
    from digisearch.search import _stub

    calls: list[tuple[int, int]] = []

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        if index_name not in ("a1", "a2"):
            return None
        calls.append((int(query.skip or 0), int(query.top_k or 0)))
        results = [_result(f"{index_name}-{i}", rank=i + 1) for i in range(2)]
        return SearchResponse(results=results, backend=BACKEND_AZURE_AI_SEARCH, total_count=200)

    _install_fake(monkeypatch, _fake)
    resp = _stub.query_index(
        Query(text="alpha", top_k=2, skip=2, include_total_count=True),
        index_name="a1,a2",
    )
    assert resp.total_count is None
    assert all(skip == 2 and top == 2 for skip, top in calls)


def test_incomplete_azure_http_total_is_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /query with include_total_count must not report the page length."""
    from digisearch.server import QueryRequest, run_query

    def _fake(query: Query, index_name: str) -> SearchResponse | None:
        results = [_result(f"hit-{i}", rank=i + 1) for i in range(2)]
        return SearchResponse(results=results, backend=BACKEND_AZURE_AI_SEARCH, total_count=200)

    _install_fake(monkeypatch, _fake)
    out = run_query(
        QueryRequest(
            text="alpha",
            index_name="a1,a2",
            top_k=2,
            skip=0,
            include_total_count=True,
        )
    )
    assert out.total is None
