"""Local MiniLM embedding provider backed by chromadb's bundled ONNX model.

Wraps the same model the Chroma backend embeds with internally, so an index built
here is directly comparable to a Chroma-built one. No new dependency: chromadb is
already required for the Chroma backend.
"""

from __future__ import annotations

from collections.abc import Callable

from digisearch.embedding.base import EmbeddingProvider

#: Recorded in vector metadata so an index cannot silently mix embedding models.
MINILM_MODEL_ID = "all-MiniLM-L6-v2-384"

#: all-MiniLM-L6-v2 output width.
MINILM_DIMENSIONS = 384

EmbedFn = Callable[[list[str]], list[list[float]]]


class MiniLMEmbedder(EmbeddingProvider):
    """all-MiniLM-L6-v2 (384-dim) via chromadb's bundled ONNX runtime."""

    #: Persisted on Chroma collection metadata (`embedding_model_id`).
    model_id: str = MINILM_MODEL_ID
    #: Logical migration version (`embedding_version`); bump when weights change.
    version: str = "1"

    def __init__(self, embed_fn: EmbedFn | None = None) -> None:
        self._embed_fn = embed_fn

    def _fn(self) -> EmbedFn:
        if self._embed_fn is None:
            from chromadb.utils import embedding_functions

            self._embed_fn = embedding_functions.ONNXMiniLM_L6_V2()
        return self._embed_fn

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(x) for x in vector] for vector in self._fn()(list(texts))]

    @property
    def dimensions(self) -> int:
        return MINILM_DIMENSIONS
