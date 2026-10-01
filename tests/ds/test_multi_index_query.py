"""Unit tests for comma-separated multi-index fan-out in query_index (#4756)."""

from __future__ import annotations

import pytest
from digisearch.core.models import Chunk, Query

pytestmark = pytest.mark.unit


def _chunk(id: str, content: str) -> Chunk:
    return Chunk(id=id, content=content, doc_id="doc")


def test_fan_out_merges_both_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["docs"] = [_chunk("d1", "alpha password reset")]
    _stub_index["tickets"] = [_chunk("t1", "alpha login failure")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="docs,tickets")
    assert resp.backend == "multi"
    assert sorted(r.chunk.id for r in resp.results) == ["d1", "t1"]
    assert [r.rank for r in resp.results] == [1, 2]


def test_fan_out_dedupes_shared_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["a"] = [_chunk("same", "alpha shared")]
    _stub_index["b"] = [_chunk("same", "alpha shared")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="a,b")
    assert [r.chunk.id for r in resp.results] == ["same"]


def test_fan_out_ignores_empty_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["a"] = [_chunk("1", "alpha once")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="a,, ,")
    assert [r.chunk.id for r in resp.results] == ["1"]


def test_single_index_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["only"] = [_chunk("1", "alpha once")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="only")
    assert resp.backend == "stub"
    assert [r.chunk.id for r in resp.results] == ["1"]


def test_fan_out_respects_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["a"] = [_chunk("a1", "alpha one"), _chunk("a2", "alpha two")]
    _stub_index["b"] = [_chunk("b1", "alpha three")]
    resp = query_index(Query(text="alpha", top_k=2), index_name="a,b")
    assert len(resp.results) == 2


def test_rrf_merge_prefers_multi_index_hits() -> None:
    from digisearch.core.models import Result
    from digisearch.search._stub import _rrf_merge_results

    def _result(id: str, rank: int | None) -> Result:
        return Result(chunk=_chunk(id, "alpha"), score=0.5, rank=rank)

    merged = _rrf_merge_results(
        [[_result("both", 1), _result("a-only", 2)], [_result("both", 1)]],
        top_k=10,
    )
    assert [r.chunk.id for r in merged] == ["both", "a-only"]
    assert [r.rank for r in merged] == [1, 2]


def test_rrf_merge_handles_unset_ranks() -> None:
    from digisearch.core.models import Result
    from digisearch.search._stub import _rrf_merge_results

    def _result(id: str) -> Result:
        return Result(chunk=_chunk(id, "alpha"), score=0.5, rank=None)

    merged = _rrf_merge_results([[_result("x")], [_result("y")]], top_k=10)
    assert [r.chunk.id for r in merged] == ["x", "y"]
    assert all(r.rank is not None for r in merged)
