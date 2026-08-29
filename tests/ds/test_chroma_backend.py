"""Unit tests for ChromaBackend ingest metadata handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from digisearch.core.models import Chunk
from digisearch.indexes.backends.chroma import ChromaBackend


@pytest.mark.unit
def test_add_keeps_canonical_doc_id_over_spoofed_metadata() -> None:
    """Caller metadata must not overwrite backend-controlled doc_id."""
    chunk = Chunk(
        id="c0",
        content="hello",
        doc_id="real-doc-id",
        embedding=None,
        metadata={"doc_id": "spoofed-doc-id", "title": "Example"},
    )
    collection = MagicMock()
    with patch("digisearch.indexes.backends.chroma._CHROMA_AVAILABLE", True):
        with patch("digisearch.indexes.backends.chroma.chromadb") as chromadb_mod:
            client = MagicMock()
            chromadb_mod.Client.return_value = client
            client.get_or_create_collection.return_value = collection
            backend = ChromaBackend("test-index")
            backend.add([chunk])

    assert collection.add.call_count == 1
    metadatas = collection.add.call_args.kwargs["metadatas"]
    assert metadatas[0]["doc_id"] == "real-doc-id"
    assert metadatas[0]["title"] == "Example"
