"""Search index router with pluggable backend registry.

Backends are tried in registration order; the first one that returns results wins.
Out-of-the-box backends: Azure AI Search, ChromaDB, in-memory stub.
Add custom backends via :func:`register_backend`.
"""

from __future__ import annotations

import logging
from typing import Callable

from digisearch.core.models import Chunk, Query, SearchResponse

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
        response = query_azure(query, index_name)
        return response if response.results else None
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
        return SearchResponse(results=results, facets=None) if results else None
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
    """Route a query through registered backends, falling back to in-memory stub.

    WARNING: The in-memory stub uses substring matching with a hardcoded score of 0.9.
    It is only suitable for development/testing. Configure a real backend (Azure or Chroma)
    for production use.
    """
    for backend in _backends:
        try:
            resp = backend(query, index_name)
        except Exception as exc:
            logger.warning("Backend %s raised unexpectedly: %s", backend.__name__, exc)
            resp = None
        if resp is not None and resp.results:
            return resp

    # Stub fallback
    chunks = _stub_index.get(index_name, [])
    if not chunks:
        return SearchResponse(results=[], facets=None)

    logger.warning(
        "No real search backend configured for index '%s' — falling back to in-memory stub "
        "(substring match only, fixed score=0.9). Results are NOT semantically ranked. "
        "Configure AZURE_SEARCH_* or CHROMA_PATH/CHROMA_HOST for production use.",
        index_name,
    )
    from digisearch.core.models import Result

    text_lower = query.text.lower()
    out: list[Result] = []
    for i, c in enumerate(chunks):
        if text_lower in c.content.lower():
            out.append(Result(chunk=c, score=0.9, rank=i + 1))
    return SearchResponse(results=out[: query.top_k], facets=None)


def add_chunks(index_name: str, chunks: list[Chunk]) -> None:
    """Add chunks to stub index."""
    _stub_index.setdefault(index_name, []).extend(chunks)


def get_stub_index() -> dict[str, list[Chunk]]:
    """Expose for tests."""
    return _stub_index
