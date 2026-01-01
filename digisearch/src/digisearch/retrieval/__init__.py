"""Pluggable retrieval backends (``RetrievalBackend`` protocol)."""

from __future__ import annotations

from digisearch.retrieval.backend import RetrievalBackend, RetrievalResult
from digisearch.retrieval.lightrag import LightRAGBackend
from digisearch.retrieval.pgvector import PgvectorBackend
from digisearch.retrieval.registry import (
    BACKENDS,
    DEFAULT_BACKEND_NAME,
    ENV_VAR,
    clear_retrieval_backend_cache,
    get_retrieval_backend,
    resolve_retrieval_backend_name,
)

__all__ = [
    "BACKENDS",
    "DEFAULT_BACKEND_NAME",
    "ENV_VAR",
    "LightRAGBackend",
    "PgvectorBackend",
    "RetrievalBackend",
    "RetrievalResult",
    "clear_retrieval_backend_cache",
    "get_retrieval_backend",
    "resolve_retrieval_backend_name",
]
