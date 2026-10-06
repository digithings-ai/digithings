"""Search index router with pluggable backend registry (DESLOP-016 / SIMP-021).

Backends are tried in registration order: Azure, then Vectorize, then Chroma.
Vectorize/Azure/Chroma return :class:`SearchResponse` when configured. A configured
backend that fails to serve a query raises a ``SearchBackendError`` (deliberately not
a member of ``_BACKEND_ERRORS``) which propagates out of :func:`query_index` instead
of falling through to the next backend and silently answering from a different corpus
(#3909). Vectorize raises its own ``VectorizeBackendError`` for the same reason.
"Not configured"/"dependency missing" paths still return ``None`` so the router can
continue to the next backend.
In-memory stub runs only when ``DIGISEARCH_ALLOW_STUB=1`` (tests); stub branches
are intentional fail-closed test hooks, not dead code.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Callable

from digisearch.core.models import Chunk, Query, Result, SearchResponse
from digisearch.core.standard_hits import BACKEND_CHROMA, BACKEND_STUB, BACKEND_VECTORIZE
from digisearch.indexes.backends.backend_errors import CorpusNotSeededError, SearchBackendError
from digisearch.indexes.backends.vectorize_errors import VectorizeBackendError

if TYPE_CHECKING:
    from digisearch.search.reranker import Reranker

logger = logging.getLogger(__name__)

_BackendFn = Callable[[Query, str], "SearchResponse | None"]
_backends: list[_BackendFn] = []

_BACKEND_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)

#: Comma-separated index names the current boot's seed failed to populate, set by
#: the stack's ``start_digisearch.sh``. Empty/absent means seeded, so this guard
#: is inert everywhere but that deployment (#5045).
UNSEEDED_INDEXES_ENV = "DIGISEARCH_UNSEEDED_INDEXES"


def unseeded_indexes() -> frozenset[str]:
    """Indexes this boot's seed could not populate.

    Read per call rather than cached at import: tests set it around individual
    requests, and a container's value is fixed for its whole life anyway.
    """
    raw = os.environ.get(UNSEEDED_INDEXES_ENV, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def guard_unseeded(index_names: list[str]) -> None:
    """Refuse to serve from a collection this boot's seed never populated.

    Raises :class:`CorpusNotSeededError` naming the offending indexes. Partial
    failure only takes down the indexes that actually failed.
    """
    missing = sorted(set(index_names) & unseeded_indexes())
    if missing:
        raise CorpusNotSeededError(missing)


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


_LEGACY_WARNED: set[str] = set()


def _warn_legacy_env(canonical: str, *legacy: str) -> None:
    if os.environ.get(canonical, "").strip():
        return
    for name in legacy:
        if os.environ.get(name, "").strip():
            if name not in _LEGACY_WARNED:
                _LEGACY_WARNED.add(name)
                logger.warning("Using deprecated env var %s; set %s instead", name, canonical)
            return


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
        raise SearchBackendError(f"azure backend error: {exc}") from exc


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
    _warn_legacy_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    _warn_legacy_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
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
        raise SearchBackendError(f"chroma backend error: {exc}") from exc


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
    # Reranker providers rebuild Result objects (chunk/score/rank only), which
    # would silently drop #5045 index provenance. Snapshot it by chunk id and
    # restore after rerank; observability only — order and scores come from the
    # reranker untouched. (source_doc loss on this path is pre-existing.)
    provenance = {r.chunk.id: r.index_names for r in resp.results if r.index_names}
    resp.results = reranker.rerank(query.text, resp.results, top_n=query.top_k)
    for result in resp.results:
        if not result.index_names:
            result.index_names = provenance.get(result.chunk.id)
    return resp


def _rrf_merge_results(
    results_list: list[tuple[str, list[Result]]], top_k: int | None, k: int = 60
) -> list[Result]:
    """Merge per-index result lists with RRF (multi-index fan-out).

    Each entry is ``(index_name, results)``. Merged hits carry provenance in
    ``Result.index_names``: every contributing index name, in fan-out order,
    deduped — a chunk present in two indexes records both (#5045). The index
    name on a result's own ``index_names`` (stamped by ``_query_single_index``)
    wins over the tuple name, which is the fallback for direct callers.

    Rank falls back to position when a backend leaves ``Result.rank`` unset.
    """
    scored: dict[str, list] = {}
    for index_name, results in results_list:
        for position, result in enumerate(results):
            rank = result.rank if result.rank is not None else position + 1
            names = list(result.index_names) if result.index_names else [index_name]
            entry = scored.get(result.chunk.id)
            if entry is None:
                scored[result.chunk.id] = [result, 1.0 / (k + rank), names]
            else:
                entry[1] += 1.0 / (k + rank)
                entry[2].extend(name for name in names if name not in entry[2])
    ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
    merged = [
        Result(
            chunk=result.chunk,
            score=score,
            source_doc=result.source_doc,
            rank=index + 1,
            index_names=names,
        )
        for index, (result, score, names) in enumerate(ranked)
    ]
    return merged[:top_k] if top_k else merged


def _with_index_name(resp: SearchResponse, index_name: str) -> SearchResponse:
    """Stamp index provenance on a single-index response (#5045, observability only).

    Sets ``SearchResponse.index_names`` and, on every hit that does not already
    carry provenance, ``Result.index_names = [index_name]``. The index name is the
    Chroma collection name (strictly 1:1), so it is the correct corpus label.
    Mutates and returns ``resp``; touches no field that affects scoring or order.
    """
    for result in resp.results:
        if not result.index_names:
            result.index_names = [index_name]
    resp.index_names = [index_name]
    return resp


def _query_single_index(query: Query, index_name: str) -> SearchResponse:
    """Route one index name through registered backends (no rerank; caller applies it)."""
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
            return _with_index_name(resp, index_name)

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
        return _with_index_name(SearchResponse(results=[], facets=None, backend=None), index_name)

    chunks = _stub_index.get(index_name, [])
    if not chunks:
        return _with_index_name(
            SearchResponse(results=[], facets=None, backend=BACKEND_STUB), index_name
        )

    logger.warning(
        "DIGISEARCH_ALLOW_STUB=1: in-memory substring index for '%s' (not for production).",
        index_name,
    )
    from digisearch.core.filter_apply import chunk_metadata_matches
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
    return _with_index_name(
        SearchResponse(results=out, facets=None, backend=BACKEND_STUB), index_name
    )


def query_index(query: Query, index_name: str = "default") -> SearchResponse:
    """Route a query through registered backends; optional in-memory stub when explicitly enabled.

    A comma-separated ``index_name`` (e.g. ``"occ_help,occ_tickets"``) fans
    out to each index and merges with RRF, so one tenant can serve docs plus
    tickets without routing changes upstream. Backend errors still propagate
    per index (fail-closed, never answered from a different corpus).
    """
    names = [name.strip() for name in str(index_name or "default").split(",")]
    names = [name for name in names if name] or ["default"]
    guard_unseeded(names)
    if len(names) == 1:
        return _maybe_rerank(query, _query_single_index(query, names[0]))
    logger.info(
        "fan-out query",
        extra={
            "operation": "query_index",
            "outcome": "ok",
            "index_names": names,
            "top_k": query.top_k,
        },
    )
    responses = [_query_single_index(query, name) for name in names]
    merged = _rrf_merge_results(
        [(name, response.results) for name, response in zip(names, responses)],
        top_k=query.top_k,
    )
    return _maybe_rerank(
        query,
        SearchResponse(results=merged, facets=None, backend="multi", index_names=names),
    )


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

    _warn_legacy_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    _warn_legacy_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
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
