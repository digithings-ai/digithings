"""Tests for chunkers."""

from __future__ import annotations

import pytest

from digisearch.core.models import Document
from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
from digisearch.ingestion.chunkers.recursive import RecursiveChunker


@pytest.mark.unit
def test_fixed_chunker() -> None:
    doc = Document(id="d1", content="a" * 1000, source="x", doc_type="txt")
    ch = FixedSizeChunker(chunk_size=100)
    chunks = ch.chunk(doc)
    assert len(chunks) >= 10
    assert all(c.doc_id == "d1" for c in chunks)


@pytest.mark.unit
def test_recursive_chunker() -> None:
    doc = Document(id="d1", content="Para one.\n\nPara two.\n\nPara three.", source="x", doc_type="txt")
    ch = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    chunks = ch.chunk(doc)
    assert len(chunks) >= 1
    assert chunks[0].content
