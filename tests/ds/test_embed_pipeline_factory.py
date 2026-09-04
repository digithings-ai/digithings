"""Unit tests for embed pipeline factory and query.mode helpers (#1177)."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.core.config import DigiSearchConfig
from digisearch.core.models import Chunk
from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.batch import BatchEmbedder
from digisearch.embedding.cache import EmbeddingCache
from digisearch.embedding.factory import (
    EmbeddingConfigError,
    effective_query_mode,
    normalize_query_mode,
    resolve_embedding_pipeline,
    wrap_embedding_pipeline,
)
from digisearch.pipeline.ingest import IngestError, index_chunks
from digisearch.search._stub import get_stub_index


class _RecordingEmbedder(EmbeddingProvider):
    def __init__(self, dimensions: int = 4) -> None:
        self._dimensions = dimensions
        self.calls: list[list[str]] = []
        self.model_id = "recording-test"

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(i + 1)] * self._dimensions for i, _ in enumerate(texts)]

    @property
    def dimensions(self) -> int:
        return self._dimensions


@pytest.mark.unit
def test_normalize_query_mode_accepts_known_values() -> None:
    assert normalize_query_mode("hybrid") == "hybrid"
    assert normalize_query_mode(" VECTOR ") == "vector"
    assert normalize_query_mode("Keyword") == "keyword"


@pytest.mark.unit
def test_normalize_query_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="invalid query.mode"):
        normalize_query_mode("semantic")


@pytest.mark.unit
def test_effective_query_mode_coerces_vector_only_backends() -> None:
    assert effective_query_mode("hybrid", "chroma") == "vector"
    assert effective_query_mode("keyword", "vectorize") == "vector"
    assert effective_query_mode("hybrid", "azure_ai_search") == "hybrid"
    assert effective_query_mode("vector", "chroma") == "vector"


@pytest.mark.unit
def test_wrap_embedding_pipeline_is_cache_over_batch(tmp_path: Path) -> None:
    raw = _RecordingEmbedder()
    pipeline = wrap_embedding_pipeline(raw, use_cache=True, cache_path=str(tmp_path / "c.db"))
    assert isinstance(pipeline, EmbeddingCache)
    assert isinstance(pipeline.provider, BatchEmbedder)
    assert pipeline.provider.provider is raw
    vectors = pipeline.embed(["a", "b"])
    assert len(vectors) == 2
    assert raw.calls == [["a", "b"]]
    pipeline.embed(["a", "b"])
    assert raw.calls == [["a", "b"]]  # cache hit


@pytest.mark.unit
def test_resolve_openai_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DIGISEARCH_EMBED", raising=False)
    with pytest.raises(EmbeddingConfigError, match="OPENAI_API_KEY"):
        resolve_embedding_pipeline()


@pytest.mark.unit
def test_resolve_skips_when_embed_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_EMBED", "0")
    monkeypatch.setenv("DIGISEARCH_EMBEDDING_PROVIDER", "minilm")
    assert resolve_embedding_pipeline() is None


@pytest.mark.unit
def test_resolve_none_without_vector_backend_or_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("DIGISEARCH_EMBED", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("VECTORIZE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("VECTORIZE_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("DIGISEARCH_CONFIG_PATH", raising=False)
    assert resolve_embedding_pipeline(DigiSearchConfig()) is None


@pytest.mark.unit
def test_index_chunks_auto_embeds_when_factory_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    get_stub_index().clear()
    embedder = _RecordingEmbedder(dimensions=3)

    monkeypatch.setattr(
        "digisearch.embedding.factory.resolve_embedding_pipeline",
        lambda *a, **k: embedder,
    )

    chunks = [
        Chunk(id="c1", content="alpha", doc_id="d1", embedding=None),
        Chunk(id="c2", content="beta", doc_id="d1", embedding=None),
    ]
    backend = index_chunks("auto-embed", chunks)
    assert backend == "stub"
    assert len(embedder.calls) == 1
    assert all(c.embedding is not None for c in chunks)
    assert all(len(c.embedding or []) == 3 for c in chunks)


@pytest.mark.unit
def test_index_chunks_raises_on_bad_embed_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    get_stub_index().clear()

    def _boom(*_a, **_k):
        raise EmbeddingConfigError("openai configured but OPENAI_API_KEY is unset")

    monkeypatch.setattr(
        "digisearch.embedding.factory.resolve_embedding_pipeline",
        _boom,
    )
    chunks = [Chunk(id="c1", content="x", doc_id="d1", embedding=None)]
    with pytest.raises(IngestError, match="OPENAI_API_KEY") as exc_info:
        index_chunks("bad-embed", chunks)
    assert exc_info.value.code == "ingest_embed_config"
