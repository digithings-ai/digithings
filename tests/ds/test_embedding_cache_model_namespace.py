"""REM-103: embedding cache keys are namespaced by provider model identity."""

from __future__ import annotations

import pytest

from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.cache import EmbeddingCache


class _CountingProvider(EmbeddingProvider):
    def __init__(self, model_id: str, vector: list[float]) -> None:
        self.model_id = model_id
        self._vector = vector
        self.call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return [list(self._vector) for _ in texts]

    @property
    def dimensions(self) -> int:
        return len(self._vector)


@pytest.mark.unit
def test_model_change_is_cache_miss(tmp_path) -> None:
    db = tmp_path / "cache.db"
    text = ["shared chunk"]
    provider_a = _CountingProvider("model-a", [1.0, 0.0])
    EmbeddingCache(provider_a, db_path=db).embed(text)
    assert provider_a.call_count == 1

    provider_b = _CountingProvider("model-b", [0.0, 1.0])
    result = EmbeddingCache(provider_b, db_path=db).embed(text)
    assert provider_b.call_count == 1
    assert result == [[0.0, 1.0]]
