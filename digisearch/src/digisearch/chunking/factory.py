"""Select chunker backends via ``DIGISEARCH_CHUNKER`` or per-index config."""

from __future__ import annotations

import os
from typing import Any  # score:allow untyped any — per-index YAML config payloads

from digisearch.chunking.backend import ChunkerBackend
from digisearch.chunking.chonkie_semantic import ChonkieSemanticChunker
from digisearch.chunking.chonkie_token import ChonkieTokenChunker
from digisearch.chunking.document_adapter import BackendDocumentChunker
from digisearch.ingestion.chunkers.base import Chunker

# Default for long-form document ingestion (SEC filings, research, transcripts).
DEFAULT_CHUNKER_NAME = "semantic"

_ENV_VAR = "DIGISEARCH_CHUNKER"

_SEMANTIC_ALIASES = frozenset({"semantic", "chonkie", "chonkie_semantic", "chonkie-semantic"})
_TOKEN_ALIASES = frozenset({"token", "chonkie_token", "chonkie-token"})
# Legacy inline chunkers still selectable for rollbacks / characterization.
_LEGACY_RECURSIVE = frozenset({"recursive"})
_LEGACY_FIXED = frozenset({"fixed"})


def resolve_chunker_name(
    name: str | None = None,
    *,
    index_config: dict[str, Any] | None = None,
) -> str:
    """Resolve chunker key: explicit *name* → index ``chunker`` → env → default."""
    if name and str(name).strip():
        return str(name).strip().lower()
    if index_config:
        cfg_name = index_config.get("chunker")
        if cfg_name and str(cfg_name).strip():
            return str(cfg_name).strip().lower()
    env = os.environ.get(_ENV_VAR, "").strip().lower()
    if env:
        return env
    return DEFAULT_CHUNKER_NAME


def get_chunker_backend(
    name: str | None = None,
    *,
    index_config: dict[str, Any] | None = None,
) -> ChunkerBackend:
    """Return a :class:`ChunkerBackend` selected by name / env / index config.

    Supported values (case-insensitive):

    * ``semantic`` (default) — :class:`ChonkieSemanticChunker`
    * ``token`` — :class:`ChonkieTokenChunker`
    """
    key = resolve_chunker_name(name, index_config=index_config)
    if key in _SEMANTIC_ALIASES:
        return ChonkieSemanticChunker()
    if key in _TOKEN_ALIASES:
        return ChonkieTokenChunker()
    raise ValueError(
        f"Unknown DIGISEARCH_CHUNKER={key!r}. "
        f"Use one of: semantic, token (aliases: chonkie_semantic, chonkie_token)."
    )


def get_document_chunker(
    name: str | None = None,
    *,
    index_config: dict[str, Any] | None = None,
) -> Chunker:
    """Document-level chunker for a single text body (no segment wrapping).

    Resolves Chonkie backends and legacy ``recursive`` / ``fixed`` names.
    """
    key = resolve_chunker_name(name, index_config=index_config)
    if key in _LEGACY_RECURSIVE:
        from digisearch.ingestion.chunkers.recursive import RecursiveChunker

        return RecursiveChunker()
    if key in _LEGACY_FIXED:
        from digisearch.ingestion.chunkers.fixed import FixedSizeChunker

        return FixedSizeChunker(chunk_size=512)
    return BackendDocumentChunker(get_chunker_backend(key))


def get_ingest_chunker(
    name: str | None = None,
    *,
    index_config: dict[str, Any] | None = None,
) -> Chunker:
    """Default ingest pipeline chunker: segment-aware wrapper over the selected backend.

    Documents with structural ``segments`` stay segment-bounded; oversized segments
    and unstructured docs use the selected inner chunker (Chonkie semantic by default).
    """
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    inner = get_document_chunker(name, index_config=index_config)
    return SegmentAwareChunker(inner=inner)
