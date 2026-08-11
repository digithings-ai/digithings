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


@pytest.mark.unit
def test_recursive_chunker_default_size_is_token_scaled() -> None:
    from digisearch.ingestion.chunkers.recursive import (
        DEFAULT_CHUNK_CHARS,
        DEFAULT_CHUNK_OVERLAP,
    )

    assert DEFAULT_CHUNK_CHARS == 2000
    assert DEFAULT_CHUNK_OVERLAP == 250
    ch = RecursiveChunker()
    assert ch.chunk_size == DEFAULT_CHUNK_CHARS
    assert ch.chunk_overlap == DEFAULT_CHUNK_OVERLAP


@pytest.mark.unit
def test_recursive_chunker_respects_larger_default() -> None:
    doc = Document(id="d2", content="word " * 600, source="x", doc_type="txt")
    chunks = RecursiveChunker().chunk(doc)
    assert all(len(c.content) <= 2000 for c in chunks)
    assert len(chunks) <= 3
