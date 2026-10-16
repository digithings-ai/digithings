"""digisearch embedding providers and pipeline factory."""

from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.factory import (
    EmbeddingConfigError,
    effective_query_mode,
    normalize_query_mode,
    resolve_embedding_pipeline,
)

__all__ = [
    "EmbeddingConfigError",
    "EmbeddingProvider",
    "effective_query_mode",
    "normalize_query_mode",
    "resolve_embedding_pipeline",
]
