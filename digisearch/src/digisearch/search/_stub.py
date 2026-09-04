"""Search index router with pluggable backend registry (DESLOP-016 / SIMP-021).

Backends are tried in registration order: Azure, then Vectorize, then Chroma.
Vectorize/Azure/Chroma return :class:`SearchResponse` when configured. Vectorize is
the authoritative remote index once configured, so a failure there raises
``VectorizeBackendError`` (deliberately not a member of ``_BACKEND_ERRORS``) which
propagates out of :func:`query_index` instead of falling through to Chroma and
silently answering from a different corpus. Azure/Chroma failures still fall
through on error -- they are optional local backends, not authoritative ones.
In-memory stub runs only when ``DIGISEARCH_ALLOW_STUB=1`` (tests); stub branches
are intentional fail-closed test hooks, not dead code.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Callable

from digisearch.core.models import Chunk, Query, SearchResponse
from digisearch.core.standard_hits import BACKEND_CHROMA, BACKEND_STUB, BACKEND_VECTORIZE
from digisearch.indexes.backends.vectorize_errors import VectorizeBackendError

if TYPE_CHECKING:
    from digisearch.search.reranker import Reranker

logger = logging.getLogger(__name__)

_BackendFn = Callable[[Query, str], "SearchResponse | None"]
_backends: list[_BackendFn] = []

_BACKEND_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def _first_env(*names: str) -> str:
    """Return the first non-empty, stripped env var among ``names``.

    Canonical-first, legacy-fallback precedence (#2239 credential rename): Vectorize
    and D1 now share one Cloudflare account + token, so every credential read here
    tries ``CLOUDFLARE_ACCOUNT_ID``/``CLOUDFLARE_API_TOKEN`` (wrangler's own
    conventional names) first, then the legacy ``VECTORIZE_*``/``D1_*`` names — kept
    working so the deployed Worker's live secrets need no coordinated rotation before
    this ships (zero-downtime rename). Same shape as
    ``digivault.supabase_store._first_env``; duplicated locally rather than imported
    across the digisearch/digivault package boundary.
    """
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


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
def _vectorize_backend(query: Query, index_name: str) -> SearchResponse | None:
    """Cloudflare Vectorize backend. Active when CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN
    are set (falls back to the legacy VECTORIZE_*, then D1_*, names -- see `_first_env`).

    Vectorize is the authoritative remote index once configured: any failure here
    (HTTP error, application-level failure, missing dependency) is wrapped as
    `VectorizeBackendError` and re-raised. That type is deliberately absent from
    `_BACKEND_ERRORS`, so `query_index` cannot catch it and fall through to Chroma --
    a configured, failing remote index must never be answered from a different
    corpus with no error surfaced to the caller.

    The `VectorizeBackend` import itself lives inside the `try` (not just the query
    call) so an `ImportError` there -- a missing dependency, a broken transitive
    import -- is wrapped the same as every other failure. `VectorizeBackendError` is
    imported at module level from `vectorize_errors` (not from `vectorize` itself)
    precisely so it stays available to wrap that failure: a failed
    `from vectorize import VectorizeBackend, VectorizeBackendError` binds neither
    name, so referencing `VectorizeBackendError` in the `except` clause would raise
    `UnboundLocalError` instead if it were imported from the same failing module.
    """
    account_id = _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    api_token = _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    if not account_id or not api_token:
        return None

    try:
        from digisearch.indexes.backends.vectorize import VectorizeBackend

        backend = VectorizeBackend(
            index_name,
            account_id=account_id,
            api_token=api_token,
            embedding_provider=_resolved_embedding_provider(),
        )
        results = backend.query(query)
    except Exception as exc:
        # str(exc) carries the underlying failure detail (e.g. "vectorize query
        # failed (500): boom"); VectorizeBackend never puts the API token in a
        # raised message, so re-raising it here cannot leak one either.
        raise VectorizeBackendError(str(exc)) from exc
    return SearchResponse(results=list(results), facets=None, backend=BACKEND_VECTORIZE)


def _resolved_embedding_provider() -> object:
    """Same configured provider the ingest pipeline uses (raw, not cache-wrapped)."""
    from digisearch.embedding.factory import resolve_backend_embedding_provider

    return resolve_backend_embedding_provider()


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
            embedding_provider=_resolved_embedding_provider(),
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

# Process-scoped Reranker instances so BGE CrossEncoder is not reloaded per query.
_reranker_by_provider: dict[str, Reranker] = {}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _get_reranker(provider: str) -> Reranker:
    from digisearch.search.reranker import Reranker as _Reranker

    cached = _reranker_by_provider.get(provider)
    if cached is not None:
        return cached
    reranker = _Reranker(provider=provider)
    _reranker_by_provider[provider] = reranker
    return reranker


def _maybe_rerank(query: Query, resp: SearchResponse) -> SearchResponse:
    """Optional second-pass rerank gated by DIGISEARCH_RERANK_ENABLED (#2441).

    Off by default. ``Query.skip_rerank`` suppresses even when the flag is on
    (fetch_all pagination shares this call chain and must not reorder pages).
    """
    if query.skip_rerank or not _env_truthy("DIGISEARCH_RERANK_ENABLED"):
        return resp
    if not resp.results:
        return resp

    provider = (os.environ.get("DIGISEARCH_RERANK_PROVIDER") or "bge").strip().lower() or "bge"
    reranker = _get_reranker(provider)
    resp.results = reranker.rerank(query.text, resp.results, top_n=query.top_k)
    return resp


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
            return _maybe_rerank(query, resp)

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
        return _maybe_rerank(query, SearchResponse(results=[], facets=None, backend=None))

    chunks = _stub_index.get(index_name, [])
    if not chunks:
        return _maybe_rerank(query, SearchResponse(results=[], facets=None, backend=BACKEND_STUB))

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
    return _maybe_rerank(query, SearchResponse(results=out, facets=None, backend=BACKEND_STUB))


def _stub_add_chunks(index_name: str, chunks: list[Chunk]) -> None:
    """Add chunks to in-memory stub index (tests / DIGISEARCH_ALLOW_STUB only)."""
    _stub_index.setdefault(index_name, []).extend(chunks)


def route_add_chunks(index_name: str, chunks: list[Chunk]) -> str | None:
    """Route ingest to Vectorize when configured, else Chroma; stub only when
    DIGISEARCH_ALLOW_STUB=1.

    Returns backend id (``vectorize`` / ``chroma`` / ``stub``) or raises when no
    backend is available.
    """
    if not chunks:
        return None

    vectorize_account = _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    vectorize_token = _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    if vectorize_account and vectorize_token:
        from digisearch.indexes.backends.vectorize import VectorizeBackend

        backend = VectorizeBackend(
            index_name,
            account_id=vectorize_account,
            api_token=vectorize_token,
            embedding_provider=_resolved_embedding_provider(),
        )
        backend.add(chunks)
        return BACKEND_VECTORIZE

    chroma_path = os.environ.get("CHROMA_PATH")
    chroma_host = os.environ.get("CHROMA_HOST")
    if chroma_host and not chroma_path:
        try:
            from digisearch.indexes.backends.chroma import ChromaBackend

            port_raw = os.environ.get("CHROMA_PORT", "8000").strip() or "8000"
            backend = ChromaBackend(
                name=index_name,
                embedding_provider=_resolved_embedding_provider(),
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
                embedding_provider=_resolved_embedding_provider(),
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
    """Add chunks via :func:`route_add_chunks` (Vectorize, Chroma, or stub)."""
    route_add_chunks(index_name, chunks)


def get_stub_index() -> dict[str, list[Chunk]]:
    """Expose for tests."""
    return _stub_index
