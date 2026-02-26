"""Tests for embedding providers."""

from __future__ import annotations

import pytest

from digisearch.embedding.base import EmbeddingProvider


class StubEmbedder(EmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]

    @property
    def dimensions(self) -> int:
        return 4


@pytest.mark.unit
def test_stub_embedder() -> None:
    e = StubEmbedder()
    r = e.embed(["hello"])
    assert len(r) == 1
    assert len(r[0]) == 4
    assert e.dimensions == 4
