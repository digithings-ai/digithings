"""Search index router with pluggable backend registry.

Backends are tried in registration order. Azure/Chroma return :class:`SearchResponse`
(including empty lists) when they handle the query.
When ``DIGISEARCH_ALLOW_STUB=1`` (tests only), an in-memory substring index may run last.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from digisearch.core.models import Chunk, Query, SearchResponse
from digisearch.core.standard_hits import BACKEND_CHROMA, BACKEND_STUB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend registry
# Each entry is a callable (query, index_name) -> SearchResponse | None.
# Return None (or an empty-results response) to signal "not handled"; the
# router will try the next backend.
# ---------------------------------------------------------------------------
_BackendFn = Callable[[Query, str], "SearchResponse | None"]
_backends: list[_BackendFn] = []


def register_backend(fn: _BackendFn) -> _BackendFn:
    """Register a search backend. Backends are tried in registration order."""
    _backends.append(fn)
    return fn


def _clear_backends() -> None:
    """Remove all registered backends (test helper)."""
    _backends.clear()


# ---------------------------------------------------------------------------
# Built-in backends
# ---------------------------------------------------------------------------


@register_backend
def _azure_backend(query: Query, index_name: str) -> SearchResponse | None:
    """Azure AI Search backend. Active when AZURE_SEARCH_ENDPOINT is configured."""
    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, query_azure

        if not is_azure_configured():
            return None
        return query_azure(query, index_name)
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("Azure backend error: %s", exc)
        return None


@register_backend
def _chroma_backend(query: Query, index_name: str) -> SearchResponse | None:
    """ChromaDB backend. Active when CHROMA_PATH or CHROMA_HOST is set."""
    import os

    chroma_path = os.environ.get("CHROMA_PATH")
    chroma_host = os.environ.get("CHROMA_HOST")
    if not chroma_path and not chroma_host:
        return None
    try:
        from digisearch.indexes.backends.chroma import ChromaBackend

        backend = ChromaBackend(name=index_name, persist_path=chroma_path)
        results = backend.query(query)
        return SearchResponse(results=list(results), facets=None, backend=BACKEND_CHROMA)
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("Chroma backend error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# In-memory stub (last resort)
# ---------------------------------------------------------------------------

_stub_index: dict[str, list[Chunk]] = {"default": []}


def query_index(query: Query, index_name: str = "default") -> SearchResponse:
    """Route a query through registered backends; optional in-memory stub when explicitly enabled."""
    start = time.perf_counter()
    for backend in _backends:
        try:
            resp = backend(query, index_name)
        except Exception as exc:
            logger.warning(
                "Backend %s raised unexpectedly: %s",
                backend.__name__,
                exc,
                extra={
                    "operation": "query_index",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "backend": backend.__name__,
                    "index_name": index_name,
                },
            )
            resp = None
        if resp is not None:
            logger.info(
                "query dispatched",
                extra={
                    "operation": "query_index",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "ok",
                    "backend": getattr(resp, "backend", None) or backend.__name__,
                    "index_name": index_name,
                    "result_count": len(resp.results),
                    "top_k": query.top_k,
                },
            )
            return resp

    allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_stub:
        logger.info(
            "no backend handled query",
            extra={
                "operation": "query_index",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "index_name": index_name,
                "result_count": 0,
                "backend": None,
            },
        )
        return SearchResponse(results=[], facets=None, backend=None)

    chunks = _stub_index.get(index_name, [])
    if not chunks:
        return SearchResponse(results=[], facets=None, backend=BACKEND_STUB)

    logger.warning(
        "DIGISEARCH_ALLOW_STUB=1: in-memory substring index for '%s' (not for production).",
        index_name,
    )
    from digisearch.core.filter_apply import chunk_metadata_matches
    from digisearch.core.models import Result

    structured = None
    fd = query.filters or {}
    if isinstance(fd.get("structured"), list):
        structured = fd["structured"]
    text_lower = query.text.lower()
    out: list[Result] = []
    rank = 0
    for c in chunks:
        if text_lower not in c.content.lower():
            continue
        if structured and not chunk_metadata_matches(structured, c.metadata):
            continue
        rank += 1
        out.append(Result(chunk=c, score=0.9, rank=rank))
        if len(out) >= query.top_k:
            break
    return SearchResponse(results=out, facets=None, backend=BACKEND_STUB)


def add_chunks(index_name: str, chunks: list[Chunk]) -> None:
    """Add chunks to stub index."""
    _stub_index.setdefault(index_name, []).extend(chunks)


def get_stub_index() -> dict[str, list[Chunk]]:
    """Expose for tests."""
    return _stub_index
