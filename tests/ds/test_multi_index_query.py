"""Unit tests for comma-separated multi-index fan-out in query_index (#4756)."""

from __future__ import annotations

import logging

import pytest
from digisearch.core.models import Chunk, Query, Result, SearchResponse

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


# --- fan-out leg isolation (#4991) -------------------------------------------------
#
# Production incident: one broken index in "occ_help,occ_tickets" aborted the whole
# fan-out comprehension, so a fault on occ_tickets also took occ_help down and the
# whole OCC tenant returned status "failed". Each leg is now isolated.


class _EmbeddingModelMismatchError(Exception):
    """Stand-in for digisearch's Chroma-side model mismatch, which is NOT a
    _BACKEND_ERRORS member -- that is exactly why it used to escape."""


def _patch_legs(monkeypatch: pytest.MonkeyPatch, **behaviour: str | Exception) -> None:
    """Make `_query_single_index` succeed ('ok') or raise, per index name."""
    from digisearch.search import _stub

    def _fake(query: Query, index_name: str) -> SearchResponse:
        outcome = behaviour.get(index_name, "ok")
        # BaseException, not Exception: KeyboardInterrupt is not an Exception
        # subclass, and this helper must be able to raise one.
        if isinstance(outcome, BaseException):
            raise outcome
        return _fake.SearchResponse(
            results=[Result(chunk=_chunk(f"{index_name}-1", "alpha"), score=0.5, rank=1)],
            facets=None,
            backend=index_name,
        )

    _fake.SearchResponse = SearchResponse  # type: ignore[attr-defined]
    monkeypatch.setattr(_stub, "_query_single_index", _fake)


def _single_failure(index_name: str, error: Exception) -> str:
    return f"{index_name} must be the leg that fails"


def test_failing_leg_does_not_take_down_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    _patch_legs(
        monkeypatch,
        occ_help="ok",
        occ_tickets=_EmbeddingModelMismatchError("written under a different embedder"),
    )
    from digisearch.search._stub import query_index

    resp = query_index(Query(text="alpha", top_k=10), index_name="occ_help,occ_tickets")

    # occ_help still answers; backend stays 'multi' because we did fan out.
    assert [r.chunk.id for r in resp.results] == ["occ_help-1"]
    assert resp.backend == "multi"


def test_failing_leg_is_logged_with_its_index_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    _patch_legs(
        monkeypatch,
        occ_help="ok",
        occ_tickets=_EmbeddingModelMismatchError("written under a different embedder"),
    )
    from digisearch.search._stub import query_index

    with caplog.at_level(logging.ERROR):
        query_index(Query(text="alpha", top_k=10), index_name="occ_help,occ_tickets")

    dropped = [r for r in caplog.records if getattr(r, "index_name", None) == "occ_tickets"]
    assert len(dropped) == 1, _single_failure("occ_tickets", _EmbeddingModelMismatchError("x"))
    assert dropped[0].outcome == "degraded"
    assert dropped[0].error_type == "_EmbeddingModelMismatchError"


def test_all_legs_failing_raises_rather_than_returning_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty fan-out must not read downstream as 'no matching rows'.

    Returning an empty SearchResponse would let the assistant answer confidently
    that nothing was found; a visible failure is the honest outcome.
    """
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    boom = _EmbeddingModelMismatchError("every leg broken")
    _patch_legs(monkeypatch, occ_help=boom, occ_tickets=boom)
    from digisearch.search._stub import query_index

    with pytest.raises(_EmbeddingModelMismatchError):
        query_index(Query(text="alpha", top_k=10), index_name="occ_help,occ_tickets")


def test_single_index_path_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fast path must NOT be silently degraded -- no fan-out, no isolation."""
    _patch_legs(monkeypatch, solo=_EmbeddingModelMismatchError("single index broken"))
    from digisearch.search._stub import query_index

    with pytest.raises(_EmbeddingModelMismatchError):
        query_index(Query(text="alpha", top_k=10), index_name="solo")


def test_one_surviving_leg_keeps_its_results_ordered_by_rrf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    _patch_legs(monkeypatch, a="ok", b=_EmbeddingModelMismatchError("b broken"), c="ok")
    from digisearch.search._stub import query_index

    resp = query_index(Query(text="alpha", top_k=10), index_name="a,b,c")

    assert sorted(r.chunk.id for r in resp.results) == ["a-1", "c-1"]
    assert [r.rank for r in resp.results] == [1, 2]


def test_base_exceptions_are_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only Exception is caught; KeyboardInterrupt/SystemExit must propagate."""
    monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
    _patch_legs(monkeypatch, good="ok", bad=KeyboardInterrupt())
    from digisearch.search._stub import query_index

    with pytest.raises(KeyboardInterrupt):
        query_index(Query(text="alpha", top_k=10), index_name="good,bad")
