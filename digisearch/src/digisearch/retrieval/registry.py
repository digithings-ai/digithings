"""Registry + factory for :class:`~digisearch.retrieval.backend.RetrievalBackend`.

Selection is config-only via ``DIGISEARCH_RETRIEVAL_BACKEND`` (default:
``pgvector``). Callers never branch on backend name.
"""

from __future__ import annotations

import os
from typing import Any

from digisearch.retrieval.backend import RetrievalBackend
from digisearch.retrieval.lightrag import LightRAGBackend
from digisearch.retrieval.pgvector import PgvectorBackend

ENV_VAR = "DIGISEARCH_RETRIEVAL_BACKEND"
DEFAULT_BACKEND_NAME = "pgvector"

# Name → constructor. Values are callables returning a RetrievalBackend.
BACKENDS: dict[str, type] = {
    "pgvector": PgvectorBackend,
    "lightrag": LightRAGBackend,
}

_ALIASES: dict[str, str] = {
    "pg": "pgvector",
    "postgres": "pgvector",
    "postgresql": "pgvector",
    "light-rag": "lightrag",
    "light_rag": "lightrag",
}

_cache: dict[str, RetrievalBackend] = {}


def clear_retrieval_backend_cache() -> None:
    """Drop cached backends (tests that swap env / constructors)."""
    _cache.clear()


def resolve_retrieval_backend_name(name: str | None = None) -> str:
    """Resolve backend key: explicit *name* → env → ``pgvector`` default."""
    raw = (name or os.environ.get(ENV_VAR, "") or DEFAULT_BACKEND_NAME).strip().lower()
    return _ALIASES.get(raw, raw)


def get_retrieval_backend(
    name: str | None = None,
    *,
    use_cache: bool = True,
    **kwargs: Any,
) -> RetrievalBackend:
    """Return a :class:`RetrievalBackend` selected by name / env.

    Supported values (case-insensitive):

    * ``pgvector`` (default) — :class:`~digisearch.retrieval.pgvector.PgvectorBackend`
    * ``lightrag`` — :class:`~digisearch.retrieval.lightrag.LightRAGBackend`
    """
    key = resolve_retrieval_backend_name(name)
    if use_cache and not kwargs:
        cached = _cache.get(key)
        if cached is not None:
            return cached
    try:
        cls = BACKENDS[key]
    except KeyError as exc:
        known = ", ".join(sorted(BACKENDS))
        raise ValueError(
            f"Unknown DIGISEARCH_RETRIEVAL_BACKEND={key!r}. Use one of: {known}."
        ) from exc
    backend: RetrievalBackend = cls(**kwargs)  # type: ignore[call-arg]
    if use_cache and not kwargs:
        _cache[key] = backend
    return backend
