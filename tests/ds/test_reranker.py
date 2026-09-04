"""Unit tests for digisearch Reranker + DIGISEARCH_RERANK_ENABLED wiring (#2441)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from digisearch.core.models import Chunk, Query, Result
from digisearch.search.reranker import BGE_RERANKER_MODEL, Reranker


def _chunk(cid: str, content: str | None = None) -> Chunk:
    return Chunk(id=cid, content=content or f"content-{cid}", doc_id=f"doc-{cid}")


def _result(cid: str, rank: int = 1, score: float = 1.0) -> Result:
    return Result(chunk=_chunk(cid), score=score, rank=rank)


@pytest.mark.unit
class TestRerankerModelId:
    def test_bge_uses_v2_m3_not_base(self) -> None:
        assert BGE_RERANKER_MODEL == "BAAI/bge-reranker-v2-m3"
        import inspect

        from digisearch.search import reranker as mod

        src = inspect.getsource(mod)
        assert "bge-reranker-v2-m3" in src
        assert "bge-reranker-base" not in src


@pytest.mark.unit
class TestRerankerTopN:
    def test_reranker_top_n_defaults_to_input_length(self) -> None:
        """No silent cap at 5 when top_n omitted — returns min(len, caller's top_k)."""
        results = [_result(str(i), rank=i + 1) for i in range(8)]

        class _Passthrough(Reranker):
            def _rerank_bge(self, query: str, results: list[Result], n: int) -> list[Result]:
                return results[:n]

        r = _Passthrough(provider="bge")
        # Caller top_k=8, no constructor default cap → all 8 (not capped at 5).
        out = r.rerank("q", results, top_n=8)
        assert len(out) == 8

        # Constructor default None + no top_n arg → len(results).
        out2 = r.rerank("q", results)
        assert len(out2) == 8


@pytest.mark.unit
class TestRerankerFailureLogging:
    def test_reranker_cohere_failure_logs_and_falls_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        results = [_result("a"), _result("b"), _result("c")]
        fake = MagicMock()
        fake.Client.side_effect = RuntimeError("cohere boom")
        with patch.dict("sys.modules", {"cohere": fake}):
            with caplog.at_level(logging.WARNING, logger="digisearch.search.reranker"):
                out = Reranker(provider="cohere").rerank("q", results, top_n=2)
        assert len(out) == 2
        assert [x.chunk.id for x in out] == ["a", "b"]
        assert any("Cohere" in rec.message for rec in caplog.records)

    def test_reranker_bge_failure_logs_and_falls_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        results = [_result("a"), _result("b"), _result("c")]
        fake_st = MagicMock()
        fake_st.CrossEncoder.side_effect = RuntimeError("bge boom")
        with patch.dict("sys.modules", {"sentence_transformers": fake_st}):
            with caplog.at_level(logging.WARNING, logger="digisearch.search.reranker"):
                out = Reranker(provider="bge").rerank("q", results, top_n=2)
        assert len(out) == 2
        assert [x.chunk.id for x in out] == ["a", "b"]
        assert any("BGE" in rec.message for rec in caplog.records)


@pytest.mark.unit
class TestQueryIndexRerank:
    def test_query_index_rerank_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGISEARCH_RERANK_ENABLED", raising=False)
        monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
        from digisearch.search._stub import _stub_index, query_index

        _stub_index.clear()
        _stub_index["rr"] = [
            _chunk("1", "alpha beta gamma"),
            _chunk("2", "alpha beta"),
            _chunk("3", "alpha"),
        ]
        called: list[Any] = []

        def _track(*args: Any, **kwargs: Any) -> list[Result]:
            called.append(True)
            return list(args[1]) if len(args) > 1 else []

        with patch("digisearch.search.reranker.Reranker.rerank", side_effect=_track):
            resp = query_index(Query(text="alpha", top_k=10), index_name="rr")
        assert called == []
        assert [r.chunk.id for r in resp.results] == ["1", "2", "3"]

    def test_query_index_rerank_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGISEARCH_RERANK_ENABLED", "1")
        monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
        monkeypatch.setenv("DIGISEARCH_RERANK_PROVIDER", "bge")
        from digisearch.search._stub import _stub_index, query_index

        _stub_index.clear()
        _stub_index["rr2"] = [
            _chunk("1", "alpha beta gamma"),
            _chunk("2", "alpha beta"),
            _chunk("3", "alpha"),
        ]

        def _reorder(
            self: Reranker, query: str, results: list[Result], top_n: int | None = None
        ) -> list[Result]:
            n = top_n if top_n is not None else len(results)
            reordered = list(reversed(results))[:n]
            return [
                Result(chunk=r.chunk, score=float(len(reordered) - i), rank=i + 1)
                for i, r in enumerate(reordered)
            ]

        with patch.object(Reranker, "rerank", _reorder):
            resp = query_index(Query(text="alpha", top_k=10), index_name="rr2")
        assert [r.chunk.id for r in resp.results] == ["3", "2", "1"]


@pytest.mark.unit
class TestFetchAllRerankSuppression:
    def test_fetch_all_skip_rerank_even_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGISEARCH_RERANK_ENABLED", "1")
        monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
        from digisearch.core.models import Chunk
        from digisearch.search import add_chunks
        from digisearch.server import app
        from fastapi.testclient import TestClient

        from tests.digi_test_jwt import auth_headers

        idx = "__fetch_all_rerank__"
        for i in range(3):
            add_chunks(
                idx,
                [
                    Chunk(
                        id=f"f{i}",
                        content=f"fetch all alpha doc {i}",
                        doc_id=f"d{i}",
                        embedding=None,
                    )
                ],
            )

        called: list[bool] = []

        def _track(
            self: Reranker, query: str, results: list[Result], top_n: int | None = None
        ) -> list[Result]:
            called.append(True)
            return results[: top_n or len(results)]

        client = TestClient(app, headers=auth_headers())
        with patch.object(Reranker, "rerank", _track):
            r = client.post(
                "/v1/orchestrator_invoke",
                json={
                    "tool": "digisearch_fetch_all",
                    "arguments": {"query": "alpha", "index_name": idx, "max_results": 10},
                },
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert called == [], "fetch_all pages must set skip_rerank and not invoke Reranker"

        # Control: single-shot digisearch tool should invoke rerank when enabled.
        called.clear()
        with patch.object(Reranker, "rerank", _track):
            r2 = client.post(
                "/v1/orchestrator_invoke",
                json={
                    "tool": "digisearch",
                    "arguments": {"query": "alpha", "index_name": idx, "top_k": 5},
                },
            )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("ok") is True
        assert called == [True]
