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
        [("a", [_result("both", 1), _result("a-only", 2)]), ("b", [_result("both", 1)])],
        top_k=10,
    )
    assert [r.chunk.id for r in merged] == ["both", "a-only"]
    assert [r.rank for r in merged] == [1, 2]


def test_rrf_merge_handles_unset_ranks() -> None:
    from digisearch.core.models import Result
    from digisearch.search._stub import _rrf_merge_results

    def _result(id: str) -> Result:
        return Result(chunk=_chunk(id, "alpha"), score=0.5, rank=None)

    merged = _rrf_merge_results([("a", [_result("x")]), ("b", [_result("y")])], top_k=10)
    assert [r.chunk.id for r in merged] == ["x", "y"]
    assert all(r.rank is not None for r in merged)


# ── per-index provenance (#5045) ──────────────────────────────────────────────


def test_single_index_query_stamps_index_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["only"] = [_chunk("1", "alpha once"), _chunk("2", "alpha twice")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="only")
    assert resp.index_names == ["only"]
    assert [r.index_names for r in resp.results] == [["only"], ["only"]]


def test_fan_out_results_carry_source_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["docs"] = [_chunk("d1", "alpha password reset")]
    _stub_index["tickets"] = [_chunk("t1", "alpha login failure")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="docs,tickets")
    assert resp.index_names == ["docs", "tickets"]
    by_id = {r.chunk.id: r.index_names for r in resp.results}
    assert by_id == {"d1": ["docs"], "t1": ["tickets"]}


def test_shared_chunk_records_all_contributing_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["a"] = [_chunk("same", "alpha shared")]
    _stub_index["b"] = [_chunk("same", "alpha shared")]
    resp = query_index(Query(text="alpha", top_k=10), index_name="a,b")
    assert [r.chunk.id for r in resp.results] == ["same"]
    # The RRF duplicate-fold must keep BOTH contributing indexes, fan-out order.
    assert resp.results[0].index_names == ["a", "b"]


def test_rrf_merge_preserves_all_contributing_index_names() -> None:
    from digisearch.core.models import Result
    from digisearch.search._stub import _rrf_merge_results

    def _result(id: str, rank: int) -> Result:
        return Result(chunk=_chunk(id, "alpha"), score=0.5, rank=rank)

    merged = _rrf_merge_results(
        [
            ("idx1", [_result("shared", 1), _result("only1", 2)]),
            ("idx2", [_result("shared", 1)]),
            ("idx3", [_result("shared", 1), _result("only3", 2)]),
        ],
        top_k=10,
    )
    by_id = {r.chunk.id: r.index_names for r in merged}
    assert by_id["shared"] == ["idx1", "idx2", "idx3"]
    assert by_id["only1"] == ["idx1"]
    assert by_id["only3"] == ["idx3"]


def test_fan_out_golden_order_and_scores_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression pin (#5045): provenance must not change retrieval behaviour.

    Golden values are the pre-change RRF maths for this fixture (k=60, stub
    ranks are 1-based scan order, merged score = sum of 1/(k+rank) over the
    contributing indexes, stable sort on insertion order for ties):

    * ``s``  — rank 3 in ``a``, rank 2 in ``b`` -> 1/63 + 1/62 (only folded hit)
    * ``a1`` — rank 1 in ``a``                  -> 1/61
    * ``b1`` — rank 1 in ``b``                  -> 1/61 (tie, inserted after a1)
    * ``a2`` — rank 2 in ``a``                  -> 1/62
    """
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    from digisearch.search._stub import _stub_index, query_index

    _stub_index.clear()
    _stub_index["a"] = [
        _chunk("a1", "alpha one"),
        _chunk("a2", "alpha two"),
        _chunk("s", "alpha shared"),
    ]
    _stub_index["b"] = [
        _chunk("b1", "alpha three"),
        _chunk("s", "alpha shared"),
    ]
    resp = query_index(Query(text="alpha", top_k=10), index_name="a,b")
    assert resp.backend == "multi"
    assert [r.chunk.id for r in resp.results] == ["s", "a1", "b1", "a2"]
    assert [r.rank for r in resp.results] == [1, 2, 3, 4]
    assert [r.score for r in resp.results] == [
        1.0 / (60 + 3) + 1.0 / (60 + 2),
        1.0 / (60 + 1),
        1.0 / (60 + 1),
        1.0 / (60 + 2),
    ]


def test_rerank_path_preserves_index_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reranker providers rebuild Results (dropping new fields); _maybe_rerank
    must restore provenance so it survives DIGISEARCH_RERANK_ENABLED=1 (#5045)."""
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.setenv("DIGISEARCH_RERANK_ENABLED", "1")
    import digisearch.search._stub as stub
    from digisearch.core.models import Result

    class _RebuildingReranker:
        """Mimics _rerank_cohere/_rerank_bge: fresh Result(chunk, score, rank)."""

        def rerank(self, text: str, results: list[Result], top_n: int | None = None):
            kept = results if top_n is None else results[:top_n]
            return [Result(chunk=r.chunk, score=r.score, rank=i + 1) for i, r in enumerate(kept)]

    monkeypatch.setattr(stub, "_get_reranker", lambda provider: _RebuildingReranker())
    stub._stub_index.clear()
    stub._stub_index["a"] = [_chunk("a1", "alpha one")]
    stub._stub_index["b"] = [_chunk("b1", "alpha two")]
    resp = stub.query_index(Query(text="alpha", top_k=10), index_name="a,b")
    assert resp.index_names == ["a", "b"]
    by_id = {r.chunk.id: r.index_names for r in resp.results}
    assert by_id == {"a1": ["a"], "b1": ["b"]}
