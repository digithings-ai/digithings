"""DigiSearch HTTP API for DigiGraph and DigiFlow (query, ingest, Azure/Chroma backends)."""

from __future__ import annotations

import logging
import os
from typing import Any

from digibase.cors import install_cors
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware, digisearch_path_scopes

from digisearch import __version__
from digisearch.core.models import Query
from digisearch.logging import configure_logging
from digisearch.ingest_paths import resolve_ingest_source
from digisearch.search._stub import query_index, route_add_chunks

configure_logging()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


app = FastAPI(
    title="DigiSearch",
    description="RAG, document search for Digi ecosystem. MCP tools for DigiGraph/DigiFlow.",
    version=__version__,
)
install_metrics(app, service="digisearch", version=__version__)
install_cors(app, service="digisearch")
app.add_middleware(DigiAuthMiddleware, service="digisearch", path_scopes=digisearch_path_scopes)


@app.on_event("startup")
def _require_real_search_backend() -> None:
    """Fail startup unless Azure, Chroma, or DIGISEARCH_ALLOW_STUB=1 (unit tests) is set."""
    allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_stub:
        logger.warning("DigiSearch: DIGISEARCH_ALLOW_STUB=1 — in-memory stub allowed (tests only).")
        return
    from digisearch.indexes.backends import azure_search as _az

    azure_ok = False
    try:
        azure_ok = _az.is_azure_configured()
    except Exception as exc:
        logger.warning("Azure backend probe failed at startup: %s", exc)
        azure_ok = False
    chroma_ok = bool(os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"))
    if not azure_ok and not chroma_ok:
        raise RuntimeError(
            "DigiSearch requires a real backend: set AZURE_SEARCH_* or CHROMA_PATH/CHROMA_HOST, "
            "or DIGISEARCH_ALLOW_STUB=1 for tests only."
        )


import time as _time
from collections import deque as _deque
from threading import Lock as _Lock

_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/query": (10, 60),
    "/ingest": (30, 60),
    "/v1/research_turn": (10, 60),
    "/v1/orchestrator_tools": (30, 60),
    "/v1/orchestrator_invoke": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health", "/healthz"}


def _rl_check(request: Request, max_req: int, window: int) -> JSONResponse | None:
    if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return None
    xff = request.headers.get("X-Forwarded-For")
    ip = (
        xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    )
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
            return json_error_response(
                status_code=429,
                code="rate_limit_exceeded",
                message=f"Rate limit exceeded: {max_req} requests per {window}s.",
                request=request,
                service="digisearch",
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


install_request_id_middleware(app)
install_request_id_logging()


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="Search query text")
    index_name: str = Field(default="default", description="Index/collection name")
    top_k: int = Field(default=10, ge=1, le=100)
    mode: str = Field(default="hybrid", description="keyword | vector | hybrid")
    format: str = Field(
        default="default",
        description="default | table — table returns formatted markdown in response.formatted",
    )
    filter: str | None = Field(
        default=None, description="Raw OData filter (when index allow_raw_filter)"
    )
    filters: list[dict[str, Any]] | None = Field(
        default=None, description="Structured filters [{field, op, value}]"
    )
    columns: list[str] | None = Field(default=None, description="Metadata columns to return")
    response_mode: str = Field(
        default="full", description="full | summary — return full rows or data summary"
    )
    summarize_if_over: int | None = Field(
        default=None, ge=1, description="If result count > this, return summary instead of full"
    )
    facets: list[str] | None = Field(
        default=None,
        description="Azure: facet expressions e.g. ['sourceType', 'itemType,count:20']",
    )
    include_facets: bool = Field(
        default=False,
        description=(
            "When true, response.facets is populated (Azure only). "
            "Fields come from request.facets or the index config's facets list."
        ),
    )
    highlight_fields: list[str] | None = Field(
        default=None, description="Azure: fields to highlight matches in (searchable fields)"
    )
    highlight_pre_tag: str | None = Field(
        default=None, description="Azure: tag before highlighted term e.g. '<em>'"
    )
    highlight_post_tag: str | None = Field(
        default=None, description="Azure: tag after highlighted term e.g. '</em>'"
    )
    order_by: list[str] | None = Field(
        default=None,
        description="Azure: sort clauses e.g. ['sentDateTime desc', 'search.score() desc']",
    )
    skip: int = Field(default=0, ge=0, description="Pagination offset (page size = top_k)")
    include_total_count: bool = Field(
        default=False, description="When true, total is full match count for pagination"
    )
    workspace_id: str | None = Field(
        default=None,
        description="Optional tenant/workspace id for index isolation or filters (enterprise).",
    )


class QueryResponse(BaseModel):
    """Response for POST /query."""

    results: list[dict]
    query: str
    index_name: str
    total: int
    formatted: str | None = Field(
        default=None, description="When format=table, markdown table string for display"
    )
    summary: dict[str, Any] | None = Field(
        default=None, description="Data summary when response_mode=summary or over threshold"
    )
    facets: dict[str, list[dict[str, Any]]] | None = Field(
        default=None, description="Facet counts by field when facets requested (Azure)"
    )
    backend: str | None = Field(
        default=None,
        description="Index backend that served the query: azure_ai_search | chroma | stub",
    )


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., min_length=1, description="File path or URL")
    index_name: str = Field(default="default")
    doc_type: str | None = Field(default=None, description="pdf, html, docx, etc.")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Document metadata (evidence_tier, doi_or_arxiv, etc.). Merged after sidecar YAML.",
    )


class IngestResponse(BaseModel):
    """Response for POST /ingest."""

    doc_id: str
    chunks_created: int
    index_name: str
    status: str = "ok"


class ResearchTurnRequest(BaseModel):
    """Request for POST /v1/research_turn (composite retrieval + citations)."""

    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(..., min_length=1, description="User question or search intent")
    index_name: str = Field(default="default", description="Index/collection name")
    top_k: int = Field(default=10, ge=1, le=100)
    mode: str = Field(default="hybrid", description="keyword | vector | hybrid")
    filter: str | None = Field(default=None, description="Raw OData filter when index allows")
    filters: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured filters [{field, op, value}]",
    )
    session_id: str | None = Field(default=None, description="Optional session id for tracing")


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check for Docker and DigiGraph (kept for back-compat)."""
    return {"status": "ok", "service": "digisearch"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. Pair with DigiSmith's ``/v1/status``
    for richer diagnostics.
    """
    return {"ok": True}


@app.get("/azure_status")
def azure_status() -> dict[str, bool | str]:
    """Check if Azure AI Search is configured and reachable."""
    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, _get_client

        if not is_azure_configured():
            return {
                "configured": False,
                "message": "Set AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME",
            }
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


def run_query(req: QueryRequest) -> QueryResponse:
    """Core query implementation; shared by ``POST /query`` and orchestrator invoke."""
    from digisearch.core.standard_hits import normalize_query_hit

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
        include_facets=req.include_facets,
        workspace_id=(
            req.workspace_id.strip() if req.workspace_id and req.workspace_id.strip() else None
        ),
    )
    response = query_index(q, index_name=req.index_name)
    results = response.results
    out_results: list[dict] = [normalize_query_hit(r, content_preview_max=500) for r in results]
    summary: dict[str, Any] | None = None
    use_summary = (req.response_mode or "").strip().lower() == "summary" or (
        req.summarize_if_over is not None and len(out_results) > req.summarize_if_over
    )
    if use_summary and out_results:
        from digisearch.core.summarize import summarize_results

        summary_obj = summarize_results(out_results, sample_size=5, include_text_summary=True)
        summary = summary_obj
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
        backend=response.backend,
    )


@app.post("/query", response_model=QueryResponse)
def api_query(req: QueryRequest) -> QueryResponse:
    """Search documents. Use format=table to get response.formatted as markdown table."""
    return run_query(req)


class OrchestratorToolsRequest(BaseModel):
    """Request for POST /v1/orchestrator_tools."""

    index_config: dict[str, Any] | None = Field(
        default=None,
        description="Optional hub index metadata (filterable_fields, index_name, …) to specialize tool schemas.",
    )


class OrchestratorInvokeRequest(BaseModel):
    """Request for POST /v1/orchestrator_invoke."""

    tool: str = Field(
        ..., description="digisearch | digisearch_fetch_all | digisearch_research_delegate"
    )
    arguments: dict[str, Any] = Field(default_factory=dict)
    default_index_name: str | None = Field(
        default=None,
        description="Index when arguments omit index_name (hub workflow default).",
    )


def _research_turn_available() -> bool:
    try:
        from digisearch.agent.pipeline import run_research_turn  # noqa: F401

        return True
    except ImportError:
        return False


@app.post("/v1/orchestrator_tools")
def api_orchestrator_tools(req: OrchestratorToolsRequest) -> dict[str, Any]:
    """Return OpenAI-style tool definitions owned by DigiSearch (for DigiGraph orchestration)."""
    from digisearch.orchestrator_tools import build_orchestrator_tool_manifest

    tools = build_orchestrator_tool_manifest(
        req.index_config,
        include_research_delegate=_research_turn_available(),
    )
    return {"tools": tools, "version": 1}


def _query_request_from_digisearch_args(
    args: dict[str, Any],
    *,
    default_index: str,
    top_k: int,
    mode: str = "hybrid",
    skip: int = 0,
    include_total_count: bool = False,
) -> QueryRequest:
    qtext = str(args.get("query") or "").strip()
    idx = (args.get("index_name") or default_index or "default").strip() or "default"
    filt_raw = args.get("filter")
    filt = str(filt_raw).strip() if filt_raw else None
    filters = args.get("filters") if isinstance(args.get("filters"), list) else None
    columns = args.get("columns") if isinstance(args.get("columns"), list) else None
    facets = args.get("facets") if isinstance(args.get("facets"), list) else None
    include_facets = bool(args.get("include_facets", False))
    order_by = args.get("order_by") if isinstance(args.get("order_by"), list) else None
    response_mode = str(args.get("response_mode") or "full")
    summarize_raw = args.get("summarize_if_over")
    summarize_if_over = int(summarize_raw) if isinstance(summarize_raw, int) else None
    return QueryRequest(
        text=qtext or "",
        index_name=idx,
        top_k=top_k,
        mode=mode,
        filter=filt,
        filters=filters,
        columns=columns,
        facets=facets,
        include_facets=include_facets,
        order_by=order_by,
        response_mode=response_mode,
        summarize_if_over=summarize_if_over,
        skip=skip,
        include_total_count=include_total_count,
    )


@app.post("/v1/orchestrator_invoke")
def api_orchestrator_invoke(req: OrchestratorInvokeRequest) -> dict[str, Any]:
    """Execute one DigiSearch orchestrator tool by name (hub dispatch)."""
    tool = (req.tool or "").strip()
    args = req.arguments if isinstance(req.arguments, dict) else {}
    default_idx = (
        req.default_index_name or os.environ.get("DIGISEARCH_INDEX", "default") or "default"
    ).strip()

    if tool == "digisearch":
        top_raw = args.get("top_k", 10)
        top_k = int(top_raw) if isinstance(top_raw, int) else 10
        qreq = _query_request_from_digisearch_args(
            args,
            default_index=default_idx,
            top_k=top_k,
            mode=str(args.get("mode") or "hybrid"),
            skip=int(args.get("skip") or 0),
            include_total_count=bool(args.get("include_total_count", False)),
        )
        if not qreq.text.strip():
            return {"ok": False, "error": "query is required"}
        resp = run_query(qreq)
        return {
            "ok": True,
            "service": "digisearch",
            "tool": tool,
            "data": resp.model_dump(mode="json"),
        }

    if tool == "digisearch_fetch_all":
        page_size = 500
        max_results_raw = args.get("max_results")
        max_results = int(max_results_raw) if isinstance(max_results_raw, int) else None
        qtext = str(args.get("query") or "").strip()
        idx = (args.get("index_name") or default_idx or "default").strip() or "default"
        mode = str(args.get("mode") or "hybrid")
        filt_raw = args.get("filter")
        filt = str(filt_raw).strip() if filt_raw else None
        filters = args.get("filters") if isinstance(args.get("filters"), list) else None
        columns = args.get("columns") if isinstance(args.get("columns"), list) else None
        order_by = args.get("order_by") if isinstance(args.get("order_by"), list) else None
        if not qtext:
            return {"ok": False, "error": "query is required"}
        all_results: list[dict] = []
        skip = 0
        total_so_far = 0
        total_estimate: int | None = None
        while True:
            qreq = _query_request_from_digisearch_args(
                {
                    "query": qtext,
                    "index_name": idx,
                    "filter": filt,
                    "filters": filters,
                    "columns": columns,
                    "order_by": order_by,
                    "mode": mode,
                },
                default_index=default_idx,
                top_k=page_size,
                mode=mode,
                skip=skip,
                include_total_count=True,
            )
            resp = run_query(qreq)
            payload = resp.model_dump(mode="json")
            results = payload.get("results") or []
            if not results:
                break
            all_results.extend(results)
            total_so_far += len(results)
            total_estimate = payload.get("total")
            if total_estimate is not None and total_so_far >= int(total_estimate):
                break
            if max_results is not None and total_so_far >= max_results:
                all_results = all_results[:max_results]
                break
            if len(results) < page_size:
                break
            skip += page_size
        return {
            "ok": True,
            "service": "digisearch",
            "tool": tool,
            "data": {
                "results": all_results,
                "total": len(all_results),
                "query": qtext,
                "index_name": idx,
            },
        }

    if tool == "digisearch_research_delegate":
        try:
            from digisearch.agent.pipeline import run_research_turn
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Install digisearch[agent] for digisearch_research_delegate: {e}",
            ) from e
        msg = str(args.get("user_message") or "").strip()
        if not msg:
            return {"ok": False, "error": "user_message is required"}
        idx = (args.get("index_name") or default_idx or "default").strip() or "default"
        top_raw = args.get("top_k", 10)
        top_k = int(top_raw) if isinstance(top_raw, int) else 10
        filt_raw = args.get("filter")
        payload = {
            "user_message": msg,
            "index_name": idx,
            "top_k": top_k,
            "mode": str(args.get("mode") or "hybrid"),
            "filter": str(filt_raw).strip() if filt_raw else None,
            "filters": args.get("filters") if isinstance(args.get("filters"), list) else None,
            "session_id": args.get("session_id"),
        }
        body = run_research_turn(payload)
        return {"ok": True, "service": "digisearch", "tool": tool, "data": body}

    raise HTTPException(status_code=400, detail=f"Unknown orchestrator tool: {tool!r}")


@app.post("/v1/research_turn")
def api_research_turn(req: ResearchTurnRequest) -> dict[str, Any]:
    """Run one DigiSearch-owned research turn (LangGraph: plan → retrieve → aggregate)."""
    try:
        from digisearch.agent.pipeline import run_research_turn
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Install digisearch[agent] for /v1/research_turn: {e}",
        ) from e
    return run_research_turn(req.model_dump(mode="json"))


@app.post("/ingest", response_model=IngestResponse)
def api_ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document. Uses parsers + chunkers when available. Returns 503 if ingestion fails."""
    try:
        from digisearch.ingestion.chunkers.recursive import RecursiveChunker
        from digisearch.ingestion.registry import ParserRegistry

        try:
            path = resolve_ingest_source(req.source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Source file not found: {req.source}")
        registry = ParserRegistry()
        doc = registry.parse(path)
        from digisearch.core.evidence_metadata import (
            load_sidecar_yaml,
            merge_document_metadata_into_chunks,
            metadata_from_sidecar_dict,
        )

        side = path.parent / f"{path.stem}.yaml"
        if not side.is_file():
            side = path.parent / f"{path.stem}.yml"
        side_meta = metadata_from_sidecar_dict(load_sidecar_yaml(side))
        merged: dict[str, Any] = {**(doc.metadata or {}), **side_meta}
        if req.metadata:
            merged = {**merged, **req.metadata}
        doc.metadata = merged
        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        chunks = chunker.chunk(doc)
        merge_document_metadata_into_chunks(doc, chunks)
        doc.chunks = chunks
        try:
            route_add_chunks(req.index_name, chunks)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
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
    """Delete document from index (not implemented)."""
    raise HTTPException(
        status_code=501,
        detail="Per-document delete is not implemented for this DigiSearch deployment",
    )


register_fastapi_error_handlers(app, service="digisearch")
setup_otel_fastapi(app, service_name="digisearch")
