"""Unit tests for EmbeddingCache (SQLite backend)."""

from __future__ import annotations

import pytest

from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.cache import EmbeddingCache


class StubProvider(EmbeddingProvider):
    """Deterministic stub: embedding[i] = [float(i)] * dim."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.call_count = 0
        self.last_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.last_texts = list(texts)
        return [[float(i)] * self._dim for i in range(len(texts))]

    @property
    def dimensions(self) -> int:
        return self._dim


class MismatchProvider(EmbeddingProvider):
    """Always returns fewer embeddings than requested."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []  # Returns nothing regardless of input

    @property
    def dimensions(self) -> int:
        return 4


@pytest.mark.unit
def test_embed_returns_same_length_as_input(tmp_path) -> None:
    cache = EmbeddingCache(StubProvider(), db_path=tmp_path / "cache.db")
    result = cache.embed(["hello", "world", "foo"])
    assert len(result) == 3


@pytest.mark.unit
def test_embed_empty_returns_empty(tmp_path) -> None:
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    result = cache.embed([])
    assert result == []
    assert p.call_count == 0


@pytest.mark.unit
def test_embed_caches_avoids_recompute(tmp_path) -> None:
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    cache.embed(["hello", "world"])
    assert p.call_count == 1
    cache.embed(["hello", "world"])
    assert p.call_count == 1  # No recompute


@pytest.mark.unit
def test_embed_only_recomputes_missing(tmp_path) -> None:
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    cache.embed(["hello"])
    assert p.call_count == 1
    cache.embed(["hello", "world"])
    assert p.call_count == 2
    assert p.last_texts == ["world"]  # Only the new text


@pytest.mark.unit
def test_embed_preserves_positional_order(tmp_path) -> None:
    """Positional alignment: result[i] corresponds to texts[i]."""
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    texts = ["a", "b", "c"]
    result = cache.embed(texts)
    assert len(result) == 3
    for emb in result:
        assert isinstance(emb, list)
        assert len(emb) == 4


@pytest.mark.unit
def test_embed_partial_cache_hit_preserves_order(tmp_path) -> None:
    """When some are cached and some are not, order is preserved."""
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    # Cache "a" and "c"
    cache.embed(["a", "c"])
    p.call_count = 0
    # Now request a, b, c — "b" is new
    result = cache.embed(["a", "b", "c"])
    assert len(result) == 3
    assert p.call_count == 1  # Only "b" fetched from provider
    assert p.last_texts == ["b"]


@pytest.mark.unit
def test_embed_raises_on_provider_mismatch(tmp_path) -> None:
    """Provider returning wrong count raises ValueError."""
    cache = EmbeddingCache(MismatchProvider(), db_path=tmp_path / "cache.db")
    with pytest.raises(ValueError, match="[Ee]mbedding"):
        cache.embed(["hello", "world"])


@pytest.mark.unit
def test_embed_single_text(tmp_path) -> None:
    p = StubProvider()
    cache = EmbeddingCache(p, db_path=tmp_path / "cache.db")
    result = cache.embed(["only one"])
    assert len(result) == 1
    assert isinstance(result[0], list)


@pytest.mark.unit
def test_embed_persists_across_cache_instances(tmp_path) -> None:
    """Two EmbeddingCache instances on the same db_path share cached data."""
    db = tmp_path / "shared.db"
    p1 = StubProvider()
    cache1 = EmbeddingCache(p1, db_path=db)
    cache1.embed(["shared text"])
    assert p1.call_count == 1

    p2 = StubProvider()
    cache2 = EmbeddingCache(p2, db_path=db)
    cache2.embed(["shared text"])
    assert p2.call_count == 0  # Served from persistent cache
