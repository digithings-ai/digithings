"""Tests for the local MiniLM embedding provider."""

from __future__ import annotations

import json

import numpy
import pytest
from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder


@pytest.mark.unit
def test_minilm_is_an_embedding_provider() -> None:
    assert issubclass(MiniLMEmbedder, EmbeddingProvider)
    assert MINILM_MODEL_ID == "all-MiniLM-L6-v2-384"


@pytest.mark.unit
def test_minilm_dimensions_are_384_without_loading_the_model() -> None:
    assert MiniLMEmbedder().dimensions == 384


@pytest.mark.unit
def test_minilm_embeds_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_fn(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[0.25] * 384 for _ in texts]

    embedder = MiniLMEmbedder(embed_fn=_fake_fn)
    out = embedder.embed(["a", "b"])
    assert calls == [["a", "b"]]
    assert len(out) == 2
    assert all(len(v) == 384 for v in out)


@pytest.mark.unit
def test_minilm_embed_output_is_json_serializable_python_floats() -> None:
    """chromadb's ONNXMiniLM_L6_V2 returns numpy.float32 arrays, which json.dumps

    cannot serialize. embed() must convert every element to a plain Python float
    before it reaches the Vectorize REST payload.
    """

    def _fake_fn(texts: list[str]) -> list[numpy.ndarray]:
        return [numpy.asarray([0.1, 0.2, 0.3], dtype=numpy.float32) for _ in texts]

    out = MiniLMEmbedder(embed_fn=_fake_fn).embed(["a", "b"])

    for vector in out:
        for x in vector:
            assert type(x) is float, f"expected python float, got {type(x)!r}"

    json.dumps(out)


@pytest.mark.unit
def test_minilm_empty_input_returns_empty_without_calling_the_model() -> None:
    def _boom(_texts: list[str]) -> list[list[float]]:
        raise AssertionError("must not be called for empty input")

    assert MiniLMEmbedder(embed_fn=_boom).embed([]) == []
