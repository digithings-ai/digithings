"""Unit tests for DigiSearch."""

from __future__ import annotations

import pytest

from digisearch.core.models import Chunk, Query
from digisearch.search import add_chunks, query_index


@pytest.mark.unit
def test_query_empty_index() -> None:
    """Query on empty index returns no results."""
    q = Query(text="test", top_k=5)
    response = query_index(q, index_name="__unit_test_empty__")
    assert response.results == []


@pytest.mark.unit
def test_add_and_query() -> None:
    """Add chunks and query finds them."""
    idx = "__unit_test_add_query__"
    chunk = Chunk(
        id="c1",
        content="Mean reversion strategy uses Bollinger Bands",
        doc_id="d1",
        embedding=None,
        metadata={},
    )
    add_chunks(idx, [chunk])
    q = Query(text="mean reversion", top_k=5)
    response = query_index(q, index_name=idx)
    assert len(response.results) == 1
    assert response.results[0].chunk.content == chunk.content
    assert response.results[0].score > 0
