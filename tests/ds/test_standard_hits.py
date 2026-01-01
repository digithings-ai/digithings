"""Tests for portable query hit normalization across backends."""

from __future__ import annotations

import pytest
from digisearch.core.models import Chunk, Result
from digisearch.core.standard_hits import STANDARD_HIT_KEYS, normalize_query_hit

pytestmark = pytest.mark.unit


def test_normalize_hit_stable_keys_and_azure_extraction() -> None:
    chunk = Chunk(
        id="k1",
        content="hello world " * 100,
        doc_id="d1",
        metadata={
            "title": "Doc",
            "venue": "SEC EDGAR",
            "@search.score": 2.5,
            "@search.highlights": {"content": ["<em>hello</em>"]},
            "@search.captions": [{"text": "cap"}],
            "@search.reranker_score": 1.23,
            "@search.some_future_field": "x",
        },
    )
    r = Result(chunk=chunk, score=2.5, rank=1)
    out = normalize_query_hit(r, content_preview_max=20)

    for key in STANDARD_HIT_KEYS:
        assert key in out
    assert out["chunk_id"] == "k1"
    assert out["doc_id"] == "d1"
    assert out["rank"] == 1
    assert out["score"] == 2.5
    assert out["content_truncated"] is True
    assert out["content_length"] == len(chunk.content)
    assert "@search" not in "".join(out["metadata"].keys())
    assert out["highlights"] == {"content": ["<em>hello</em>"]}
    assert out["captions"] == [{"text": "cap"}]
    assert out["reranker_score"] == 1.23
    assert out["backend_extras"] == {"@search.some_future_field": "x"}


def test_full_content_when_preview_max_zero() -> None:
    ch = Chunk(id="a", content="abc", doc_id="d", metadata={})
    out = normalize_query_hit(Result(chunk=ch, score=1.0, rank=None), content_preview_max=0)
    assert out["content"] == "abc"
    assert out["content_truncated"] is False
