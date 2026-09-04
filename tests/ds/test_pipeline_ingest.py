"""Unit tests for the canonical digisearch ingest pipeline (#1189)."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.core.models import Chunk
from digisearch.embedding.base import EmbeddingProvider
from digisearch.pipeline.ingest import (
    IngestError,
    apply_embeddings,
    ingest_source,
)
from digisearch.search._stub import get_stub_index


class _RecordingEmbedder(EmbeddingProvider):
    """Deterministic embedder that records calls for assertions."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(i + 1)] * self._dimensions for i, _ in enumerate(texts)]

    @property
    def dimensions(self) -> int:
        return self._dimensions


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    # Keep pipeline unit tests free of MiniLM/OpenAI unless a test opts in.
    monkeypatch.setenv("DIGISEARCH_EMBED", "0")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    get_stub_index().clear()


@pytest.mark.unit
def test_ingest_source_chunks_and_indexes(tmp_path: Path) -> None:
    doc = tmp_path / "note.md"
    doc.write_text("# Title\n\n" + ("paragraph text. " * 40), encoding="utf-8")

    result = ingest_source(doc, index_name="pipeline-test")

    assert result.status == "ok"
    assert result.chunks_created >= 1
    assert result.backend == "stub"
    assert result.doc_id
    indexed = get_stub_index().get("pipeline-test") or []
    assert len(indexed) == result.chunks_created
    assert all(c.content for c in indexed)


@pytest.mark.unit
def test_ingest_source_embed_hook_when_configured(tmp_path: Path) -> None:
    doc = tmp_path / "embed-me.md"
    doc.write_text("Short body for embedding.\n", encoding="utf-8")
    embedder = _RecordingEmbedder(dimensions=4)

    result = ingest_source(
        doc,
        index_name="embed-test",
        embedding_provider=embedder,
    )

    assert result.chunks_created >= 1
    assert len(embedder.calls) == 1
    assert len(embedder.calls[0]) == result.chunks_created
    indexed = get_stub_index()["embed-test"]
    assert all(c.embedding is not None for c in indexed)
    assert all(len(c.embedding or []) == 4 for c in indexed)


@pytest.mark.unit
def test_apply_embeddings_rejects_partial_batch() -> None:
    chunks = [
        Chunk(id="a", content="one", doc_id="d", embedding=[0.1, 0.2]),
        Chunk(id="b", content="two", doc_id="d", embedding=None),
    ]
    with pytest.raises(IngestError, match="partial embedding"):
        apply_embeddings(chunks, _RecordingEmbedder())


@pytest.mark.unit
def test_ingest_source_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "gone.md"
    with pytest.raises(IngestError) as exc_info:
        ingest_source(missing, index_name="x")
    assert exc_info.value.http_status == 404
    assert exc_info.value.code == "ingest_source_not_found"


@pytest.mark.unit
def test_ingest_source_enforces_ingest_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("nope", encoding="utf-8")
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(jail))

    with pytest.raises(IngestError) as exc_info:
        ingest_source(outside, index_name="x", enforce_ingest_root=True)
    assert exc_info.value.http_status == 400
    assert exc_info.value.code == "ingest_source_rejected"


@pytest.mark.unit
def test_http_ingest_delegates_to_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(tmp_path))
    doc = tmp_path / "http.md"
    doc.write_text("# HTTP\n\nbody text for ingest.\n", encoding="utf-8")

    from digisearch.server import app
    from fastapi.testclient import TestClient

    from tests.digi_test_jwt import auth_headers

    client = TestClient(app, headers=auth_headers())
    response = client.post(
        "/ingest",
        json={"source": str(doc), "index_name": "http-pipeline"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chunks_created"] >= 1
    assert body["status"] == "ok"
    assert body["index_name"] == "http-pipeline"
