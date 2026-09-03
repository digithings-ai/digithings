"""Phase 1 (#2437): wire EmbeddingProvider into ChromaBackend (behavior-preserving)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from digisearch.core.models import Chunk, Query
from digisearch.embedding.providers.minilm import (
    MINILM_DIMENSIONS,
    MINILM_MODEL_ID,
    MiniLMEmbedder,
)
from digisearch.indexes.backends.chroma import ChromaBackend


class _FakeEmbedder:
    """Deterministic embedder for unit tests (no ONNX)."""

    model_id = "fake-model-8"
    version = "1"

    def __init__(self) -> None:
        self.embed_calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        out: list[list[float]] = []
        for text in texts:
            base = float(len(text) % 7) / 7.0
            out.append([base + i * 0.01 for i in range(8)])
        return out

    @property
    def dimensions(self) -> int:
        return 8


def _backend_with_collection(
    collection: MagicMock,
    *,
    embedding_provider: object | None = None,
    collection_metadata: dict[str, Any] | None = None,
) -> ChromaBackend:
    collection.metadata = dict(collection_metadata or {"hnsw:space": "cosine"})
    with patch("digisearch.indexes.backends.chroma._CHROMA_AVAILABLE", True):
        with patch("digisearch.indexes.backends.chroma.chromadb") as chromadb_mod:
            client = MagicMock()
            chromadb_mod.Client.return_value = client
            client.get_or_create_collection.return_value = collection
            return ChromaBackend("test-index", embedding_provider=embedding_provider)


@pytest.mark.unit
def test_embedding_provider_default_used_on_add_and_query() -> None:
    """No explicit provider → MiniLMEmbedder; embed() called when vectors missing."""
    collection = MagicMock()
    fake = _FakeEmbedder()
    with patch(
        "digisearch.indexes.backends.chroma._get_default_embedder",
        return_value=fake,
    ):
        backend = _backend_with_collection(collection, embedding_provider=None)
        backend.add(
            [Chunk(id="c0", content="hello world", doc_id="d0", embedding=None, metadata={})]
        )
        backend.query(Query(text="hello world", top_k=3))

    assert fake.embed_calls == [["hello world"], ["hello world"]]
    assert collection.upsert.call_count == 1
    upsert_kw = collection.upsert.call_args.kwargs
    assert len(upsert_kw["embeddings"]) == 1
    assert len(upsert_kw["embeddings"][0]) == 8
    assert collection.query.call_count == 1
    qe = collection.query.call_args.kwargs["query_embeddings"]
    assert len(qe) == 1 and len(qe[0]) == 8


@pytest.mark.unit
def test_stub_call_sites_pass_embedding_provider() -> None:
    """Every ChromaBackend(...) in _stub.py must pass embedding_provider=."""
    from digisearch.search import _stub

    source = Path(inspect.getsourcefile(_stub)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "ChromaBackend":
                calls.append(node)
    assert len(calls) >= 3
    for call in calls:
        names = {kw.arg for kw in call.keywords if kw.arg}
        assert "embedding_provider" in names, ast.dump(call)


@pytest.mark.unit
def test_partial_embedding_raises() -> None:
    """Mixed precomputed / missing embeddings must raise, not discard vectors."""
    collection = MagicMock()
    fake = _FakeEmbedder()
    backend = _backend_with_collection(collection, embedding_provider=fake)
    chunks = [
        Chunk(id="c0", content="a", doc_id="d0", embedding=[0.1] * 8, metadata={}),
        Chunk(id="c1", content="b", doc_id="d0", embedding=None, metadata={}),
        Chunk(id="c2", content="c", doc_id="d0", embedding=[0.2] * 8, metadata={}),
    ]
    with pytest.raises(ValueError, match=r"c1") as exc_info:
        backend.add(chunks)
    assert "partial" in str(exc_info.value).lower()
    collection.upsert.assert_not_called()
    assert fake.embed_calls == []


@pytest.mark.unit
def test_embedding_metadata_written_and_mismatch_raises() -> None:
    """Fresh writes stamp model metadata; mismatched construct raises."""
    collection = MagicMock()
    fake = _FakeEmbedder()
    # Simulate a legacy collection created without embedding metadata.
    backend = _backend_with_collection(
        collection,
        embedding_provider=fake,
        collection_metadata={"hnsw:space": "cosine"},
    )
    backend.add([Chunk(id="c0", content="x", doc_id="d0", embedding=None, metadata={})])

    assert collection.modify.called
    meta = collection.modify.call_args.kwargs.get("metadata") or {}
    assert meta.get("embedding_model_id") == fake.model_id
    assert meta.get("embedding_dimensions") == fake.dimensions
    assert meta.get("embedding_version") == fake.version

    other = _FakeEmbedder()
    other.model_id = "other-model"
    with pytest.raises(ValueError, match=r"embedding_model_id|model"):
        _backend_with_collection(
            collection,
            embedding_provider=other,
            collection_metadata={
                "hnsw:space": "cosine",
                "embedding_model_id": fake.model_id,
                "embedding_dimensions": fake.dimensions,
                "embedding_version": fake.version,
            },
        )


@pytest.mark.unit
def test_no_op_behavior_preserving_minilm_matches_chroma_onnx() -> None:
    """MiniLMEmbedder wraps the same ONNX model Chroma bundled — vectors match."""
    pytest.importorskip("chromadb")
    from chromadb.utils import embedding_functions

    texts = ["revenue growth outlook", "quarterly earnings call"]
    bundled = embedding_functions.ONNXMiniLM_L6_V2()
    provider = MiniLMEmbedder()
    bundled_vecs = [[float(x) for x in v] for v in bundled(list(texts))]
    provider_vecs = provider.embed(texts)
    assert provider.dimensions == MINILM_DIMENSIONS
    assert MINILM_MODEL_ID.startswith("all-MiniLM")
    assert len(provider_vecs) == len(bundled_vecs)
    for a, b in zip(provider_vecs, bundled_vecs, strict=True):
        assert len(a) == len(b) == MINILM_DIMENSIONS
        assert a == b
