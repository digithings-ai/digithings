"""Search index router with pluggable backend registry (DESLOP-016 / SIMP-021).

Backends are tried in registration order. Azure/Chroma return :class:`SearchResponse`
when configured. In-memory stub runs only when ``DIGISEARCH_ALLOW_STUB=1`` (tests);
stub branches are intentional fail-closed test hooks, not dead code.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from digisearch.core.models import Chunk, Query, SearchResponse
from digisearch.core.standard_hits import BACKEND_CHROMA, BACKEND_STUB

logger = logging.getLogger(__name__)

_BackendFn = Callable[[Query, str], "SearchResponse | None"]
_backends: list[_BackendFn] = []

_BACKEND_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def register_backend(fn: _BackendFn) -> _BackendFn:
    """Register a search backend. Backends are tried in registration order."""
    _backends.append(fn)
    return fn


def _clear_backends() -> None:
    """Remove all registered backends (test helper)."""
    _backends.clear()


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
    except _BACKEND_ERRORS as exc:
        logger.warning("Azure backend error: %s", exc)
        return None


@register_backend
def _chroma_backend(query: Query, index_name: str) -> SearchResponse | None:
    """ChromaDB backend. Active when CHROMA_PATH or CHROMA_HOST is set."""
    chroma_path = os.environ.get("CHROMA_PATH")
    chroma_host = os.environ.get("CHROMA_HOST")
    if not chroma_path and not chroma_host:
        return None
    try:
        from digisearch.indexes.backends.chroma import ChromaBackend

        port_raw = os.environ.get("CHROMA_PORT", "8000").strip() or "8000"
        backend = ChromaBackend(
            name=index_name,
            persist_path=chroma_path,
            chroma_host=chroma_host,
            chroma_port=int(port_raw),
        )
        results = backend.query(query)
        return SearchResponse(results=list(results), facets=None, backend=BACKEND_CHROMA)
    except ImportError:
        return None
    except _BACKEND_ERRORS as exc:
        logger.warning("Chroma backend error: %s", exc)
        return None


_stub_index: dict[str, list[Chunk]] = {"default": []}


def query_index(query: Query, index_name: str = "default") -> SearchResponse:
    """Route a query through registered backends; optional in-memory stub when explicitly enabled."""
    start = time.perf_counter()
    for backend in _backends:
        try:
            resp = backend(query, index_name)
        except _BACKEND_ERRORS as exc:
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
    from digisearch.core.workspace_filter import chunk_matches_workspace

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
        if not chunk_matches_workspace(c.metadata, query.workspace_id):
            continue
        rank += 1
        out.append(Result(chunk=c, score=0.9, rank=rank))
        if len(out) >= query.top_k:
            break
    return SearchResponse(results=out, facets=None, backend=BACKEND_STUB)


def _stub_add_chunks(index_name: str, chunks: list[Chunk]) -> None:
    """Add chunks to in-memory stub index (tests / DIGISEARCH_ALLOW_STUB only)."""
    _stub_index.setdefault(index_name, []).extend(chunks)


def route_add_chunks(index_name: str, chunks: list[Chunk]) -> str | None:
    """Route ingest to Chroma when configured; stub only when DIGISEARCH_ALLOW_STUB=1.

    Returns backend id (``chroma`` / ``stub``) or raises when no backend is available.
    """
    if not chunks:
        return None

    chroma_path = os.environ.get("CHROMA_PATH")
    chroma_host = os.environ.get("CHROMA_HOST")
    if chroma_host and not chroma_path:
        try:
            from digisearch.indexes.backends.chroma import ChromaBackend

            port_raw = os.environ.get("CHROMA_PORT", "8000").strip() or "8000"
            backend = ChromaBackend(
                name=index_name,
                chroma_host=chroma_host,
                chroma_port=int(port_raw),
            )
            backend.add(chunks)
            return BACKEND_CHROMA
        except ImportError as exc:
            raise RuntimeError("Chroma backend unavailable; install digisearch[chroma]") from exc
        except _BACKEND_ERRORS as exc:
            logger.error("Chroma HTTP ingest failed for index %s: %s", index_name, exc)
            raise
    if chroma_path:
        try:
            from digisearch.indexes.backends.chroma import ChromaBackend

            port_raw = os.environ.get("CHROMA_PORT", "8000").strip() or "8000"
            backend = ChromaBackend(
                name=index_name,
                persist_path=chroma_path,
                chroma_host=chroma_host,
                chroma_port=int(port_raw),
            )
            backend.add(chunks)
            return BACKEND_CHROMA
        except ImportError as exc:
            raise RuntimeError("Chroma backend unavailable; install digisearch[chroma]") from exc
        except _BACKEND_ERRORS as exc:
            logger.error("Chroma ingest failed for index %s: %s", index_name, exc)
            raise

    allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_stub:
        _stub_add_chunks(index_name, chunks)
        return BACKEND_STUB

    raise RuntimeError(
        "No ingest backend configured: set CHROMA_PATH/CHROMA_HOST or DIGISEARCH_ALLOW_STUB=1 (tests)"
    )


def add_chunks(index_name: str, chunks: list[Chunk]) -> None:
    """Add chunks via :func:`route_add_chunks` (Chroma or stub)."""
    route_add_chunks(index_name, chunks)


def get_stub_index() -> dict[str, list[Chunk]]:
    """Expose for tests."""
    return _stub_index
