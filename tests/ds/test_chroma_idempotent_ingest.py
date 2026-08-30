"""Unit tests for idempotent Chroma ingest."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("chromadb")

from digisearch.chunking.factory import get_ingest_chunker
from digisearch.core.evidence_metadata import merge_document_metadata_into_chunks
from digisearch.indexes.backends.chroma import ChromaBackend
from digisearch.ingestion.registry import ParserRegistry


@pytest.mark.unit
def test_chroma_reseed_same_corpus_does_not_duplicate_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-ingesting an unchanged file replaces chunks instead of appending duplicates."""
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    doc_path = tmp_path / "note.md"
    doc_path.write_text("# Title\n\n" + ("paragraph text. " * 80), encoding="utf-8")

    registry = ParserRegistry()
    doc_first = registry.parse(doc_path)
    doc_second = registry.parse(doc_path)
    assert doc_first.id == doc_second.id

    chunker = get_ingest_chunker()
    chunks_first = chunker.chunk(doc_first)
    merge_document_metadata_into_chunks(doc_first, chunks_first)
    chunks_second = chunker.chunk(doc_second)
    merge_document_metadata_into_chunks(doc_second, chunks_second)
    assert [c.id for c in chunks_first] == [c.id for c in chunks_second]

    backend = ChromaBackend("reseed-idempotent-test")
    backend.add(chunks_first)
    count_after_first = backend._collection.count()

    backend.add(chunks_second)
    assert backend._collection.count() == count_after_first
