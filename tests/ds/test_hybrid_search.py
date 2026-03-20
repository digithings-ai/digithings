"""Unit tests for digisearch hybrid search — RRF merge and HybridSearcher."""

from __future__ import annotations

import pytest

from digisearch.core.models import Chunk, Query, Result
from digisearch.search.hybrid import HybridSearcher, _rrf_score
from digisearch.search.multi_index import _rrf_merge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(cid: str) -> Chunk:
    return Chunk(id=cid, content=f"content-{cid}", doc_id=f"doc-{cid}")


def _result(cid: str, rank: int, score: float = 1.0) -> Result:
    return Result(chunk=_chunk(cid), score=score, rank=rank)


class _FakeSearcher:
    """Minimal searcher for testing HybridSearcher."""

    def __init__(self, results: list[Result]) -> None:
        self._results = results

    def search(self, query, top_k=None) -> list[Result]:
        k = top_k or query.top_k
        return self._results[:k]


# ---------------------------------------------------------------------------
# _rrf_score
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRrfScore:
    def test_rank_1_default_k(self) -> None:
        assert _rrf_score(1) == pytest.approx(1.0 / 61)

    def test_higher_rank_lower_score(self) -> None:
        assert _rrf_score(1) > _rrf_score(10) > _rrf_score(100)

    def test_custom_k(self) -> None:
        assert _rrf_score(1, k=10) == pytest.approx(1.0 / 11)

    def test_always_positive(self) -> None:
        for rank in (1, 5, 50, 1000):
            assert _rrf_score(rank) > 0


# ---------------------------------------------------------------------------
# _rrf_merge (MultiIndex helper)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRrfMerge:
    def test_single_list_preserves_order(self) -> None:
        results = [_result("a", 1), _result("b", 2), _result("c", 3)]
        merged = _rrf_merge([results])
        ids = [r.chunk.id for r in merged]
        assert ids == ["a", "b", "c"]

    def test_two_lists_boosts_shared_doc(self) -> None:
        """Doc 'b' appearing in both lists should rank above docs in only one."""
        list1 = [_result("a", 1), _result("b", 2)]
        list2 = [_result("b", 1), _result("c", 2)]
        merged = _rrf_merge([list1, list2])
        # 'b' appears in both → highest RRF score
        assert merged[0].chunk.id == "b"

    def test_empty_lists_return_empty(self) -> None:
        assert _rrf_merge([]) == []
        assert _rrf_merge([[], []]) == []

    def test_one_empty_list_returns_other(self) -> None:
        results = [_result("x", 1), _result("y", 2)]
        merged = _rrf_merge([results, []])
        assert {r.chunk.id for r in merged} == {"x", "y"}

    def test_scores_are_positive(self) -> None:
        lists = [[_result("a", 1)], [_result("b", 1)]]
        merged = _rrf_merge(lists)
        assert all(r.score > 0 for r in merged)

    def test_ranks_are_sequential(self) -> None:
        lists = [[_result("a", 1), _result("b", 2)], [_result("c", 1)]]
        merged = _rrf_merge(lists)
        for i, r in enumerate(merged, start=1):
            assert r.rank == i

    def test_no_duplicates_in_output(self) -> None:
        """Same doc in two lists should appear exactly once."""
        lists = [[_result("dup", 1)], [_result("dup", 1)]]
        merged = _rrf_merge(lists)
        ids = [r.chunk.id for r in merged]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# HybridSearcher
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestHybridSearcher:
    def _query(self, top_k: int = 5) -> Query:
        return Query(text="test query", top_k=top_k, mode="hybrid")

    def test_returns_results(self) -> None:
        kw = _FakeSearcher([_result("a", 1), _result("b", 2)])
        vec = _FakeSearcher([_result("c", 1), _result("a", 2)])
        hs = HybridSearcher(kw, vec, alpha=0.5)
        out = hs.search(self._query())
        assert len(out) > 0

    def test_shared_doc_ranked_first(self) -> None:
        """Doc 'a' in both keyword and vector results should be highest scored."""
        kw = _FakeSearcher([_result("a", 1), _result("b", 2), _result("c", 3)])
        vec = _FakeSearcher([_result("a", 1), _result("d", 2)])
        hs = HybridSearcher(kw, vec, alpha=0.6)
        out = hs.search(self._query(top_k=5))
        assert out[0].chunk.id == "a"

    def test_alpha_0_uses_only_keyword(self) -> None:
        """alpha=0 → vector scores are 0, keyword dominates entirely."""
        kw = _FakeSearcher([_result("kw1", 1), _result("kw2", 2)])
        vec = _FakeSearcher([_result("vec1", 1)])
        hs = HybridSearcher(kw, vec, alpha=0.0)
        out = hs.search(self._query())
        ids = {r.chunk.id for r in out}
        # vec-only doc should have 0 score and may still appear but should not beat kw docs
        kw_ids = {"kw1", "kw2"}
        assert kw_ids.issubset(ids) or out[0].chunk.id in kw_ids

    def test_alpha_1_uses_only_vector(self) -> None:
        """alpha=1 → keyword scores are 0, vector dominates entirely."""
        kw = _FakeSearcher([_result("kw1", 1)])
        vec = _FakeSearcher([_result("vec1", 1), _result("vec2", 2)])
        hs = HybridSearcher(kw, vec, alpha=1.0)
        out = hs.search(self._query())
        ids = {r.chunk.id for r in out}
        vec_ids = {"vec1", "vec2"}
        assert vec_ids.issubset(ids) or out[0].chunk.id in vec_ids

    def test_top_k_respected(self) -> None:
        kw = _FakeSearcher([_result(str(i), i) for i in range(1, 11)])
        vec = _FakeSearcher([_result(str(i), i) for i in range(1, 11)])
        hs = HybridSearcher(kw, vec)
        out = hs.search(self._query(top_k=3))
        assert len(out) <= 3

    def test_empty_keyword_results(self) -> None:
        kw = _FakeSearcher([])
        vec = _FakeSearcher([_result("v1", 1), _result("v2", 2)])
        hs = HybridSearcher(kw, vec, alpha=0.6)
        out = hs.search(self._query())
        assert {r.chunk.id for r in out} >= {"v1", "v2"}

    def test_empty_vector_results(self) -> None:
        kw = _FakeSearcher([_result("k1", 1), _result("k2", 2)])
        vec = _FakeSearcher([])
        hs = HybridSearcher(kw, vec, alpha=0.6)
        out = hs.search(self._query())
        assert {r.chunk.id for r in out} >= {"k1", "k2"}

    def test_both_empty_returns_empty(self) -> None:
        kw = _FakeSearcher([])
        vec = _FakeSearcher([])
        hs = HybridSearcher(kw, vec)
        out = hs.search(self._query())
        assert out == []

    def test_output_ranks_are_sequential(self) -> None:
        kw = _FakeSearcher([_result("a", 1), _result("b", 2)])
        vec = _FakeSearcher([_result("c", 1)])
        hs = HybridSearcher(kw, vec)
        out = hs.search(self._query())
        for i, r in enumerate(out, start=1):
            assert r.rank == i

    def test_scores_descending(self) -> None:
        kw = _FakeSearcher([_result("a", 1), _result("b", 2), _result("c", 3)])
        vec = _FakeSearcher([_result("b", 1), _result("d", 2)])
        hs = HybridSearcher(kw, vec)
        out = hs.search(self._query())
        scores = [r.score for r in out]
        assert scores == sorted(scores, reverse=True)
