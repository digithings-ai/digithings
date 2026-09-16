"""digisearch HTTP API for digigraph and digiflow (query, ingest, Azure/Chroma backends)."""

# score:allow untyped any
# HTTP request/response payloads carry schema-dynamic metadata dicts; Any is the honest annotation.

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import sqlite3
import time as _time
from collections import deque as _deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Lock as _Lock
from typing import Any, Literal

from digibase.cors import install_cors
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware, digisearch_path_scopes

from digisearch import __version__
from digisearch.agent.pipeline_models import ResearchTurnOutput
from digisearch.backend_require import require_real_search_backend
from digisearch.core.models import Query
from digisearch.indexes.backends.vectorize import MAX_TOP_K as _VECTORIZE_MAX_TOP_K
from digisearch.logging import configure_logging
from digisearch.monitors.exa_adapter import (
    ExaAdapterError,
    exa_event_is_non_terminal,
    exa_monitor_id_from_payload,
    exa_run_to_monitor_run,
    verify_exa_signature,
)
from digisearch.monitors.models import MonitorRun, Watch
from digisearch.monitors.runner import MonitorRunError, run_watch, tick_due_watches
from digisearch.monitors.store import MonitorStore, MonitorStoreError, get_store
from digisearch.monitors.validation import DATATAP_WORKSPACE_ID, watch_config_error
from digisearch.orchestrator_tools import (
    TOOL_DIGISEARCH,
    TOOL_DIGISEARCH_FETCH_ALL,
    TOOL_DIGISEARCH_MONITORS_RUNS,
    TOOL_DIGISEARCH_MONITORS_TRIGGER,
    TOOL_DIGISEARCH_RESEARCH_DELEGATE,
    TOOL_DIGISEARCH_WEB_SEARCH,
    TOOL_DIGISEARCH_WEBSETS_ADD_SEARCH,
    TOOL_DIGISEARCH_WEBSETS_CREATE,
    TOOL_DIGISEARCH_WEBSETS_EVENTS,
    TOOL_DIGISEARCH_WEBSETS_EXPORT,
    TOOL_DIGISEARCH_WEBSETS_GET,
    TOOL_DIGISEARCH_WEBSETS_LIST_ITEMS,
    TOOL_WEB_SEARCH,
    OpenAIToolDict,
)
from digisearch.pipeline.ingest import IngestError, ingest_source
from digisearch.pipeline.url_ingest import UrlIngestResult, ingest_url
from digisearch.search._stub import query_index
from digisearch.web_exa import WebSearchData
from digisearch.web_search.models import WebSearchConfigError, WebSearchRequest, WebSearchResponse
from digisearch.websets import service as websets_service
from digisearch.websets.models import (
    EnrichmentDef,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetSearch,
)
from digisearch.websets.runner import (
    WEBSET_TASKS,
    backfill_enrichment,
    guard_webset_task,
    schedule_webset_task,
)
from digisearch.websets.service import WebsetServiceError
from digisearch.websets.store import WebsetStoreError
from digisearch.websets.store import get_store as get_webset_store

configure_logging()

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


def _resolve_fetch_all_max(requested: int | None) -> int:
    """Clamp fetch-all result cap to server default and hard ceiling."""
    default_max = int(os.environ.get("DIGISEARCH_FETCH_ALL_DEFAULT_MAX", "2000"))
    hard_ceiling = int(os.environ.get("DIGISEARCH_FETCH_ALL_HARD_CEILING", "10000"))
    cap = requested if requested is not None else default_max
    return min(max(cap, 1), hard_ceiling)


def get_monitor_store() -> MonitorStore:
    """Return a Phase C monitor store for the configured home (#4065, Task 2).

    Module-level seam for the Tasks 4/6/7 monitor consumers: each call resolves
    ``DIGISEARCH_MONITORS_DB`` → ``{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3``
    → cwd fallback and opens a fresh store. Tests and callers monkeypatch this
    attribute; there is deliberately no cached module-level store.
    """
    return get_store()


def _digisearch_path_scopes(method: str, path: str) -> list[str] | None:
    """Local scope resolver for the digikey auth middleware (R1).

    ``POST /v1/monitors/exa_webhook`` is the one auth-exempt digisearch route:
    EXA holds no digikey JWT, so it authenticates with the resolved watch's
    per-monitor stored secret checked inside the handler (missing or
    unverifiable secret → 401 ``exa_bad_signature``, fail closed). Every other
    path keeps the landed ``digisearch_path_scopes`` rules — no digikey change,
    and the Phase D ``/v1/websets*`` routes inherit its ``digisearch:query``
    fallthrough like the Phase C monitor paths do.
    """
    if method.upper() == "POST" and path == "/v1/monitors/exa_webhook":
        return None
    return digisearch_path_scopes(method, path)


# --- Phase D websets: lifespan-owned scheduler (§ Async lifecycle, #4066) ----


class _WebsetTaskScheduler:
    """Lifespan-owned ``WebsetScheduler``: runs are TaskGroup children.

    Installed on the service facade at startup (``set_scheduler``) so every
    route/service schedule ends up in the lifespan TaskGroup:

    - ``schedule_run`` delegates to ``runner.schedule_webset_task``, which owns
      the ``WEBSET_TASKS`` registry entry, the ``(webset_id, ok|error)``
      done-callback, and the single-drive guard;
    - ``schedule_backfill`` opens a tracked ``runner.backfill_enrichment`` task
      (the ``add_enrichment`` drain path);
    - ``cancel_all`` cancels every tracked task first so a clean shutdown never
      hangs on an in-flight pass (spec § Async lifecycle: a selected webset at
      boot is an orphan).
    """

    def __init__(self, task_group: asyncio.TaskGroup) -> None:
        self._task_group = task_group
        self._backfills: set[asyncio.Task[list[WebsetItem] | None]] = set()

    def schedule_run(self, webset_id: str, *, verification_mode: str = "llm") -> None:
        schedule_webset_task(self._task_group, webset_id, verification_mode=verification_mode)

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        task = self._task_group.create_task(
            guard_webset_task(
                backfill_enrichment(webset_id, enrichment_id),
                webset_id=webset_id,
                kind="backfill",
            )
        )
        self._backfills.add(task)
        task.add_done_callback(self._backfills.discard)

    def cancel_all(self) -> None:
        for task in [*WEBSET_TASKS.values(), *self._backfills]:
            task.cancel()


def _load_incomplete_websets() -> list[Webset]:
    """Startup-resume selector query, run on a worker thread by the lifespan."""
    return get_webset_store().list_incomplete_websets()


def _require_real_search_backend() -> None:
    """Fail startup unless Vectorize, Azure, Chroma, or DIGISEARCH_ALLOW_STUB=1 (unit tests) is set."""
    require_real_search_backend()


async def _resume_incomplete_websets(task_group: asyncio.TaskGroup) -> None:
    """Re-schedule every orphaned webset as a registry-tracked run.

    § Async lifecycle: the selector is the store's union of websets still
    ``running`` and websets holding a non-terminal ``running`` search; each
    selected webset is re-scheduled via ``run_webset_async`` (here through
    ``schedule_webset_task``, so the run is visible in ``WEBSET_TASKS`` like
    every other pass) under its persisted ``verification_mode``. The store
    query runs on a worker thread because the sqlite connection is thread-bound.
    A store that cannot be opened must not block startup: the routes will
    surface the same fault per request.
    """
    try:
        incomplete = await asyncio.to_thread(_load_incomplete_websets)
    except (OSError, sqlite3.Error, WebsetStoreError) as exc:
        logger.warning("webset startup resume skipped; store unavailable: %s", exc)
        return
    for webset in incomplete:
        logger.info("webset startup resume scheduled webset_id=%s", webset.id)
        schedule_webset_task(task_group, webset.id, verification_mode=webset.verification_mode)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """App lifespan: fail-closed backend gate + webset TaskGroup ownership.

    The TaskGroup wraps the whole serving window, so route-scheduled runs and
    backfills stay cancelable at shutdown; ``set_scheduler`` is undone first so
    no new work can be scheduled mid-teardown.
    """
    _require_real_search_backend()
    async with asyncio.TaskGroup() as task_group:
        scheduler = _WebsetTaskScheduler(task_group)
        websets_service.set_scheduler(scheduler)
        await _resume_incomplete_websets(task_group)
        try:
            yield
        finally:
            websets_service.set_scheduler(None)
            scheduler.cancel_all()


app = FastAPI(
    title="digisearch",
    description=(
        "RAG and document search for digithings: ingest, query, indexes, and research turns. "
        "MCP tools and orchestrator manifests for digigraph. "
        "Interactive docs: `/docs` (Swagger) and `/redoc`."
    ),
    version=__version__,
    lifespan=_lifespan,
)
install_metrics(app, service="digisearch", version=__version__)
install_cors(app, service="digisearch")
app.add_middleware(DigiAuthMiddleware, service="digisearch", path_scopes=_digisearch_path_scopes)


_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/query": (10, 60),
    "/ingest": (30, 60),
    "/v1/research_turn": (10, 60),
    "/v1/orchestrator_tools": (30, 60),
    "/v1/orchestrator_invoke": (10, 60),
    # §4.6 monitor statics; the per-watch routes are parameterized below.
    "/v1/monitors": (30, 60),
    "/v1/monitors/tick": (10, 60),
    "/v1/monitors/exa_webhook": (10, 60),
    # § Interfaces websets statics (creation is a DoS surface); the
    # parameterized webset routes follow the same two-tier mechanism (D17).
    "/v1/websets": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health", "/healthz"}

# R10: the §4.6 per-watch routes cannot be keyed by exact path. Ordered
# patterns; the exact table above is consulted first so the static monitor
# paths keep their own budgets.
_RATE_LIMIT_PATTERNS: tuple[tuple[re.Pattern[str], tuple[int, int]], ...] = (
    (re.compile(r"^/v1/monitors/[^/]+/trigger$"), (10, 60)),
    (re.compile(r"^/v1/monitors/[^/]+/runs$"), (30, 60)),
    (re.compile(r"^/v1/monitors/[^/]+/runs/[^/]+$"), (30, 60)),
    (re.compile(r"^/v1/monitors/[^/]+$"), (30, 60)),
    # § Interfaces websets pattern budget, most specific first: creation/refresh
    # surfaces 10/min, read surfaces 30/min. ``/v1/websets`` stays an exact
    # static above so the list/create path cannot fall into the id pattern.
    (re.compile(r"^/v1/websets/[^/]+/monitors/[^/]+/trigger$"), (10, 60)),
    (re.compile(r"^/v1/websets/[^/]+/webhooks/[^/]+/rotate$"), (10, 60)),
    (re.compile(r"^/v1/websets/[^/]+/(searches|monitors|webhooks|cancel|export)$"), (10, 60)),
    (re.compile(r"^/v1/websets/[^/]+/enrichments/[^/]+$"), (30, 60)),
    (re.compile(r"^/v1/websets/[^/]+/(items|events|enrichments)$"), (30, 60)),
    (re.compile(r"^/v1/websets/[^/]+$"), (30, 60)),
)


def _rate_limit_for(path: str) -> tuple[int, int]:
    """Resolve the ``(max_requests, window_seconds)`` budget for *path* (R10).

    Exact static paths win first so ``/v1/monitors/tick`` and
    ``/v1/monitors/exa_webhook`` cannot fall into the parameterized
    ``/v1/monitors/{watch_id}`` pattern; unknown paths use the default.
    """
    if path in _RATE_LIMITS:
        return _RATE_LIMITS[path]
    for pattern, limit in _RATE_LIMIT_PATTERNS:
        if pattern.match(path):
            return limit
    return _DEFAULT_RATE_LIMIT


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
    """Per-IP rate limiting. /query: 10/min; /ingest: 30/min; others: 30/min.

    Monitor routes follow §4.6 (trigger/tick/exa_webhook 10/min, CRUD and
    runs 30/min) via :func:`_rate_limit_for` (R10).
    """
    path = request.url.path
    if path not in _UNLIMITED_PATHS:
        max_req, window = _rate_limit_for(path)
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
    mode: str = Field(
        default="hybrid",
        description=(
            "keyword | vector | hybrid — capability hint. Chroma/Vectorize/stub "
            "coerce keyword/hybrid to vector-only ANN (see ARCHITECTURE)."
        ),
    )
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
    skip_rerank: bool = Field(
        default=False,
        description=(
            "When true, skip optional DIGISEARCH_RERANK_ENABLED second pass. "
            "Set by digisearch_fetch_all so partial pages are not reordered (#2441)."
        ),
    )

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_query_mode(cls, value: object) -> str:
        from digisearch.embedding.factory import normalize_query_mode

        return normalize_query_mode(str(value) if value is not None else "hybrid")


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
        description="Index backend that served the query: vectorize | azure_ai_search | chroma | stub",
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
    mode: str = Field(
        default="hybrid",
        description=(
            "keyword | vector | hybrid — capability hint. Chroma/Vectorize/stub "
            "coerce keyword/hybrid to vector-only ANN (see ARCHITECTURE)."
        ),
    )
    filter: str | None = Field(default=None, description="Raw OData filter when index allows")
    filters: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured filters [{field, op, value}]",
    )
    session_id: str | None = Field(default=None, description="Optional session id for tracing")
    workspace_id: str | None = Field(
        default=None,
        description=(
            "Optional tenant/workspace id. Injected as a mandatory structured filter "
            "so the research path is scoped like POST /query (enterprise)."
        ),
    )
    source: Literal["corpus", "web", "auto"] = Field(
        default="corpus",
        description=(
            "corpus | web | auto. Defaults to corpus; the web branch runs only when "
            "web or auto is explicitly requested."
        ),
    )
    effort: str = Field(
        default="fast",
        description="fast | thorough — web branch effort preset (validated by the branch).",
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema for structured web synthesis (web branch only).",
    )
    cited_top_n: int | None = Field(
        default=None,
        ge=1,
        description="Explicit cited-source cap; wins over the effort preset when set.",
    )

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_query_mode(cls, value: object) -> str:
        from digisearch.embedding.factory import normalize_query_mode

        return normalize_query_mode(str(value) if value is not None else "hybrid")


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check for Docker and digigraph (kept for back-compat)."""
    return {"status": "ok", "service": "digisearch"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. Pair with digismith's ``/v1/status``
    for richer diagnostics.
    """
    return {"ok": True}


@app.get("/azure_status")
def azure_status() -> dict[str, bool | str]:
    """Check if Azure AI Search is configured and reachable."""
    try:
        from digisearch.indexes.backends.azure_search import _get_client, is_azure_configured

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
    except (OSError, ValueError, RuntimeError, TypeError) as e:
        return {"configured": True, "reachable": False, "message": str(e)[:200]}


def _reject_raw_filter_if_disallowed(filter_raw: str | None, index_name: str | None) -> None:
    """Reject a raw OData filter for an index that has not opted in (#3909).

    Only the Azure backend re-gated raw ``filter``; every other backend passed it
    through. Raw OData is opt-in per ``digisearch/AGENTS.md``, so the server refuses
    it up front with HTTP 400 regardless of which backend would serve the query.
    """
    if not filter_raw or not str(filter_raw).strip():
        return
    from digisearch.core.config import index_allows_raw_filter

    if not index_allows_raw_filter(index_name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"raw filter not allowed for index {index_name or 'default'!r}: "
                "set allow_raw_filter=true in the index config, or use structured filters"
            ),
        )


def _build_query_filters(req: QueryRequest) -> dict[str, Any]:
    """Build Query.filters from request: either raw odata or structured list."""
    from digisearch.core.workspace_filter import build_query_filters

    _reject_raw_filter_if_disallowed(req.filter, req.index_name)
    try:
        workspace_id = (
            req.workspace_id.strip() if req.workspace_id and req.workspace_id.strip() else None
        )
        return build_query_filters(
            filter_raw=req.filter,
            filters_struct=req.filters,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def run_query(req: QueryRequest) -> QueryResponse:
    """Core query implementation; shared by ``POST /query`` and orchestrator invoke."""
    from digisearch.core.standard_hits import normalize_query_hit
    from digisearch.embedding.factory import effective_query_mode, normalize_query_mode

    try:
        mode = normalize_query_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    q = Query(
        text=req.text,
        top_k=req.top_k,
        mode=mode,
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
        skip_rerank=bool(req.skip_rerank),
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
    effective = effective_query_mode(mode, response.backend)
    if effective != mode:
        logger.info(
            "query.mode coerced for backend",
            extra={
                "operation": "query_mode",
                "requested_mode": mode,
                "effective_mode": effective,
                "backend": response.backend,
                "index_name": req.index_name,
            },
        )
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
        ...,
        description="digisearch | digisearch_fetch_all | digisearch_research_delegate | web_search | digisearch_web_search",
    )
    arguments: dict[str, Any] = Field(default_factory=dict)
    default_index_name: str | None = Field(
        default=None,
        description="Index when arguments omit index_name (hub workflow default).",
    )


class OrchestratorToolsResponse(BaseModel):
    """Response for POST /v1/orchestrator_tools (SIMP-020)."""

    tools: list[OpenAIToolDict]
    version: int = 1


class OrchestratorFetchAllData(BaseModel):
    """Payload for ``digisearch_fetch_all`` orchestrator invoke (SIMP-020)."""

    results: list[dict[str, Any]]
    total: int
    query: str
    index_name: str
    possibly_truncated: bool = Field(
        default=False,
        description=(
            "True when a page came back capped at the Vectorize backend's per-query "
            "match limit before this tool's own total/max_results check ended pagination "
            "-- `total` above may undercount the actual number of matches. Chroma/Azure "
            "pages never set this; only Vectorize's fixed per-query cap can trigger it."
        ),
    )


class MonitorRunsData(BaseModel):
    """Payload for the ``digisearch_monitors_runs`` orchestrator tool (Task 7)."""

    runs: list[MonitorRun]
    next_cursor: str | None = None


class WebsetCounts(BaseModel):
    """Item counts by verification state for ``digisearch_websets_get`` (#4066)."""

    pending: int = 0
    verified: int = 0
    rejected: int = 0


class WebsetGetData(BaseModel):
    """Payload for the ``digisearch_websets_get`` orchestrator tool (#4066)."""

    webset: Webset
    counts: WebsetCounts


class WebsetItemsData(BaseModel):
    """Payload for the ``digisearch_websets_list_items`` orchestrator tool (#4066)."""

    items: list[WebsetItem]
    next_cursor: str | None = None


class WebsetEventsData(BaseModel):
    """Payload for the ``digisearch_websets_events`` orchestrator tool (#4066)."""

    events: list[WebsetEvent]
    next_cursor: str | None = None


class WebsetExportData(BaseModel):
    """Payload for the ``digisearch_websets_export`` orchestrator tool (#4066)."""

    format: str
    content: str


class OrchestratorInvokeResponse(BaseModel):
    """Response for POST /v1/orchestrator_invoke (SIMP-020)."""

    ok: bool
    service: str | None = None
    tool: str | None = None
    data: (
        QueryResponse
        | OrchestratorFetchAllData
        | ResearchTurnOutput
        | WebSearchResponse
        | WebSearchData
        | MonitorRun
        | MonitorRunsData
        | Webset
        | WebsetSearch
        | WebsetGetData
        | WebsetItemsData
        | WebsetEventsData
        | WebsetExportData
        | None
    ) = None
    error: str | None = None


def _research_turn_available() -> bool:
    try:
        from digisearch.agent.pipeline import run_research_turn  # noqa: F401

        return True
    except ImportError:
        return False


@app.post("/v1/orchestrator_tools")
def api_orchestrator_tools(req: OrchestratorToolsRequest) -> OrchestratorToolsResponse:
    """Return OpenAI-style tool definitions owned by digisearch (for digigraph orchestration)."""
    from digisearch.orchestrator_tools import build_orchestrator_tool_manifest
    from digisearch.web_exa import is_exa_configured

    tools = build_orchestrator_tool_manifest(
        req.index_config,
        include_research_delegate=_research_turn_available(),
        include_web_search=is_exa_configured(),
    )
    return OrchestratorToolsResponse(tools=tools)


def _query_request_from_digisearch_args(
    args: dict[str, Any],
    *,
    default_index: str,
    top_k: int,
    mode: str = "hybrid",
    skip: int = 0,
    include_total_count: bool = False,
    skip_rerank: bool = False,
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
    workspace_raw = args.get("workspace_id")
    workspace_id = str(workspace_raw).strip() if workspace_raw else None
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
        skip_rerank=skip_rerank,
        workspace_id=workspace_id,
    )


def _coerce_web_search_max_results(raw: object) -> int | None:
    """Defensively coerce an orchestrator max_results arg; None when invalid.

    Accepts ints (never bools — the bool-is-int quirk silently mapped True to
    1), integral floats, and int-looking strings; clamps the result to 1–10.
    A missing arg (None) maps to the default 4; anything else is invalid.
    """
    if raw is None:
        return 4
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        num = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            return None
        num = int(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            num = int(text)
        except ValueError:
            return None
    else:
        return None
    return min(max(num, 1), 10)


# --- Phase D websets: orchestrator invoke branches (#4066, R12) --------------

_WEBSET_VERIFICATION_STATES = ("verified", "rejected", "pending")


def _coerce_webset_int(raw: object, *, default: int, minimum: int, maximum: int) -> int | None:
    """Defensively coerce an orchestrator webset integer arg (None when invalid).

    Bools are rejected (the bool-is-int quirk), integral strings are accepted,
    and the result is clamped to the documented bound.
    """
    if raw is None:
        return default
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        number = raw
    elif isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        number = int(raw.strip())
    else:
        return None
    return min(max(number, minimum), maximum)


def _invoke_webset_tool(tool: str, args: dict[str, Any]) -> OrchestratorInvokeResponse:
    """Dispatch one ``digisearch_websets_*`` tool to the service facade.

    Every failure is ``ok=False`` with the stable code (``code: message``) — the
    orchestrator surface raises no new error shape (R12). Missing required args
    are the same shape, never a 5xx.
    """
    webset_id = str(args.get("webset_id") or "").strip()
    if tool != TOOL_DIGISEARCH_WEBSETS_CREATE and not webset_id:
        return OrchestratorInvokeResponse(ok=False, error="webset_id is required")
    try:
        if tool == TOOL_DIGISEARCH_WEBSETS_CREATE:
            query = str(args.get("query") or "").strip()
            if not query:
                return OrchestratorInvokeResponse(ok=False, error="query is required")
            count = _coerce_webset_int(args.get("count"), default=10, minimum=1, maximum=100)
            if count is None:
                return OrchestratorInvokeResponse(ok=False, error="count must be an integer 1-100")
            criteria = args.get("criteria") if isinstance(args.get("criteria"), list) else []
            enrichments = (
                args.get("enrichments") if isinstance(args.get("enrichments"), list) else None
            )
            data: Any = websets_service.create_webset(
                query=query,
                count=count,
                criteria=criteria,
                enrichments=enrichments,
                verification_mode=str(args.get("verification_mode") or "llm"),
                workspace_id=(
                    str(args["workspace_id"]).strip() if args.get("workspace_id") else None
                ),
            )
        elif tool == TOOL_DIGISEARCH_WEBSETS_GET:
            webset = websets_service.get_webset(webset_id)
            data = WebsetGetData(
                webset=webset,
                counts=WebsetCounts(**websets_service.count_items(webset_id)),
            )
        elif tool == TOOL_DIGISEARCH_WEBSETS_ADD_SEARCH:
            query = str(args.get("query") or "").strip()
            if not query:
                return OrchestratorInvokeResponse(ok=False, error="query is required")
            count = _coerce_webset_int(args.get("count"), default=10, minimum=1, maximum=100)
            if count is None:
                return OrchestratorInvokeResponse(ok=False, error="count must be an integer 1-100")
            criteria = args.get("criteria") if isinstance(args.get("criteria"), list) else None
            data = websets_service.add_search(
                webset_id, query=query, count=count, criteria=criteria
            )
        elif tool == TOOL_DIGISEARCH_WEBSETS_LIST_ITEMS:
            verification = args.get("verification")
            if verification is not None and verification not in _WEBSET_VERIFICATION_STATES:
                return OrchestratorInvokeResponse(
                    ok=False, error="verification must be verified | rejected | pending"
                )
            limit = _coerce_webset_int(args.get("limit"), default=50, minimum=1, maximum=200)
            if limit is None:
                return OrchestratorInvokeResponse(ok=False, error="limit must be an integer 1-200")
            cursor = str(args["cursor"]).strip() if args.get("cursor") else None
            items, next_cursor = websets_service.list_items(
                webset_id, verification=verification, limit=limit, cursor=cursor
            )
            data = WebsetItemsData(items=items, next_cursor=next_cursor)
        elif tool == TOOL_DIGISEARCH_WEBSETS_EVENTS:
            limit = _coerce_webset_int(args.get("limit"), default=50, minimum=1, maximum=200)
            if limit is None:
                return OrchestratorInvokeResponse(ok=False, error="limit must be an integer 1-200")
            after = str(args["after"]).strip() if args.get("after") else None
            events, next_cursor = websets_service.list_events(webset_id, after=after, limit=limit)
            data = WebsetEventsData(events=events, next_cursor=next_cursor)
        elif tool == TOOL_DIGISEARCH_WEBSETS_EXPORT:
            fmt = str(args.get("format") or "json").strip().lower()
            content, _media_type = websets_service.export_webset(webset_id, fmt=fmt)
            data = WebsetExportData(format=fmt, content=content)
        else:  # pragma: no cover - the dispatch guard admits only the six names
            return OrchestratorInvokeResponse(ok=False, error=f"unknown webset tool: {tool!r}")
    except WebsetServiceError as exc:
        return OrchestratorInvokeResponse(ok=False, error=f"{exc.code}: {exc}")
    except ValidationError as exc:
        return OrchestratorInvokeResponse(ok=False, error=f"validation_error: {exc}")
    except ValueError as exc:
        return OrchestratorInvokeResponse(ok=False, error=str(exc))
    return OrchestratorInvokeResponse(ok=True, service="digisearch", tool=tool, data=data)


@app.post("/v1/orchestrator_invoke")
def api_orchestrator_invoke(req: OrchestratorInvokeRequest) -> OrchestratorInvokeResponse:
    """Execute one digisearch orchestrator tool by name (hub dispatch)."""
    tool = (req.tool or "").strip()
    args = req.arguments if isinstance(req.arguments, dict) else {}
    default_idx = (
        req.default_index_name or os.environ.get("DIGISEARCH_INDEX", "default") or "default"
    ).strip()

    if tool == TOOL_DIGISEARCH:
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
            return OrchestratorInvokeResponse(ok=False, error="query is required")
        resp = run_query(qreq)
        return OrchestratorInvokeResponse(
            ok=True,
            service="digisearch",
            tool=tool,
            data=resp,
        )

    if tool == TOOL_DIGISEARCH_FETCH_ALL:
        page_size = min(100, _resolve_fetch_all_max(None))
        max_results_raw = args.get("max_results")
        requested_max = int(max_results_raw) if isinstance(max_results_raw, int) else None
        max_results = _resolve_fetch_all_max(requested_max)
        qtext = str(args.get("query") or "").strip()
        idx = (args.get("index_name") or default_idx or "default").strip() or "default"
        mode = str(args.get("mode") or "hybrid")
        filt_raw = args.get("filter")
        filt = str(filt_raw).strip() if filt_raw else None
        filters = args.get("filters") if isinstance(args.get("filters"), list) else None
        columns = args.get("columns") if isinstance(args.get("columns"), list) else None
        order_by = args.get("order_by") if isinstance(args.get("order_by"), list) else None
        if not qtext:
            return OrchestratorInvokeResponse(ok=False, error="query is required")
        all_results: list[dict] = []
        skip = 0
        total_so_far = 0
        total_estimate: int | None = None
        possibly_truncated = False
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
                # Exhaustive pagination must not reorder each partial page (#2441).
                skip_rerank=True,
            )
            resp = run_query(qreq)
            payload = resp.model_dump(mode="json")
            results = payload.get("results") or []
            if not results:
                break
            all_results.extend(results)
            total_so_far += len(results)
            total_estimate = payload.get("total")
            # I4: Vectorize clamps any query to MAX_TOP_K (50) matches regardless of
            # the requested page_size. A page landing at exactly that cap while a
            # bigger page was requested is indistinguishable from "no more results"
            # by the len(results) < page_size check below -- it means this backend
            # cannot even see whether more matches exist, let alone page to them
            # (VectorizeBackend.query() does not consult Query.skip). Flag it rather
            # than let the caller believe `total` is exhaustive.
            if (
                payload.get("backend") == "vectorize"
                and page_size > _VECTORIZE_MAX_TOP_K
                and len(results) == _VECTORIZE_MAX_TOP_K
            ):
                possibly_truncated = True
                logger.warning(
                    "digisearch_fetch_all page capped at Vectorize's per-query limit "
                    "(%d matches, page_size=%d requested); result set may be incomplete",
                    _VECTORIZE_MAX_TOP_K,
                    page_size,
                    extra={
                        "operation": "digisearch_fetch_all",
                        "outcome": "clamped",
                        "index_name": idx,
                        "backend": "vectorize",
                    },
                )
            if total_estimate is not None and total_so_far >= int(total_estimate):
                break
            if max_results is not None and total_so_far >= max_results:
                all_results = all_results[:max_results]
                break
            if len(results) < page_size:
                break
            skip += page_size
        return OrchestratorInvokeResponse(
            ok=True,
            service="digisearch",
            tool=tool,
            data=OrchestratorFetchAllData(
                results=all_results,
                total=len(all_results),
                query=qtext,
                index_name=idx,
                possibly_truncated=possibly_truncated,
            ),
        )

    if tool == TOOL_DIGISEARCH_RESEARCH_DELEGATE:
        try:
            from digisearch.agent.pipeline import run_research_turn
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Install digisearch[agent] for digisearch_research_delegate: {e}",
            ) from e
        msg = str(args.get("user_message") or "").strip()
        if not msg:
            return OrchestratorInvokeResponse(ok=False, error="user_message is required")
        idx = (args.get("index_name") or default_idx or "default").strip() or "default"
        top_raw = args.get("top_k", 10)
        top_k = int(top_raw) if isinstance(top_raw, int) else 10
        filt_raw = args.get("filter")
        filt = str(filt_raw).strip() if filt_raw else None
        _reject_raw_filter_if_disallowed(filt, idx)
        src_raw = args.get("source")
        payload = {
            "user_message": msg,
            "index_name": idx,
            "top_k": top_k,
            "mode": str(args.get("mode") or "hybrid"),
            "filter": filt,
            "filters": args.get("filters") if isinstance(args.get("filters"), list) else None,
            "session_id": args.get("session_id"),
            "workspace_id": args.get("workspace_id"),
            "source": str(src_raw).strip().lower() if src_raw else "corpus",
            "effort": str(args.get("effort") or "fast"),
            "output_schema": args.get("output_schema")
            if isinstance(args.get("output_schema"), dict)
            else None,
        }
        body = run_research_turn(payload)
        return OrchestratorInvokeResponse(
            ok=True,
            service="digisearch",
            tool=tool,
            data=ResearchTurnOutput.model_validate(body),
        )

    if tool == TOOL_WEB_SEARCH:
        try:
            from digisearch.web_search.service import run_web_search
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Install digisearch[web-search] for web_search: {e}",
            ) from e
        qtext = str(args.get("query") or "").strip()
        if not qtext:
            return OrchestratorInvokeResponse(ok=False, error="query is required")
        include = (
            args.get("include_domains") if isinstance(args.get("include_domains"), list) else []
        )
        exclude = (
            args.get("exclude_domains") if isinstance(args.get("exclude_domains"), list) else []
        )
        max_results = _coerce_web_search_max_results(args.get("max_results", 4))
        if max_results is None:
            return OrchestratorInvokeResponse(ok=False, error="max_results must be an integer 1-10")
        try:
            web_req = WebSearchRequest(
                query=qtext,
                include_domains=[str(d) for d in include],
                exclude_domains=[str(d) for d in exclude],
                max_results=max_results,
            )
        except ValidationError as e:
            from digisearch.web_search.models import summarize_validation_error

            return OrchestratorInvokeResponse(
                ok=False, error=f"invalid web_search input: {summarize_validation_error(e)}"
            )
        try:
            resp = run_web_search(web_req)
        except WebSearchConfigError as e:
            return OrchestratorInvokeResponse(ok=False, error=f"invalid web_search config: {e}")
        return OrchestratorInvokeResponse(
            ok=True,
            service="digisearch",
            tool=tool,
            data=resp,
        )

    if tool == TOOL_DIGISEARCH_WEB_SEARCH:
        from digisearch import web_exa

        if not web_exa.is_exa_configured():
            return OrchestratorInvokeResponse(ok=False, error="EXA_API_KEY is not set")
        qtext = str(args.get("query") or "").strip()
        if not qtext:
            return OrchestratorInvokeResponse(ok=False, error="query is required")
        stype = str(args.get("search_type") or "auto")
        if stype not in web_exa.VALID_SEARCH_TYPES:
            return OrchestratorInvokeResponse(ok=False, error=f"invalid search_type: {stype!r}")
        n_raw = args.get("num_results", 8)
        inc = args.get("include_domains")
        exc = args.get("exclude_domains")
        try:
            data = web_exa.exa_search(
                qtext,
                search_type=stype,  # type: ignore[arg-type]
                num_results=int(n_raw) if isinstance(n_raw, int) else 8,
                category=args.get("category"),
                contents_text=bool(args.get("contents_text", False)),
                output_schema=args.get("output_schema")
                if isinstance(args.get("output_schema"), dict)
                else None,
                include_domains=inc if isinstance(inc, list) else None,
                exclude_domains=exc if isinstance(exc, list) else None,
            )
        except (web_exa.ExaError, ValueError) as e:
            return OrchestratorInvokeResponse(ok=False, error=str(e))
        return OrchestratorInvokeResponse(ok=True, service="digisearch", tool=tool, data=data)

    if tool == TOOL_DIGISEARCH_MONITORS_TRIGGER:
        watch_id = str(args.get("watch_id") or "").strip()
        if not watch_id:
            return OrchestratorInvokeResponse(ok=False, error="watch_id is required")
        raw_mode = str(args.get("mode") or "manual")
        if raw_mode not in ("manual", "poll"):
            return OrchestratorInvokeResponse(ok=False, error=f"invalid mode: {raw_mode!r}")
        mode: Literal["manual", "poll"] = "poll" if raw_mode == "poll" else "manual"
        try:
            run = run_watch(watch_id, trigger=mode, store=get_monitor_store())
        except MonitorStoreError as exc:
            return OrchestratorInvokeResponse(ok=False, error=f"{exc.code}: {exc}")
        except MonitorRunError as exc:
            # The failed turn is already persisted; the hub gets the fail-hard
            # shape instead of a body (POST /v1/monitors/{id}/trigger returns it).
            return OrchestratorInvokeResponse(ok=False, error=str(exc))
        return OrchestratorInvokeResponse(ok=True, service="digisearch", tool=tool, data=run)

    if tool == TOOL_DIGISEARCH_MONITORS_RUNS:
        watch_id = str(args.get("watch_id") or "").strip()
        if not watch_id:
            return OrchestratorInvokeResponse(ok=False, error="watch_id is required")
        limit_raw = args.get("limit", 20)
        limit = limit_raw if isinstance(limit_raw, int) and not isinstance(limit_raw, bool) else 20
        cursor_raw = args.get("cursor")
        cursor = str(cursor_raw).strip() if cursor_raw else None
        try:
            runs, next_cursor = get_monitor_store().list_runs(watch_id, limit=limit, cursor=cursor)
        except MonitorStoreError as exc:
            return OrchestratorInvokeResponse(ok=False, error=f"{exc.code}: {exc}")
        return OrchestratorInvokeResponse(
            ok=True,
            service="digisearch",
            tool=tool,
            data=MonitorRunsData(runs=runs, next_cursor=next_cursor),
        )

    # Phase D websets (#4066, R12): six prefixed manifest names, each reaching
    # the facade through _invoke_webset_tool (errors are ok:false, never 4xx).
    if tool == TOOL_DIGISEARCH_WEBSETS_CREATE:
        return _invoke_webset_tool(tool, args)

    if tool == TOOL_DIGISEARCH_WEBSETS_GET:
        return _invoke_webset_tool(tool, args)

    if tool == TOOL_DIGISEARCH_WEBSETS_ADD_SEARCH:
        return _invoke_webset_tool(tool, args)

    if tool == TOOL_DIGISEARCH_WEBSETS_LIST_ITEMS:
        return _invoke_webset_tool(tool, args)

    if tool == TOOL_DIGISEARCH_WEBSETS_EVENTS:
        return _invoke_webset_tool(tool, args)

    if tool == TOOL_DIGISEARCH_WEBSETS_EXPORT:
        return _invoke_webset_tool(tool, args)

    raise HTTPException(status_code=400, detail=f"Unknown orchestrator tool: {tool!r}")


@app.post("/v1/research_turn", response_model=ResearchTurnOutput)
def api_research_turn(req: ResearchTurnRequest) -> ResearchTurnOutput:
    """Run one digisearch-owned research turn (LangGraph: plan → retrieve → aggregate)."""
    try:
        from digisearch.agent.pipeline import run_research_turn
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Install digisearch[agent] for /v1/research_turn: {e}",
        ) from e
    _reject_raw_filter_if_disallowed(req.filter, req.index_name)
    return ResearchTurnOutput.model_validate(run_research_turn(req.model_dump(mode="json")))


@app.post("/v1/web_search", response_model=WebSearchResponse)
def v1_web_search(req: WebSearchRequest) -> WebSearchResponse:
    """Search the public web (searxng with ddgs fallback, fetch + extract enrichment)."""
    try:
        from digisearch.web_search.service import run_web_search
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Install digisearch[web-search] for /v1/web_search: {e}",
        ) from e
    try:
        return run_web_search(req)
    except WebSearchConfigError as e:
        raise HTTPException(
            status_code=503,
            detail=f"invalid web_search config: {e}",
        ) from e


class ExaWebSearchRequest(BaseModel):
    """Request for POST /v1/digisearch_web_search (EXA live web search, optional provider)."""

    query: str = Field(..., description="Natural-language web query.")
    search_type: str = Field(
        default="auto", description="instant|fast|auto|deep-lite|deep|deep-reasoning."
    )
    num_results: int = Field(default=8, ge=1, le=100)
    category: str | None = None
    contents_text: bool = False
    output_schema: dict[str, Any] | None = None
    system_prompt: str | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None


class WebContentsRequest(BaseModel):
    """Request for POST /v1/web_contents (EXA page fetch for known URLs)."""

    urls: list[str] = Field(..., min_length=1, max_length=50, description="Known URLs to fetch.")
    text: bool = True
    highlights: bool = False
    summary: bool = False
    highlight_query: str | None = None


class WebAnswerRequest(BaseModel):
    """Request for POST /v1/web_answer (EXA grounded answer)."""

    question: str = Field(..., description="Question to answer from the live web.")


@app.post("/v1/digisearch_web_search", response_model=WebSearchData)
def api_web_search(req: ExaWebSearchRequest) -> WebSearchData:
    """Live web search via EXA (dormant without EXA_API_KEY; not the owned corpus).

    Mounted at ``/v1/digisearch_web_search`` (not ``/v1/web_search``): the first-party
    searxng→ddgs web search owns ``/v1/web_search`` on develop.
    """
    from digisearch import web_exa

    if not web_exa.is_exa_configured():
        raise HTTPException(status_code=503, detail="EXA_API_KEY is not set")
    if req.search_type not in web_exa.VALID_SEARCH_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid search_type: {req.search_type!r}")
    try:
        return web_exa.exa_search(
            req.query,
            search_type=req.search_type,  # type: ignore[arg-type]
            num_results=req.num_results,
            category=req.category,
            contents_text=req.contents_text,
            output_schema=req.output_schema,
            system_prompt=req.system_prompt,
            include_domains=req.include_domains,
            exclude_domains=req.exclude_domains,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except web_exa.ExaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/v1/web_contents")
def api_web_contents(req: WebContentsRequest) -> dict[str, Any]:
    """Fetch known URLs via EXA contents (dormant without EXA_API_KEY)."""
    from digisearch import web_exa

    if not web_exa.is_exa_configured():
        raise HTTPException(status_code=503, detail="EXA_API_KEY is not set")
    try:
        return web_exa.exa_contents(
            req.urls,
            text=req.text,
            highlights=req.highlights,
            summary=req.summary,
            highlight_query=req.highlight_query,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except web_exa.ExaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/v1/web_answer")
def api_web_answer(req: WebAnswerRequest) -> dict[str, Any]:
    """Grounded answer from the live web via EXA (dormant without EXA_API_KEY)."""
    from digisearch import web_exa

    if not web_exa.is_exa_configured():
        raise HTTPException(status_code=503, detail="EXA_API_KEY is not set")
    try:
        return web_exa.exa_answer(req.question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except web_exa.ExaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


class IngestUrlRequest(BaseModel):
    """Request body for POST /ingest/url."""

    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(..., min_length=1, description="URL to fetch and ingest")
    index_name: str = Field(default="default")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Document metadata (evidence_tier, doi_or_arxiv, etc.). Merged after sidecar YAML.",
    )


@app.post("/ingest", response_model=IngestResponse)
def api_ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document via :func:`digisearch.pipeline.ingest.ingest_source`."""
    try:
        result = ingest_source(
            req.source,
            index_name=req.index_name,
            metadata=req.metadata,
            enforce_ingest_root=True,
        )
    except IngestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc
    return IngestResponse(
        doc_id=result.doc_id,
        chunks_created=result.chunks_created,
        index_name=result.index_name,
        status=result.status,
    )


@app.post("/ingest/url", response_model=UrlIngestResult)
def api_ingest_url(req: IngestUrlRequest) -> UrlIngestResult:
    """Ingest a URL via :func:`digisearch.pipeline.url_ingest.ingest_url`."""
    try:
        return ingest_url(req.source_url, index_name=req.index_name, metadata=req.metadata)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Install digisearch[web-search] for /ingest/url: {exc}",
        ) from exc
    except IngestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc


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
        detail="Per-document delete is not implemented for this digisearch deployment",
    )


# --- Phase C monitors (§4.6, #4065) -------------------------------------------------
#
# Thin handlers only: validate → build the store in this request's thread →
# call the Task 4 runner / Task 5 delivery → return. Monitor store connections
# are thread-bound (``check_same_thread`` stays default), so ``get_monitor_store()``
# is invoked inside the handler and never bound via ``Depends``.


def _monitor_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    """Build the shared digibase error envelope for a monitor route."""
    return json_error_response(
        status_code=status_code,
        code=code,
        message=message,
        request=request,
        service="digisearch",
    )


def _store_error(request: Request, exc: MonitorStoreError) -> JSONResponse:
    """Map a store failure to the §4.6 envelope (missing → 404, else 409)."""
    status_code = 404 if exc.code in ("watch_not_found", "run_not_found") else 409
    return _monitor_error(request, status_code, exc.code, str(exc))


def _validate_watch_config(watch: Watch, request: Request) -> JSONResponse | None:
    """Create/update gate: datatap off, known timezone, parseable cron, deliverable.

    Delegates the decision to :func:`digisearch.monitors.validation.watch_config_error`
    (shared with the Task 7 MCP create tool) and renders it in the §4.6 envelope.
    Runs before persistence so an invalid schedule or delivery config can never
    reach the store (and therefore never the tick).
    """
    failure = watch_config_error(watch)
    if failure is None:
        return None
    status_code, code, message = failure
    return _monitor_error(request, status_code, code, message)


class MonitorTriggerRequest(BaseModel):
    """Request body for POST /v1/monitors/{watch_id}/trigger."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "poll"] = "manual"


@app.post("/v1/monitors", status_code=201, response_model=None)
def api_create_monitor(watch: Watch, request: Request) -> dict[str, Any] | JSONResponse:
    """Create a watch. The response carries the one-time delivery secret (R8)."""
    invalid = _validate_watch_config(watch, request)
    if invalid is not None:
        return invalid
    store = get_monitor_store()
    created = store.create_watch(watch)
    secret = secrets.token_hex(32)
    store.set_delivery_secret(created.watch_id, secret)
    return {"watch": created.model_dump(mode="json"), "delivery_secret": secret}


@app.get("/v1/monitors")
def api_list_monitors(request: Request, workspace_id: str | None = None) -> dict[str, Any]:
    """List watches newest-updated first, optionally scoped by workspace."""
    store = get_monitor_store()
    watches = store.list_watches(workspace_id=workspace_id or None)
    return {"watches": [watch.model_dump(mode="json") for watch in watches]}


@app.get("/v1/monitors/{watch_id}", response_model=None)
def api_get_monitor(watch_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """Load one watch. The delivery secret is never part of a watch body (R8)."""
    store = get_monitor_store()
    try:
        watch = store.get_watch(watch_id)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    return watch.model_dump(mode="json")


@app.patch("/v1/monitors/{watch_id}", response_model=None)
def api_update_monitor(
    watch_id: str, patch: dict[str, Any], request: Request
) -> dict[str, Any] | JSONResponse:
    """Apply a partial patch; ``{"rotate_delivery_secret": true}`` mints a new secret (R8)."""
    store = get_monitor_store()
    rotate = patch.pop("rotate_delivery_secret", False) is True
    try:
        current = store.get_watch(watch_id)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    if patch:
        try:
            candidate = Watch.model_validate({**current.model_dump(mode="json"), **patch})
        except ValidationError as exc:
            return _monitor_error(request, 422, "validation_error", str(exc))
        invalid = _validate_watch_config(candidate, request)
        if invalid is not None:
            return invalid
        try:
            watch = store.update_watch(watch_id, patch)
        except MonitorStoreError as exc:
            return _store_error(request, exc)
    else:
        watch = current
    if rotate:
        secret = secrets.token_hex(32)
        store.set_delivery_secret(watch_id, secret)
        return {"watch": watch.model_dump(mode="json"), "delivery_secret": secret}
    return watch.model_dump(mode="json")


@app.delete("/v1/monitors/{watch_id}", response_model=None)
def api_delete_monitor(watch_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """Delete a watch; its run history is retained."""
    store = get_monitor_store()
    try:
        store.delete_watch(watch_id)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    return {"deleted": watch_id}


@app.post("/v1/monitors/{watch_id}/trigger", status_code=201, response_model=None)
def api_trigger_monitor(
    watch_id: str, req: MonitorTriggerRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Run one watch turn now (the portable create → trigger → runs path).

    A failed turn already persisted its ``status="failed"`` run, so the stored
    record is returned with 201 rather than masked by a 5xx.
    """
    store = get_monitor_store()
    try:
        run = run_watch(watch_id, trigger=req.mode, store=store)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    except MonitorRunError as exc:
        run = store.get_run(watch_id, exc.run_id)
    return run.model_dump(mode="json")


@app.get("/v1/monitors/{watch_id}/runs", response_model=None)
def api_list_monitor_runs(
    watch_id: str, request: Request, limit: int = 20, cursor: str | None = None
) -> dict[str, Any] | JSONResponse:
    """Page run history newest-first; *cursor* is the last run id of a page."""
    store = get_monitor_store()
    try:
        runs, next_cursor = store.list_runs(watch_id, limit=limit, cursor=cursor)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    return {
        "runs": [run.model_dump(mode="json") for run in runs],
        "next_cursor": next_cursor,
    }


@app.get("/v1/monitors/{watch_id}/runs/{run_id}", response_model=None)
def api_get_monitor_run(
    watch_id: str, run_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    """Load one stored run."""
    store = get_monitor_store()
    try:
        run = store.get_run(watch_id, run_id)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    return run.model_dump(mode="json")


@app.post("/v1/monitors/tick")
def api_tick_monitors(request: Request) -> dict[str, Any]:
    """Run every due + enabled watch once (digiclaw wake-up clock, §4.8)."""
    store = get_monitor_store()
    runs = tick_due_watches(store=store)
    return {"runs": [run.model_dump(mode="json") for run in runs]}


@app.post("/v1/monitors/exa_webhook", response_model=None)
async def api_exa_webhook(request: Request) -> dict[str, Any] | JSONResponse:
    """Auth-exempt but per-watch-secret-gated EXA delivery webhook (R1, §4.6).

    EXA cannot present a digikey JWT, so the route is exempted in
    :func:`_digisearch_path_scopes` and authenticates each delivery with the
    WATCH's own stored secret (``MonitorStore.get_delivery_secret``) against the
    live-pinned ``exa-signature: t=<unix>,v1=<hex>`` header
    (``HMAC-SHA256(secret, f"{t}.{body}")``, #4123). There is deliberately no
    static shared-secret fallback: a missing stored secret, a missing header,
    or a mismatch fails closed with 401 ``exa_bad_signature``; the presented
    value is never logged or echoed.

    The target watch is resolved by matching the NESTED event envelope's
    ``data.monitorId`` against stored ``Watch.exa_monitor_id`` values — the
    minimal derivation that needs no new store API; datatap-scoped watches
    never match (§5). Signature verification happens before any translation or
    persistence, and the resolved watch must be ``backend="exa"`` (a mismatch
    is a misconfiguration: 409 ``watch_backend_mismatch``, nothing persisted).

    Non-terminal deliveries (``monitor.run.created``, run ``status: "running"``)
    are acked 200 ``{"acknowledged": true}`` without persisting; terminal
    deliveries translate (Task 8c adapter) into the canonical ``MonitorRun``
    and persist it — 201 on first store, and an idempotent 200 with the stored
    run on redelivery (EXA retries non-2xx, so ``run_exists`` must never answer
    409). Translation and store failures use the shared fail-closed envelope.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except ValueError:
        return _monitor_error(
            request, 400, "exa_payload_invalid", "EXA webhook body is not valid JSON."
        )
    if not isinstance(payload, dict):
        return _monitor_error(
            request, 422, "exa_payload_invalid", "EXA webhook payload must be a JSON object."
        )
    try:
        exa_monitor_id = exa_monitor_id_from_payload(payload)
    except ExaAdapterError as exc:
        return _monitor_error(request, 422, exc.code, str(exc))

    store = get_monitor_store()
    watch = next(
        (
            candidate
            for candidate in store.list_watches()
            if candidate.exa_monitor_id == exa_monitor_id
            and candidate.workspace_id != DATATAP_WORKSPACE_ID
        ),
        None,
    )
    if watch is None:
        return _monitor_error(
            request,
            404,
            "watch_not_found",
            f"No watch is linked to EXA monitor {exa_monitor_id!r}.",
        )
    try:
        secret = store.get_delivery_secret(watch.watch_id)
    except MonitorStoreError as exc:
        return _store_error(request, exc)
    presented = request.headers.get("exa-signature") or ""
    if not secret or not verify_exa_signature(header=presented, body=raw_body, secret=secret):
        return _monitor_error(request, 401, "exa_bad_signature", "Invalid EXA webhook signature.")
    if watch.backend != "exa":
        return _monitor_error(
            request,
            409,
            "watch_backend_mismatch",
            f"Watch {watch.watch_id!r} is not an exa-backend watch.",
        )
    try:
        if exa_event_is_non_terminal(payload):
            return {"acknowledged": True}
    except ExaAdapterError as exc:
        return _monitor_error(request, 422, exc.code, str(exc))
    try:
        run = exa_run_to_monitor_run(watch_id=watch.watch_id, exa_payload=payload)
    except ExaAdapterError as exc:
        return _monitor_error(request, 422, exc.code, str(exc))
    try:
        store.append_run(run)
    except MonitorStoreError as exc:
        if exc.code != "run_exists":
            return _store_error(request, exc)
        try:
            stored = store.get_run(watch.watch_id, run.run_id)
        except MonitorStoreError as lookup_exc:
            return _store_error(request, lookup_exc)
        return stored.model_dump(mode="json")
    return JSONResponse(status_code=201, content=run.model_dump(mode="json"))


# --- Phase D websets (§ Interfaces, #4066) -----------------------------------
#
# Thin handlers only: validate the body shape, call the T6 service facade (which
# opens its own thread-bound store per call via DIGISEARCH_WEBSETS_DB), and
# render either the object or the shared digibase error envelope. The run itself
# is never awaited here: the lifespan-installed scheduler owns the TaskGroup and
# the WEBSET_TASKS registry (§ Async lifecycle), and every route returns
# immediately (202/201).


def _webset_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    """Build the shared digibase error envelope for a webset route."""
    return json_error_response(
        status_code=status_code,
        code=code,
        message=message,
        request=request,
        service="digisearch",
    )


#: Stable webset codes → HTTP status. Anything absent (and any 500-class entry)
#: renders as the generic ``internal_error``, so store-internal invariant codes
#: (``webset_not_settled``, ``transition_invalid``, ...) can never surface.
_WEBSET_ERROR_STATUS: dict[str, int] = {
    "webset_not_found": 404,
    "search_not_found": 404,
    "monitor_not_found": 404,
    "enrichment_not_found": 404,
    "item_not_found": 404,
    "webhook_not_found": 404,
    "cursor_not_found": 404,
    "invalid_criteria": 422,
    "invalid_verification_mode": 422,
    "datatap_websets_disabled": 422,
    "webhook_url_required": 422,
    "webhook_url_private": 422,
    "enrichment_limit_exceeded": 400,
    "webset_terminal": 409,
    # A T5b ledger receipt error, never a route failure: map to the internal
    # shape so neither the code nor ledger detail surfaces.
    "webhook_secret_missing": 500,
}


def _webset_service_error(request: Request, exc: WebsetServiceError) -> JSONResponse:
    """Map a facade failure to the § Interfaces envelope (unknown → internal)."""
    status_code = _WEBSET_ERROR_STATUS.get(exc.code)
    if status_code is None or status_code >= 500:
        logger.warning("webset service error mapped to internal_error: %s", exc.code)
        return _webset_error(
            request, 500, websets_service.INTERNAL_ERROR_CODE, "internal webset failure"
        )
    return _webset_error(request, status_code, exc.code, str(exc))


class WebsetCreateRequest(BaseModel):
    """Request body for POST /v1/websets (spec § Interfaces)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Natural-language candidate query")
    count: int = Field(
        default=10, ge=1, le=100, description="Target VERIFIED items (not a page size)"
    )
    criteria: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "1-5 verification rules [{name, rule}]; the service raises invalid_criteria "
            "for 0 or >5 so the stable code reaches the envelope"
        ),
    )
    enrichments: list[dict[str, Any]] | None = Field(
        default=None, description="Up to 10 typed enrichment defs (max 10 enforced by the service)"
    )
    verification_mode: str = Field(
        default="llm",
        description="llm (default) | rules — validated by the service (invalid_verification_mode)",
    )
    workspace_id: str | None = Field(
        default=None, description="Tenant id; 'datatap' is rejected (datatap_websets_disabled)"
    )


class WebsetSearchRequest(BaseModel):
    """Request body for POST /v1/websets/{webset_id}/searches."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    count: int = Field(default=10, ge=1, le=100)
    criteria: list[dict[str, str]] | None = Field(
        default=None, description="Missing criteria inherit the webset's initial rules"
    )


class WebsetMonitorRequest(BaseModel):
    """Request body for POST /v1/websets/{webset_id}/monitors (poll-only v1)."""

    model_config = ConfigDict(extra="forbid")

    interval_seconds: int = Field(
        default=3600, ge=60, description="Refresh-cadence METADATA; no tick driver runs it in v1"
    )
    webhook_url: str | None = Field(
        default=None, description="Optional https public URL (Phase C SSRF gate)"
    )


class WebsetWebhookRequest(BaseModel):
    """Request body for POST /v1/websets/{webset_id}/webhooks (secret returned once)."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(default="", description="https public URL (Phase C SSRF gate)")
    events: list[str] = Field(
        default_factory=list,
        description="Subset of item.created|item.enriched|webset.idle|webset.failed",
    )


class WebsetEnrichmentRequest(BaseModel):
    """Request body for POST /v1/websets/{webset_id}/enrichments."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    type: Literal["text", "number", "date", "url", "email", "phone", "options", "company_profile"]
    description: str = ""
    options: list[str] = Field(default_factory=list)

    def to_definition(self) -> EnrichmentDef:
        """Build the T1 def (raises ``ValidationError`` on invalid options usage)."""
        return EnrichmentDef(
            name=self.name, type=self.type, description=self.description, options=self.options
        )


@app.post("/v1/websets", status_code=202, response_model=None)
def api_create_webset(req: WebsetCreateRequest, request: Request) -> dict[str, Any] | JSONResponse:
    """Create a webset + initial search; the run is scheduled and 202 returns."""
    try:
        webset = websets_service.create_webset(
            query=req.query,
            count=req.count,
            criteria=req.criteria,
            enrichments=req.enrichments,
            verification_mode=req.verification_mode,
            workspace_id=req.workspace_id,
        )
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    except ValidationError as exc:
        return _webset_error(request, 422, "validation_error", str(exc))
    return webset.model_dump(mode="json")


@app.get("/v1/websets/{webset_id}", response_model=None)
def api_get_webset(webset_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """Load one webset (status + search generations + enrichment defs)."""
    try:
        webset = websets_service.get_webset(webset_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return webset.model_dump(mode="json")


@app.post("/v1/websets/{webset_id}/searches", status_code=202, response_model=None)
def api_add_webset_search(
    webset_id: str, req: WebsetSearchRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Attach a follow-up search generation (async; 202 returns status=running)."""
    try:
        search = websets_service.add_search(
            webset_id, query=req.query, count=req.count, criteria=req.criteria
        )
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    except ValidationError as exc:
        return _webset_error(request, 422, "validation_error", str(exc))
    return search.model_dump(mode="json")


@app.get("/v1/websets/{webset_id}/items", response_model=None)
def api_list_webset_items(
    webset_id: str,
    request: Request,
    verification: Literal["verified", "rejected", "pending"] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any] | JSONResponse:
    """Page items NEWEST-first (R11); ``cursor`` is the previous page's last item id."""
    try:
        items, next_cursor = websets_service.list_items(
            webset_id, verification=verification, limit=limit, cursor=cursor
        )
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "next_cursor": next_cursor,
    }


@app.post("/v1/websets/{webset_id}/enrichments", status_code=201, response_model=None)
def api_add_webset_enrichment(
    webset_id: str, req: WebsetEnrichmentRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Attach an enrichment def (max 10 active; 11th → 400 enrichment_limit_exceeded)."""
    try:
        definition = req.to_definition()
        attached = websets_service.add_enrichment(webset_id, definition)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    except ValidationError as exc:
        return _webset_error(request, 422, "validation_error", str(exc))
    return attached.model_dump(mode="json")


@app.delete(
    "/v1/websets/{webset_id}/enrichments/{enrichment_id}",
    status_code=204,
    response_class=Response,
)
def api_remove_webset_enrichment(webset_id: str, enrichment_id: str, request: Request) -> Response:
    """Detach an enrichment; already-resolved item values are retained."""
    try:
        websets_service.remove_enrichment(webset_id, enrichment_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return Response(status_code=204)


@app.post("/v1/websets/{webset_id}/monitors", status_code=201, response_model=None)
def api_create_webset_monitor(
    webset_id: str, req: WebsetMonitorRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Record a poll-only refresh cadence on a webset (never a Phase C Watch)."""
    try:
        monitor = websets_service.create_monitor(
            webset_id, interval_seconds=req.interval_seconds, webhook_url=req.webhook_url
        )
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return monitor.model_dump(mode="json")


@app.get("/v1/websets/{webset_id}/monitors", response_model=None)
def api_list_webset_monitors(webset_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """List a webset's monitors newest-created first."""
    try:
        monitors = websets_service.list_monitors(webset_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return {"monitors": [monitor.model_dump(mode="json") for monitor in monitors]}


@app.post(
    "/v1/websets/{webset_id}/monitors/{monitor_id}/trigger", status_code=202, response_model=None
)
def api_trigger_webset_monitor(
    webset_id: str, monitor_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    """Manual refresh: open a new search generation (the v1 tick-driver substitute)."""
    try:
        webset = websets_service.trigger_monitor(webset_id, monitor_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return webset.model_dump(mode="json")


@app.get("/v1/websets/{webset_id}/events", response_model=None)
def api_list_webset_events(
    webset_id: str,
    request: Request,
    after: str | None = None,
    limit: int = 50,
) -> dict[str, Any] | JSONResponse:
    """Page the append-only event log OLDEST-first; ``after`` is the last seen event id."""
    try:
        events, next_cursor = websets_service.list_events(webset_id, after=after, limit=limit)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return {
        "events": [event.model_dump(mode="json") for event in events],
        "next_cursor": next_cursor,
    }


@app.post("/v1/websets/{webset_id}/webhooks", status_code=201, response_model=None)
def api_add_webset_webhook(
    webset_id: str, req: WebsetWebhookRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """Register a webhook; the server-generated secret appears in this response only.

    An unknown ``events`` kind is caller input: ``WebsetWebhookRequest.events`` is
    ``list[str]`` while ``WebhookConfig.events`` is ``list[EventKind]``, so the
    service's pydantic ``ValidationError`` maps to 422 here (the sibling routes'
    ``validation_error`` envelope) instead of escaping into the generic 500.
    """
    try:
        webhook = websets_service.add_webhook(webset_id, url=req.url, events=req.events)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    except ValidationError as exc:
        return _webset_error(request, 422, "validation_error", str(exc))
    return webhook.model_dump(mode="json")


@app.post("/v1/websets/{webset_id}/webhooks/{webhook_id}/rotate", response_model=None)
def api_rotate_webset_webhook(
    webset_id: str, webhook_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    """Rotate the webhook secret with a 24h overlap; returns the NEW secret once."""
    try:
        webhook = websets_service.rotate_webhook_secret(webset_id, webhook_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return webhook.model_dump(mode="json")


@app.post("/v1/websets/{webset_id}/cancel", response_model=None)
def api_cancel_webset(webset_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """Cancel a webset; the runner settles every non-terminal search ``cancelled``."""
    try:
        webset = websets_service.cancel_webset(webset_id)
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    return webset.model_dump(mode="json")


@app.get("/v1/websets/{webset_id}/export", response_model=None)
def api_export_webset(
    webset_id: str, request: Request, format: str = "json"
) -> Response | JSONResponse:
    """Export verified items as CSV (polars) or JSON (per-field citations retained)."""
    try:
        content, media_type = websets_service.export_webset(webset_id, fmt=format.strip().lower())
    except WebsetServiceError as exc:
        return _webset_service_error(request, exc)
    except ValueError as exc:
        return _webset_error(request, 422, "validation_error", str(exc))
    filename = f"{webset_id}.{'csv' if media_type == 'text/csv' else 'json'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


register_fastapi_error_handlers(app, service="digisearch")
setup_otel_fastapi(app, service_name="digisearch", service_version=__version__)
