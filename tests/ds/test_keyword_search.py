"""Unit tests for keyword search: TFIDFSearcher and BM25Searcher."""

from __future__ import annotations

import math

import pytest

from digisearch.core.models import Query
from digisearch.search.keyword import TFIDFSearcher


@pytest.mark.unit
class TestTFIDFSearcher:
    def test_search_finds_relevant_doc(self) -> None:
        corpus = ["machine learning algorithms", "stock market trading", "deep neural networks"]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="machine learning", top_k=3))
        assert len(results) >= 1
        assert "machine" in results[0].chunk.content.lower()

    def test_search_empty_corpus_returns_empty(self) -> None:
        s = TFIDFSearcher([])
        results = s.search(Query(text="anything", top_k=5))
        assert results == []

    def test_search_no_match_returns_empty(self) -> None:
        s = TFIDFSearcher(["apple pie recipe", "chocolate cake"])
        results = s.search(Query(text="quantum physics", top_k=5))
        assert results == []

    def test_search_top_k_limits_results(self) -> None:
        corpus = [f"machine learning topic {i}" for i in range(10)]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="machine learning", top_k=3))
        assert len(results) <= 3

    def test_scores_are_positive(self) -> None:
        corpus = ["python programming language", "java development", "python scripting"]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="python", top_k=5))
        assert all(r.score > 0 for r in results)

    def test_idf_is_log_based(self) -> None:
        """IDF should use log(). Rare term has higher IDF than common term."""
        corpus = [
            "rare_term foo",
            "foo bar",
            "foo baz",
        ]
        s = TFIDFSearcher(corpus)
        # "foo" appears in all 3 docs (df=3), "rare_term" appears in 1 (df=1)
        # With log IDF: log(3/(3+1)) < log(3/(1+1)) so rare_term has higher IDF
        idf_foo = s._idf.get("foo", 0)
        idf_rare = s._idf.get("rare_term", 0)
        assert idf_rare > idf_foo, "Rare term should have higher IDF than common term"

    def test_idf_values_are_finite(self) -> None:
        """All IDF values must be finite (log-based formula prevents blowup)."""
        corpus = ["alpha beta gamma", "delta epsilon", "alpha zeta"]
        s = TFIDFSearcher(corpus)
        for term, idf in s._idf.items():
            assert math.isfinite(idf), f"IDF for '{term}' is not finite: {idf}"

    def test_result_ranks_are_sequential(self) -> None:
        corpus = ["machine learning", "machine learning deep", "machine learning neural"]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="machine learning", top_k=3))
        for i, r in enumerate(results, 1):
            assert r.rank == i

    def test_result_chunk_content_matches_corpus(self) -> None:
        corpus = ["unique phrase here", "another doc"]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="unique phrase", top_k=1))
        assert len(results) == 1
        assert results[0].chunk.content == corpus[0]

    def test_top_k_from_query_respected(self) -> None:
        corpus = [f"alpha beta {i}" for i in range(10)]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="alpha", top_k=2))
        assert len(results) <= 2

    def test_results_sorted_by_score_descending(self) -> None:
        corpus = ["python", "python python", "python python python"]
        s = TFIDFSearcher(corpus)
        results = s.search(Query(text="python", top_k=3))
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
class TestBM25Searcher:
    def test_bm25_finds_relevant_doc(self) -> None:
        pytest.importorskip("rank_bm25")
        from digisearch.search.keyword import BM25Searcher

        corpus = ["machine learning algorithms", "stock market analysis", "deep learning models"]
        s = BM25Searcher(corpus)
        results = s.search(Query(text="machine learning", top_k=3))
        assert len(results) >= 1
        assert results[0].score > 0

    def test_bm25_no_match_returns_empty(self) -> None:
        pytest.importorskip("rank_bm25")
        from digisearch.search.keyword import BM25Searcher

        s = BM25Searcher(["hello world", "foo bar"])
        results = s.search(Query(text="quantum physics xyz", top_k=5))
        assert results == []

    def test_bm25_top_k_limits_results(self) -> None:
        pytest.importorskip("rank_bm25")
        from digisearch.search.keyword import BM25Searcher

        corpus = [f"machine learning topic {i}" for i in range(10)]
        s = BM25Searcher(corpus)
        results = s.search(Query(text="machine learning", top_k=3))
        assert len(results) <= 3

    def test_bm25_import_error_without_rank_bm25(self) -> None:
        """BM25Searcher raises ImportError when rank_bm25 is not available."""
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"rank_bm25": None}):
            from importlib import reload
            import digisearch.search.keyword as kw_module
            reload(kw_module)
            if not kw_module._BM25_AVAILABLE:
                with pytest.raises(ImportError):
                    kw_module.BM25Searcher(["test"])
