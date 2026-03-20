"""DigiSearch HTTP API for DigiGraph and DigiFlow. Phase 1: health, query, ingest stubs."""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from typing import Any

from digisearch.core.models import Chunk, Query
from digisearch.search._stub import add_chunks, query_index

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _subst_env(s: str) -> str:
    """Expand ${VAR} or $VAR patterns in *s* using current environment variables."""
    import re
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: os.environ.get(m.group(1) or m.group(2), ""), s)


def _allowed_origins() -> list[str]:
    """Read DIGI_ALLOWED_ORIGINS (comma-separated). Defaults to localhost origins when unset.

    Each origin may contain ``${VAR}`` references that are expanded from the environment,
    e.g. ``http://${API_HOST}:3000``.
    """
    raw = os.environ.get("DIGI_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://localhost:8000", "http://localhost:11434"]
    return [_subst_env(o.strip()) for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="DigiSearch",
    description="RAG, document search for Digi ecosystem. MCP tools for DigiGraph/DigiFlow.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warn_if_stub_backend() -> None:
    """Warn at startup if no real search backend is configured."""
    from digisearch.indexes.backends import azure_search as _az

    azure_ok = False
    try:
        azure_ok = _az.is_azure_configured()
    except Exception:
        pass
    chroma_ok = bool(os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"))
    if not azure_ok and not chroma_ok:
        logger.warning(
            "DigiSearch: no real search backend configured (Azure or Chroma). "
            "All queries will use the in-memory stub (substring match, score=0.9). "
            "Set AZURE_SEARCH_ENDPOINT/AZURE_SEARCH_API_KEY or CHROMA_PATH for production use."
        )


import time as _time
from collections import deque as _deque
from threading import Lock as _Lock

_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/query": (10, 60),
    "/ingest": (30, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health"}


def _rl_check(request: Request, max_req: int, window: int) -> JSONResponse | None:
    if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return None
    xff = request.headers.get("X-Forwarded-For")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    if ip == "testclient":
        return None
    now = _time.monotonic()
    cutoff = now - window
    with _rl_lock:
        if ip not in _rl_windows:
            _rl_windows[ip] = _deque()
        q = _rl_windows[ip]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_req:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {max_req} requests per {window}s."},
                headers={"Retry-After": str(window)},
            )
        q.append(now)
    return None


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP rate limiting. /query: 10/min; /ingest: 30/min; others: 30/min."""
    path = request.url.path
    if path not in _UNLIMITED_PATHS:
        max_req, window = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        result = _rl_check(request, max_req, window)
        if result is not None:
            return result
    return await call_next(request)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Require Authorization: Bearer <DIGI_API_KEY> when DIGI_API_KEY env var is set. Health endpoint is exempt."""
    api_key = os.environ.get("DIGI_API_KEY", "").strip()
    if api_key and request.url.path not in ("/health",):
        auth_header = request.headers.get("Authorization", "")
        if not secrets.compare_digest(auth_header, f"Bearer {api_key}"):
            logger.warning("Unauthorized request to %s from %s", request.url.path, request.client)
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    """Propagate X-Request-ID header; generate one if absent."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    text: str = Field(..., description="Search query text")
    index_name: str = Field(default="default", description="Index/collection name")
    top_k: int = Field(default=10, ge=1, le=100)
    mode: str = Field(default="hybrid", description="keyword | vector | hybrid")
    format: str = Field(default="default", description="default | table — table returns formatted markdown in response.formatted")
    filter: str | None = Field(default=None, description="Raw OData filter (when index allow_raw_filter)")
    filters: list[dict[str, Any]] | None = Field(default=None, description="Structured filters [{field, op, value}]")
    columns: list[str] | None = Field(default=None, description="Metadata columns to return")
    response_mode: str = Field(default="full", description="full | summary — return full rows or data summary")
    summarize_if_over: int | None = Field(default=None, ge=1, description="If result count > this, return summary instead of full")
    facets: list[str] | None = Field(default=None, description="Azure: facet expressions e.g. ['sourceType', 'itemType,count:20']")
    highlight_fields: list[str] | None = Field(default=None, description="Azure: fields to highlight matches in (searchable fields)")
    highlight_pre_tag: str | None = Field(default=None, description="Azure: tag before highlighted term e.g. '<em>'")
    highlight_post_tag: str | None = Field(default=None, description="Azure: tag after highlighted term e.g. '</em>'")
    order_by: list[str] | None = Field(default=None, description="Azure: sort clauses e.g. ['sentDateTime desc', 'search.score() desc']")
    skip: int = Field(default=0, ge=0, description="Pagination offset (page size = top_k)")
    include_total_count: bool = Field(default=False, description="When true, total is full match count for pagination")


class QueryResponse(BaseModel):
    """Response for POST /query."""

    results: list[dict]
    query: str
    index_name: str
    total: int
    formatted: str | None = Field(default=None, description="When format=table, markdown table string for display")
    summary: dict[str, Any] | None = Field(default=None, description="Data summary when response_mode=summary or over threshold")
    facets: dict[str, list[dict[str, Any]]] | None = Field(default=None, description="Facet counts by field when facets requested (Azure)")


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    source: str = Field(..., description="File path or URL")
    index_name: str = Field(default="default")
    doc_type: str | None = Field(default=None, description="pdf, html, docx, etc.")


class IngestResponse(BaseModel):
    """Response for POST /ingest."""

    doc_id: str
    chunks_created: int
    index_name: str
    status: str = "ok"


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for Docker and DigiGraph."""
    return {"status": "ok", "service": "digisearch"}


@app.get("/azure_status")
def azure_status() -> dict[str, bool | str]:
    """Check if Azure AI Search is configured and reachable."""
    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, _get_client

        if not is_azure_configured():
            return {"configured": False, "message": "Set AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME"}
        client = _get_client()
        if client is None:
            return {"configured": True, "reachable": False, "message": "Client init failed"}
        # Quick count to verify connection
        _ = client.get_document_count()
        return {"configured": True, "reachable": True, "message": "ok"}
    except ImportError:
        return {"configured": False, "message": "Install digisearch[azure] for Azure backend"}
    except Exception as e:
        return {"configured": True, "reachable": False, "message": str(e)[:200]}


def _build_query_filters(req: QueryRequest) -> dict[str, Any]:
    """Build Query.filters from request: either raw odata or structured list."""
    from digisearch.core.filter_validator import validate_odata_filter

    filters: dict[str, Any] = {}
    if req.filter and req.filter.strip():
        try:
            filters["odata"] = validate_odata_filter(req.filter.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.filters:
        filters["structured"] = req.filters
    return filters


@app.post("/query", response_model=QueryResponse)
def api_query(req: QueryRequest) -> QueryResponse:
    """Search documents. Use format=table to get response.formatted as markdown table."""
    q = Query(
        text=req.text,
        top_k=req.top_k,
        mode=req.mode,
        filters=_build_query_filters(req),
        columns=req.columns,
        facets=req.facets,
        highlight_fields=req.highlight_fields,
        highlight_pre_tag=req.highlight_pre_tag,
        highlight_post_tag=req.highlight_post_tag,
        order_by=req.order_by,
        skip=req.skip,
        include_total_count=req.include_total_count,
    )
    response = query_index(q, index_name=req.index_name)
    results = response.results
    # Build each result: content, score, doc_id, rank, and metadata (exclude @search.score; already at top level)
    out_results: list[dict] = []
    for r in results:
        meta = dict(r.chunk.metadata)
        meta.pop("@search.score", None)
        out_results.append({
            "content": r.chunk.content[:500],
            "score": r.score,
            "doc_id": r.chunk.doc_id,
            "rank": r.rank,
            "metadata": meta,
        })
    summary: dict[str, Any] | None = None
    use_summary = (req.response_mode or "").strip().lower() == "summary" or (
        req.summarize_if_over is not None and len(out_results) > req.summarize_if_over
    )
    if use_summary and out_results:
        from digisearch.core.summarize import summarize_results

        summary_obj = summarize_results(out_results, sample_size=5, include_text_summary=True)
        summary = summary_obj
        # Return first 5 results as sample so response shape stays consistent (content, score, doc_id, rank, metadata)
        out_results = out_results[:5]
    formatted: str | None = None
    if (getattr(req, "format", None) or "").strip().lower() == "table":
        from digisearch.http_client import format_results_table

        formatted = format_results_table(out_results, req.text, top_k=req.top_k)
    total = response.total_count if response.total_count is not None else len(results)
    return QueryResponse(
        results=out_results,
        query=req.text,
        index_name=req.index_name,
        total=total,
        formatted=formatted,
        summary=summary,
        facets=response.facets,
    )


@app.post("/ingest", response_model=IngestResponse)
def api_ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document. Uses parsers + chunkers when available. Returns 503 if ingestion fails."""
    from pathlib import Path
    try:
        from digisearch.ingestion.chunkers.recursive import RecursiveChunker
        from digisearch.ingestion.registry import ParserRegistry

        path = Path(req.source)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Source file not found: {req.source}")
        registry = ParserRegistry()
        doc = registry.parse(path)
        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        chunks = chunker.chunk(doc)
        doc.chunks = chunks
        add_chunks(req.index_name, chunks)
        return IngestResponse(
            doc_id=doc.id,
            chunks_created=len(chunks),
            index_name=req.index_name,
        )
    except HTTPException:
        raise
    except ImportError as e:
        logger.error("Ingestion dependencies not installed: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Ingestion backend unavailable (missing dependency: {e}). Install digisearch[parsers].",
        )
    except Exception as e:
        logger.error("Ingestion failed for source '%s': %s", req.source, e)
        raise HTTPException(
            status_code=503,
            detail=f"Ingestion failed: {e}",
        )


@app.get("/indexes")
def list_indexes() -> dict[str, list[str]]:
    """List available indexes."""
    from digisearch.search._stub import get_stub_index

    return {"indexes": list(get_stub_index().keys())}


@app.get("/indexes/{name}")
def get_index(name: str) -> dict:
    """Get index metadata."""
    from digisearch.search._stub import get_stub_index

    idx = get_stub_index()
    if name not in idx:
        raise HTTPException(status_code=404, detail=f"Index {name} not found")
    return {"name": name, "chunks": len(idx[name])}


@app.delete("/indexes/{name}/documents/{doc_id}")
def delete_document(name: str, doc_id: str) -> dict:
    """Delete document from index. Stub: no-op for in-memory."""
    return {"status": "ok", "message": "Delete not yet implemented for stub index"}
