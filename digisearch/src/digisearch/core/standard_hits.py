"""Stable JSON shape for DigiSearch query hits across backends (Azure, Chroma, stub).

Hubs (DigiGraph), DigiChat, and MCP should only rely on the top-level keys documented in
``STANDARD_HIT_KEYS``. Backend-specific fields are lifted out of chunk metadata where
possible (e.g. Azure ``@search.highlights`` → ``highlights``).
"""

from __future__ import annotations

from typing import Any, Final

from digisearch.core.models import Result

# Provenance labels for ``SearchResponse.backend`` and ``QueryResponse.backend``.
BACKEND_AZURE_AI_SEARCH: Final[str] = "azure_ai_search"
BACKEND_CHROMA: Final[str] = "chroma"
BACKEND_STUB: Final[str] = "stub"

# Every hit dict from ``POST /query`` includes these keys (null/Omit only where noted).
STANDARD_HIT_KEYS: Final[tuple[str, ...]] = (
    "chunk_id",
    "doc_id",
    "rank",
    "score",
    "content",
    "content_length",
    "content_truncated",
    "metadata",
)

# Azure AI Search result well-known keys we normalize out of ``metadata``.
_AZURE_SEARCH_METADATA_PREFIX: Final[str] = "@search."


def normalize_query_hit(
    result: Result,
    *,
    content_preview_max: int = 500,
) -> dict[str, Any]:
    """Build one API/JSON hit from a :class:`Result`, independent of index backend.

    * ``content`` is a preview of at most *content_preview_max* characters (0 = full text).
    * Azure ``@search.*`` fields are removed from ``metadata`` and exposed as top-level
      keys when present (``highlights``, ``captions``, ``reranker_score``).
    """
    meta = dict(result.chunk.metadata or {})

    highlights = meta.pop("@search.highlights", None)
    captions = meta.pop("@search.captions", None)
    reranker_score = meta.pop("@search.reranker_score", None)
    meta.pop("@search.score", None)

    # Drop any other @search.* keys into a bucket so metadata stays portable.
    backend_passthrough: dict[str, Any] = {}
    for k in list(meta.keys()):
        if isinstance(k, str) and k.startswith(_AZURE_SEARCH_METADATA_PREFIX):
            backend_passthrough[k] = meta.pop(k)

    full_content = result.chunk.content or ""
    if content_preview_max <= 0:
        preview = full_content
        truncated = False
    else:
        truncated = len(full_content) > content_preview_max
        preview = full_content[:content_preview_max]

    out: dict[str, Any] = {
        "chunk_id": result.chunk.id,
        "doc_id": result.chunk.doc_id,
        "rank": result.rank,
        "score": float(result.score),
        "content": preview,
        "content_length": len(full_content),
        "content_truncated": truncated,
        "metadata": meta,
    }
    if highlights is not None:
        out["highlights"] = highlights
    if captions is not None:
        out["captions"] = captions
    if reranker_score is not None:
        try:
            out["reranker_score"] = float(reranker_score)
        except (TypeError, ValueError):
            out["reranker_score"] = reranker_score
    if backend_passthrough:
        out["backend_extras"] = backend_passthrough
    return out
