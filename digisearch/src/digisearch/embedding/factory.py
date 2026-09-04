"""Resolve the documented EmbeddingCache → BatchEmbedder → EmbeddingProvider stack.

Configuration sources (highest precedence first):

1. ``DIGISEARCH_EMBEDDING_PROVIDER`` (+ optional ``DIGISEARCH_EMBEDDING_MODEL``)
2. Non-empty ``embedding:`` block in ``DigiSearchConfig`` (``DIGISEARCH_CONFIG_PATH``)
3. Default ``minilm`` when a vector backend (Chroma / Vectorize) is configured

``DIGISEARCH_EMBED=0`` disables the pipeline-level embed step (backends may still
embed via their own injected providers). Explicit provider config that cannot be
loaded raises :class:`EmbeddingConfigError` — never a silent no-op.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from digisearch.core.config import DigiSearchConfig
from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.batch import BatchEmbedder
from digisearch.embedding.cache import EmbeddingCache

logger = logging.getLogger(__name__)

QueryMode = Literal["keyword", "vector", "hybrid"]
QUERY_MODES: frozenset[str] = frozenset({"keyword", "vector", "hybrid"})

_VECTOR_ONLY_BACKENDS = frozenset({"chroma", "vectorize", "stub"})


class EmbeddingConfigError(RuntimeError):
    """Embed configuration is present but cannot be activated."""


def normalize_query_mode(mode: str | None) -> QueryMode:
    """Validate and normalize ``query.mode``.

    Raises
    ------
    ValueError
        When *mode* is not one of ``keyword`` | ``vector`` | ``hybrid``.
    """
    raw = (mode or "hybrid").strip().lower()
    if raw not in QUERY_MODES:
        allowed = ", ".join(sorted(QUERY_MODES))
        raise ValueError(f"invalid query.mode {mode!r}; expected one of: {allowed}")
    return raw  # type: ignore[return-value]


def effective_query_mode(requested: str, backend: str | None) -> QueryMode:
    """Return the mode a backend actually executes.

    Chroma, Vectorize, and the in-memory stub are ANN / substring only — they
    coerce ``keyword`` and ``hybrid`` to ``vector`` (documented in ARCHITECTURE).
    Azure keeps the requested mode (text BM25 today; vector fields are out of scope).
    """
    mode = normalize_query_mode(requested)
    be = (backend or "").strip().lower()
    if be in _VECTOR_ONLY_BACKENDS and mode != "vector":
        return "vector"
    return mode


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def vector_backend_configured() -> bool:
    """True when Chroma or Vectorize credentials/paths are present."""
    if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"):
        return True
    account = _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    token = _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    return bool(account and token)


def _provider_name_and_model(config: DigiSearchConfig | None) -> tuple[str | None, str | None]:
    """Return (provider_name, model) from env / config, or (None, None) if unset."""
    env_provider = os.environ.get("DIGISEARCH_EMBEDDING_PROVIDER", "").strip().lower()
    env_model = os.environ.get("DIGISEARCH_EMBEDDING_MODEL", "").strip() or None
    if env_provider:
        return env_provider, env_model

    cfg = config or DigiSearchConfig.from_env()
    embedding = cfg.embedding or {}
    if not embedding:
        return None, None
    name = str(embedding.get("provider") or "").strip().lower() or None
    model = str(embedding.get("model") or "").strip() or None
    return name, model


def _build_raw_provider(name: str, model: str | None) -> EmbeddingProvider:
    if name in ("minilm", "local", "onnx"):
        from digisearch.embedding.providers.minilm import MiniLMEmbedder

        return MiniLMEmbedder()
    if name in ("openai", "oai"):
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise EmbeddingConfigError(
                "embedding provider 'openai' is configured but OPENAI_API_KEY is unset; "
                "set the key or switch DIGISEARCH_EMBEDDING_PROVIDER / config embedding.provider"
            )
        from digisearch.embedding.providers.openai import OpenAIEmbedder

        return OpenAIEmbedder(model=model or "text-embedding-3-small", api_key=api_key)
    raise EmbeddingConfigError(
        f"unknown embedding provider {name!r}; expected minilm or openai "
        "(new providers are out of scope for the wire-embed task)"
    )


def wrap_embedding_pipeline(
    provider: EmbeddingProvider,
    *,
    batch_size: int | None = None,
    use_cache: bool | None = None,
    cache_path: str | None = None,
) -> EmbeddingProvider:
    """Wrap *provider* as EmbeddingCache → BatchEmbedder → provider."""
    size = batch_size
    if size is None:
        raw = os.environ.get("DIGISEARCH_EMBED_BATCH_SIZE", "").strip()
        if raw:
            try:
                size = int(raw)
            except ValueError as exc:
                raise EmbeddingConfigError(
                    f"DIGISEARCH_EMBED_BATCH_SIZE must be an integer, got {raw!r}"
                ) from exc
        else:
            size = 100
    if size < 1:
        raise EmbeddingConfigError(f"DIGISEARCH_EMBED_BATCH_SIZE must be >= 1, got {size}")
    batched: EmbeddingProvider = BatchEmbedder(provider, batch_size=size)
    cache_on = _env_truthy("DIGISEARCH_EMBED_CACHE", "1") if use_cache is None else use_cache
    if not cache_on:
        return batched
    path = cache_path or os.environ.get("DIGISEARCH_CACHE_PATH")
    return EmbeddingCache(batched, db_path=path)


def unwrap_embedding_provider(provider: EmbeddingProvider) -> EmbeddingProvider:
    """Return the innermost provider under BatchEmbedder / EmbeddingCache wrappers."""
    current: EmbeddingProvider = provider
    seen: set[int] = set()
    while True:
        ident = id(current)
        if ident in seen:
            return current
        seen.add(ident)
        inner = getattr(current, "provider", None)
        if not isinstance(inner, EmbeddingProvider) or inner is current:
            return current
        current = inner


def resolve_backend_embedding_provider(
    config: DigiSearchConfig | None = None,
) -> EmbeddingProvider:
    """Raw EmbeddingProvider for Chroma/Vectorize construction (no cache wrap).

    Always returns a provider (default MiniLM). Uses the same env/config resolution
    as the ingest pipeline so query-time and ingest-time models stay aligned.
    """
    name, model = _provider_name_and_model(config)
    if name is None:
        name = "minilm"
    try:
        return _build_raw_provider(name, model)
    except EmbeddingConfigError:
        raise
    except Exception as exc:
        raise EmbeddingConfigError(f"failed to load embedding provider {name!r}: {exc}") from exc


def resolve_embedding_pipeline(
    config: DigiSearchConfig | None = None,
    *,
    require: bool = False,
) -> EmbeddingProvider | None:
    """Build the configured embed stack, or ``None`` when embed is intentionally off.

    Parameters
    ----------
    require:
        When True, raise if no provider can be resolved (callers that must embed).
    """
    # DIGISEARCH_EMBED defaults to on when unset; only an explicit 0/false/no disables.
    embed_env = os.environ.get("DIGISEARCH_EMBED")
    if embed_env is not None and embed_env.strip() != "" and not _env_truthy("DIGISEARCH_EMBED"):
        if require:
            raise EmbeddingConfigError("DIGISEARCH_EMBED=0 but an embedding provider is required")
        logger.info("DIGISEARCH_EMBED disabled; skipping pipeline-level embed")
        return None

    name, model = _provider_name_and_model(config)
    explicit = name is not None
    if name is None:
        if vector_backend_configured() or require:
            name = "minilm"
        else:
            return None

    try:
        raw = _build_raw_provider(name, model)
    except EmbeddingConfigError:
        raise
    except Exception as exc:  # ImportError / runtime from provider ctor
        raise EmbeddingConfigError(f"failed to load embedding provider {name!r}: {exc}") from exc

    pipeline = wrap_embedding_pipeline(raw)
    logger.info(
        "embed pipeline ready",
        extra={
            "operation": "resolve_embedding_pipeline",
            "provider": name,
            "explicit_config": explicit,
            "cached": isinstance(pipeline, EmbeddingCache),
        },
    )
    return pipeline


__all__ = [
    "QUERY_MODES",
    "EmbeddingConfigError",
    "QueryMode",
    "effective_query_mode",
    "normalize_query_mode",
    "resolve_backend_embedding_provider",
    "resolve_embedding_pipeline",
    "unwrap_embedding_provider",
    "vector_backend_configured",
    "wrap_embedding_pipeline",
]
