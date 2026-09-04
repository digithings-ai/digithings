"""digigraph HTTP API. Phase 0: run_digigraph_workflow. Phase 1+: LangGraph + MCP."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from queue import Empty, Queue
from threading import Event, Thread

from openai import OpenAIError

logger = logging.getLogger(__name__)

# Last N chat completion request summaries for debugging (inspect input messages).
_DEBUG_REQUEST_LOG: list[dict] = []
_DEBUG_REQUEST_LOG_MAX = 5

from digibase.cors import install_cors, resolve_cors_origins
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware, digigraph_path_scopes
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from digigraph import __version__
from digigraph.boundaries import GRAPH_RUNTIME_ERRORS, PROJECT_CONFIG_ERRORS, STREAM_SSE_ERRORS
from digigraph.chat_prompt import messages_to_workflow_prompt
from digigraph.formatters import get_stream_formatter
from digigraph.llm_client import completion_text
from digigraph.model_config import get_model_for_mode
from digigraph.models import (
    ChatCompletionRequest,
    ResumeThreadRequest,
    WorkflowRequest,
    WorkflowResult,
)
from digigraph.policy import debug_endpoints_enabled, thread_api_enabled
from digigraph.thread_scope import (
    assert_thread_access,
    auth_subject_from_request,
    resolve_client_thread_id,
    workflow_thread_id,
)
from digigraph.workflow import run_digigraph_workflow, run_digigraph_workflow_streaming

_LLM_PROBE_ERRORS = (
    OpenAIError,
    OSError,
    RuntimeError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)

_THREAD_GRAPH_ERRORS = GRAPH_RUNTIME_ERRORS


def _thread_error_response(e: Exception, request: Request | None = None) -> JSONResponse:
    return json_error_response(
        status_code=400,
        code="thread_error",
        message=str(e),
        request=request,
        service="digigraph",
    )


def _allowed_origins() -> list[str]:
    """Back-compat shim — resolves the digigraph CORS allowlist.

    Kept for older tests / external callers. New code should use
    :func:`digibase.cors.resolve_cors_origins`. Falls back to the historical
    localhost defaults when *nothing* is configured so legacy callers that
    expected a non-empty list continue to work.
    """
    origins = resolve_cors_origins("digigraph")
    if origins:
        return origins
    return ["http://localhost:3000", "http://localhost:8000", "http://localhost:11434"]


app = FastAPI(
    title="digigraph",
    description=(
        "Orchestration brain for digithings: LangGraph workflows, OpenAI-compatible chat, "
        "and federated vertical tools (digisearch, digiquant, digivault). "
        "Interactive docs: `/docs` (Swagger) and `/redoc`."
    ),
    version=__version__,
)
install_metrics(app, service="digigraph", version=__version__)
install_cors(app, service="digigraph")
app.add_middleware(DigiAuthMiddleware, service="digigraph", path_scopes=digigraph_path_scopes)


@app.middleware("http")
async def lite_llm_proxy_header_context(request: Request, call_next):
    """Apply per-request LiteLLM Bearer from X-LiteLLM-Proxy-Key (digikey funnel via digichat)."""
    from digigraph.llm_auth import pop_lite_llm_proxy, push_lite_llm_proxy_header

    tok = push_lite_llm_proxy_header(request)
    try:
        return await call_next(request)
    finally:
        pop_lite_llm_proxy(tok)


def _byok_default_routes_elsewhere(provider: str) -> bool:
    """True when this deployment's default model would bill someone other than *provider*.

    Resolution failures answer ``False`` rather than refusing. ``operator_default_model``
    raises in ``llm_mode: free`` without an explicit pin, and this middleware is not the
    place to convert a *server* misconfiguration into a 400 blaming the caller's key —
    the request proceeds and fails where it actually breaks.

    The billing invariant survives that open failure two ways, and which one applies
    turns on the *path*, not on which error was swallowed. On the mode path,
    ``get_model_for_mode`` evaluates ``operator_default_model()`` as the *argument* to
    ``_apply_byok_model_override``, so a failure that recurs re-raises before the
    resolver is ever entered — nothing is billed because the request fails, not because
    a second verdict was reached — while a merely transient one (``_LLM_PROBE_ERRORS``
    is wider than the free-mode ``ValueError``) lets the resolver judge the same string
    this function could not resolve. On the phase path, ``get_model_for_phase`` never
    calls ``operator_default_model`` at all: it hands the resolver a ``phase_models``
    override or an ``digiquant_models.yaml`` capability model, neither of which this
    middleware ever sees, and the resolver refuses on *that* string. Either way the
    refusal — or the failure — lands on whatever the request would actually have been
    billed for.
    """
    from digigraph.llm_auth import byok_operator_model_routes_elsewhere
    from digigraph.model_config import operator_default_model

    try:
        default_model = operator_default_model()
    except _LLM_PROBE_ERRORS:
        return False
    return byok_operator_model_routes_elsewhere(provider, default_model)


@app.middleware("http")
async def byok_header_context(request: Request, call_next):
    """Apply per-request BYOK user API key from X-BYOK-Key / X-BYOK-Provider (digichat BYOK flow).

    The key is bound to a ContextVar for the duration of the request only.
    It is never logged or persisted server-side. On each request the key
    overrides the LLM client credentials for that single execution.

    "Duration of the request" is bounded by ``pop_byok`` below for everything that
    runs in the request task. A streaming response outlives that: its worker thread
    holds a *copy* of this context, which ``pop_byok`` cannot reach, and clears its
    own copy in its ``finally`` instead (see ``_stream_completions_progressive``).
    """
    from digigraph.llm_auth import (
        BYOK_DEFAULT_MODEL_MISMATCH_CODE,
        BYOK_ROUTABLE_PROVIDERS,
        byok_default_model_refusal,
        byok_model_required,
        byok_model_routes_elsewhere,
        byok_provider_supported,
        pop_byok,
        push_byok_header,
    )

    if (request.headers.get("x-byok-key") or "").strip():
        provider = (request.headers.get("x-byok-provider") or "openai").strip().lower()
        if not byok_provider_supported(provider):
            return json_error_response(
                status_code=400,
                code="byok_provider_unsupported",
                message=(
                    f"BYOK provider {provider!r} is not routed by digigraph, so your key "
                    f"would not be used. Supported: {', '.join(BYOK_ROUTABLE_PROVIDERS)}."
                ),
                request=request,
                service="digigraph",
            )
        model = (request.headers.get("x-byok-model") or "").strip()
        if byok_model_required(provider) and not model:
            return json_error_response(
                status_code=400,
                code="byok_model_required",
                message=(
                    f"BYOK provider {provider!r} requires X-BYOK-Model "
                    "(e.g. openai/gpt-4o-mini, gemini/gemini-2.5-flash, claude-sonnet-4-6)."
                ),
                request=request,
                service="digigraph",
            )
        if not model and _byok_default_routes_elsewhere(provider):
            # A key with no model is not a request to use the operator's default: the
            # default is *this deployment's* string, so if it names a registered
            # provider digillm bills that provider's env key and the pasted key is
            # accepted, shown active, and never spent. Same invariant as the mismatch
            # below, reached by omission rather than by input. Refusing beats
            # substituting a model the caller did not choose (see #2490).
            return json_error_response(
                status_code=400,
                code=BYOK_DEFAULT_MODEL_MISMATCH_CODE,
                message=byok_default_model_refusal(provider),
                request=request,
                service="digigraph",
            )
        if model and byok_model_routes_elsewhere(provider, model):
            # Not a typo-catcher: this is the same billing invariant as the
            # unsupported-provider refusal above. A model naming another registered
            # provider is served by that provider's client on the *operator's* env
            # key, so the pasted key is accepted, shown as active, and never spent.
            # Refuse instead of silently answering on the wrong credential.
            return json_error_response(
                status_code=400,
                code="byok_model_provider_mismatch",
                message=(
                    f"X-BYOK-Model names a provider other than {provider!r}, so your key "
                    "would not be the one billed. Send a model for the provider you "
                    "declared in X-BYOK-Provider."
                ),
                request=request,
                service="digigraph",
            )

    tok = push_byok_header(request)
    try:
        return await call_next(request)
    finally:
        pop_byok(tok)


from digigraph.rate_limit import RateLimiter as _RateLimiter

_rate_limiter = _RateLimiter()
# Expensive endpoints: 10 req/min. Ingest/query: 30 req/min. Health: unlimited.
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/workflow": (10, 60),
    "/v1/chat/completions": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health", "/healthz"}

# A request/header-level `require_tool_calls=true` (see _resolve_require_tool_calls_chat)
# forces tool_choice="required", which reliably exhausts all max_tool_rounds completions
# instead of returning after one -- a ~4-5x LLM-spend multiplier any caller holding plain
# digigraph:chat scope can opt into per request (the deployment-mandated floor is separate
# and not what this limits). Give that class of request its own, stricter budget on top of
# the general per-path limit above; both checks apply and either can 429 the request.
_require_tool_calls_limiter = _RateLimiter()
_REQUIRE_TOOL_CALLS_RATE_LIMIT: tuple[int, int] = (
    int(os.environ.get("DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX", "3")),
    60,
)


def _enforce_require_tool_calls_budget(
    require_tool_calls: bool | None, request: Request
) -> JSONResponse | None:
    """429 if this IP is over budget for `require_tool_calls=true` requests.

    Only requests that actually opt into the escalation (see
    _resolve_require_tool_calls_chat) are metered here -- a deployment that mandates
    require_tool_calls itself via project config / DIGI_REQUIRE_TOOL_CALLS has already
    accepted that cost for every request and isn't what this budget defends against.
    """
    if not require_tool_calls:
        return None
    max_req, window = _REQUIRE_TOOL_CALLS_RATE_LIMIT
    return _require_tool_calls_limiter.check(request, max_req, window)


@app.middleware("http")
async def gated_sensitive_endpoints(request: Request, call_next):
    """Opt-in exposure for debug and thread/file APIs (defaults off). Set DIGI_ENABLE_DEBUG_ENDPOINTS=1 and DIGI_ENABLE_THREAD_API=1 for local/dev; production compose sets these as needed."""
    path = request.url.path
    if path == "/test_llm" or path.startswith("/v1/debug"):
        if not debug_endpoints_enabled():
            return json_error_response(
                status_code=404,
                code="endpoint_disabled",
                message="Debug endpoints are disabled. Set DIGI_ENABLE_DEBUG_ENDPOINTS=1.",
                request=request,
                service="digigraph",
            )
    if path.startswith("/threads/") or path.startswith("/files/"):
        if not thread_api_enabled():
            return json_error_response(
                status_code=404,
                code="endpoint_disabled",
                message="Thread API is disabled. Set DIGI_ENABLE_THREAD_API=1.",
                request=request,
                service="digigraph",
            )
    return await call_next(request)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP rate limiting. Limits vary by endpoint (see _RATE_LIMITS)."""
    path = request.url.path
    if path not in _UNLIMITED_PATHS:
        max_req, window = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        result = _rate_limiter.check(request, max_req, window)
        if result is not None:
            return result
    return await call_next(request)


install_request_id_middleware(app)
install_request_id_logging()


# OpenAI-compatible API (expose digigraph as a model in Open WebUI)
v1 = APIRouter(prefix="/v1", tags=["openai-compatible"])


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check for Docker and digiclaw (kept for back-compat)."""
    return {"status": "ok", "service": "digigraph"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Contract: returns HTTP 200 with ``{"ok": true}``. Intended for load
    balancers and k8s probes. For richer diagnostics, see digismith's
    ``/v1/status``.
    """
    return {"ok": True}


def _digi_fields_from_request(http_request: Request) -> dict[str, str | None]:
    from digigraph.corpus_routing import (
        TenantCorpusMapError,
        load_tenant_corpus_map,
        resolve_corpus_override,
    )

    bearer = getattr(http_request.state, "digi_bearer", None)
    auth = getattr(http_request.state, "digi_auth", None)
    updates: dict[str, str | None] = {"digi_bearer": bearer}
    # digi_subject keys the cross-thread Store namespace (supervisor_node,
    # ARCHITECTURE.md §6.10) and, via workflow_thread_id, the checkpoint thread_id — so
    # it must NEVER survive from a client-supplied WorkflowRequest.digi_subject unless
    # backed by verified auth (CWE-639 IDOR). This key must always be present in
    # `updates` (never merely omitted): `req.model_copy(update=updates)` in
    # _with_digi_request_context only clears a field when its key is explicitly present
    # here — an absent key leaves the client's original value untouched. So this is an
    # unconditional assignment, not a conditional override: it sets the verified
    # `auth.subject` when `auth` is present and its `subject` claim is non-empty, and
    # explicitly `None` in every other case — no `auth` object at all, OR an `auth`
    # object present with an empty/falsy `subject` claim. Both are real overrides, not
    # skips, because the key is always present.
    updates["digi_subject"] = auth.subject if (auth is not None and auth.subject) else None
    tenant_from_auth: str | None = None
    if auth is not None:
        if auth.key_prefix:
            updates["digi_trace_key_prefix"] = auth.key_prefix
        if auth.tenant_slug:
            updates["digi_trace_tenant"] = auth.tenant_slug
            tenant_from_auth = auth.tenant_slug
        if auth.project_id:
            updates["digi_trace_project_id"] = auth.project_id
        if auth.jti:
            updates["digi_trace_jti"] = auth.jti
    # Mirror digivault tenant_scope: set-but-broken DIGI_TENANT_CORPUS_MAP is 503,
    # never silently treated as unset (which would re-enable client corpus headers).
    try:
        corpus_map = load_tenant_corpus_map()
    except TenantCorpusMapError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    corpus = resolve_corpus_override(
        headers=http_request.headers,
        tenant_slug=tenant_from_auth,
        corpus_map=corpus_map,
    )
    # Same CWE-639 class as digi_subject: when DIGI_TENANT_CORPUS_MAP is configured,
    # digisearch_index / vault_path_prefix / research_system_prompt_override must be
    # written unconditionally so a client body value cannot survive into graph state
    # (digisearch has no server-side tenant→index bind; digivault does for prefixes).
    if corpus_map:
        updates["digisearch_index"] = corpus.digisearch_index
        updates["vault_path_prefix"] = corpus.vault_path_prefix
        updates["research_system_prompt_override"] = corpus.research_system_prompt
    else:
        if corpus.digisearch_index:
            updates["digisearch_index"] = corpus.digisearch_index
        if corpus.vault_path_prefix:
            updates["vault_path_prefix"] = corpus.vault_path_prefix
        if corpus.research_system_prompt:
            updates["research_system_prompt_override"] = corpus.research_system_prompt
    # Per-request response language (X-Digi-Language) — a per-request signal, not a
    # tenant-derived value, so it's read directly rather than via resolve_corpus_override.
    # Never interpolated into a prompt (resolve_language_directive only ever emits
    # mapped display names for curated 2-char codes), but capped defensively before
    # it reaches WorkflowRequest/checkpointed state — an arbitrarily long header value
    # has no business sitting in checkpoint storage. Curated codes are 2 characters,
    # so 16 is generous headroom, not a functional constraint.
    lang = http_request.headers.get("x-digi-language")
    if lang and lang.strip():
        updates["response_language"] = lang.strip().lower()[:16]
    from digigraph.retrieval import resolve_force_tool

    force_raw = http_request.headers.get("x-digi-force-tool")
    resolved_force = resolve_force_tool(force_raw)
    if resolved_force:
        updates["force_tool"] = resolved_force
    return updates


def _with_digi_request_context(http_request: Request, req: WorkflowRequest) -> WorkflowRequest:
    updates = _digi_fields_from_request(http_request)
    subject = updates.get("digi_subject")
    if subject:
        updates["session_id"] = workflow_thread_id(subject, req.session_id)
    return req.model_copy(update=updates)


def _thread_config(http_request: Request, thread_id: str) -> dict:
    subject = auth_subject_from_request(http_request)
    scoped = resolve_client_thread_id(subject, thread_id)
    assert_thread_access(subject, scoped)
    return {"configurable": {"thread_id": scoped}}


@v1.get("/debug/input_messages")
def debug_input_messages() -> dict:
    """
    Return the last few chat completion request summaries (message count, content lengths, prompt preview).
    Use to inspect what the client is sending when debugging context or empty responses.
    """
    return {"requests": list(_DEBUG_REQUEST_LOG)}


def _serve_run_data_file(path: str) -> FileResponse | dict:
    """Serve a file under run_data_dir. path is relative (e.g. default/export.csv). Returns 404 dict if disabled or invalid."""
    from pathlib import Path

    from digigraph.path_utils import assert_safe_path
    from digigraph.run_storage import get_run_data_dir

    root = get_run_data_dir()
    if not root:
        return {"detail": "File serving disabled (run_data_dir not set)"}
    base = Path(root).resolve()
    clean = path.strip().lstrip("/")
    try:
        full = assert_safe_path(base, clean, label="file path")
    except ValueError:
        return {"detail": "Invalid path"}
    if not full.is_file():
        return {"detail": "File not found"}
    return FileResponse(full, filename=full.name, media_type="application/octet-stream")


@app.get("/files/{path:path}")
def serve_file(path: str):
    """
    Serve exported files (CSV, JSON, Parquet) from run_data_dir.
    Path is relative to run_data_dir (e.g. default/export.csv). Only files under run_data_dir are allowed.
    """
    result = _serve_run_data_file(path)
    if isinstance(result, dict):
        return JSONResponse(status_code=404, content=result)
    return result


@app.get("/test_llm")
def test_llm() -> dict[str, str | bool]:
    """
    Test digigraph → LiteLLM → Ollama (or configured provider).
    Same code path as workflow research node; no backtest.
    """
    try:
        model = get_model_for_mode()
        reply = completion_text(
            model,
            [{"role": "user", "content": "Reply with exactly: OK"}],
        )
        return {"ok": True, "model": model, "reply": reply or "(empty)"}
    except _LLM_PROBE_ERRORS as e:
        return {"ok": False, "model": "", "reply": "", "error": str(e)}


def _resolve_request_id(request: Request) -> str | None:
    """HTTP request id from middleware (request.state) or X-Request-ID header."""
    rid = getattr(request.state, "request_id", None)
    if rid and str(rid).strip():
        return str(rid).strip()
    h = (request.headers.get("X-Request-ID") or "").strip()
    return h or None


@app.post(
    "/workflow",
    response_model=WorkflowResult,
    operation_id="run_digigraph_workflow",
    summary="Run digigraph workflow",
)
def api_run_digigraph_workflow(http_request: Request, req: WorkflowRequest) -> WorkflowResult:
    """
    digiclaw custom skill: run_digigraph_workflow.
    Phase 0: user idea → backtest via digiquant → result in < 10s.
    """
    # WorkflowRequest.require_tool_calls is body-only (no X-Require-Tool-Calls header,
    # unlike ChatCompletionRequest -- see models.py), but it reaches the identical
    # tool_choice="required" spend-amplification path via require_tool_calls_for_workflow,
    # so it needs the same dedicated budget as /v1/chat/completions (#2361 finding 7 gap).
    limited = _enforce_require_tool_calls_budget(req.require_tool_calls, http_request)
    if limited is not None:
        return limited
    rid = _resolve_request_id(http_request)
    if rid and not (req.request_id and str(req.request_id).strip()):
        req = req.model_copy(update={"request_id": rid})
    req = _with_digi_request_context(http_request, req)
    return run_digigraph_workflow(req)


# --- Thread state (LangGraph get_state) ---

# Keys we expose from checkpointed state (exclude digi_bearer and other internals;
# streaming now goes through LangGraph's native get_stream_writer(), so there is no
# stream_callback state key to exclude anymore -- see graph/research.py's
# _safe_stream_writer()).
_THREAD_STATE_KEYS = (
    "stored_datasets",
    "research_response",
    "research_note",
    "error",
    "backtest_result",
    "strategy_name",
    "symbols",
)


def _safe_state_values(values: dict | None) -> dict:
    """Return a subset of state values safe for API response."""
    if not values:
        return {}
    return {k: values[k] for k in _THREAD_STATE_KEYS if k in values}


@app.get("/threads/{thread_id}/state")
def get_thread_state(http_request: Request, thread_id: str, checkpoint_id: str | None = None):
    """
    Return current (or specified) checkpoint state for a thread.
    Requires a checkpointer (default: memory when DIGI_CHECKPOINTER unset). Returns stored_datasets, research_response, error, etc.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config: dict = _thread_config(http_request, thread_id)
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = checkpoint_id
    try:
        snapshot = graph.get_state(config)
    except _THREAD_GRAPH_ERRORS as e:
        return _thread_error_response(e, http_request)
    if snapshot is None:
        return {"thread_id": thread_id, "values": {}, "next": ()}
    values = getattr(snapshot, "values", None) or {}
    return {
        "thread_id": thread_id,
        "values": _safe_state_values(values),
        "next": getattr(snapshot, "next", ()),
        "metadata": getattr(snapshot, "metadata", None),
    }


@app.get("/threads/{thread_id}/history")
def get_thread_history(http_request: Request, thread_id: str):
    """
    Return checkpoint history for a thread (debug). Most recent first.
    Requires a checkpointer. Each entry is a safe subset of state values.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config = _thread_config(http_request, thread_id)
    try:
        history = list(graph.get_state_history(config))
    except _THREAD_GRAPH_ERRORS as e:
        return _thread_error_response(e, http_request)
    out = []
    for snapshot in history:
        out.append(
            {
                "values": _safe_state_values(
                    snapshot.values if hasattr(snapshot, "values") else None
                ),
                "next": getattr(snapshot, "next", ()),
                "metadata": getattr(snapshot, "metadata", None),
                "created_at": getattr(snapshot, "created_at", None),
            }
        )
    return {"thread_id": thread_id, "history": out}


@app.post("/threads/{thread_id}/resume")
def resume_thread(http_request: Request, thread_id: str, body: ResumeThreadRequest | None = None):
    """
    Resume a thread that was interrupted (e.g. after research when DIGI_INTERRUPT_AFTER_RESEARCH=1).
    Optional body: {"resume": <value>} passed to LangGraph Command(resume=...). Same graph config required.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config = _thread_config(http_request, thread_id)
    resume_value = body.resume if body is not None else None
    try:
        if resume_value is not None:
            try:
                from langgraph.types import Command

                result = graph.invoke(Command(resume=resume_value), config=config)
            except ImportError:
                result = graph.invoke(None, config=config)
        else:
            result = graph.invoke(None, config=config)
    except _THREAD_GRAPH_ERRORS as e:
        return _thread_error_response(e, http_request)
    return {"thread_id": thread_id, "values": _safe_state_values(result)}


# --- OpenAI-compatible (expose as model in Open WebUI) ---


@v1.get("/model-info")
def model_info() -> dict:
    """Return the LLM model used for Project RAG completions. Use to validate config."""
    from digigraph.model_config import get_model_for_mode

    mode = os.environ.get("DIGI_LLM_MODE", "test")
    try:
        from digigraph.project_config import DigiProjectConfig

        cfg = DigiProjectConfig.load()
        mode = cfg.get_llm_mode() or mode
    except PROJECT_CONFIG_ERRORS:
        pass
    model = get_model_for_mode()
    return {"model": model, "mode": mode, "base_url": os.environ.get("OPENAI_API_BASE", "")}


@v1.get("/status")
def status() -> dict:
    """Public project status. Secret-free: never exposes filesystem paths, URLs, or env-var values.

    Fields surface the subset of the resolved `DigiProjectConfig` safe for unauthenticated
    consumption (name, version, enabled agents, llm_mode, mcp.enabled, workflow_profile).
    Fresh read on every request (mtime-cached inside `DigiProjectConfig.load()`).
    """
    from digigraph.project_config import DigiProjectConfig

    try:
        cfg = DigiProjectConfig.load()
    except PROJECT_CONFIG_ERRORS:
        cfg = DigiProjectConfig({})
    project = cfg.project or {}
    return {
        "service": "digigraph",
        "project_name": str(project.get("name", "default")),
        "project_version": str(project.get("version", "0.0.0")),
        "agents_enabled": list(cfg.get_enabled_agents()),
        "llm_mode": cfg.get_llm_mode(),
        "mcp_enabled": bool(cfg.is_mcp_enabled()),
        "workflow_profile": cfg.get_workflow_profile(),
    }


@v1.get("/models")
def list_models() -> dict:
    """List available models. Open WebUI discovers digigraph-rag here."""
    return {
        "object": "list",
        "data": [
            {
                "id": "digigraph-rag",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "digigraph",
            }
        ],
    }


def _build_completion(req: ChatCompletionRequest, content: str, prompt: str) -> dict:
    """Build OpenAI-compatible completion response."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(content.split()),
            "total_tokens": len(prompt.split()) + len(content.split()),
            "estimated": True,
            "note": "Rough whitespace-split estimates; not provider-reported token counts.",
        },
    }


def _sse_chunk(
    cid: str,
    created: int,
    model: str,
    content: str,
    finish_reason: str | None = None,
    reasoning_content: str | None = None,
    digigraph_trace: dict | None = None,
    digigraph_error: dict | None = None,
) -> str:
    """One SSE data line for chat.completion.chunk. Optionally include reasoning_content or digigraph_trace in delta."""
    delta: dict = {}
    if content:
        delta["content"] = content
    if reasoning_content:
        delta["reasoning_content"] = reasoning_content
    if digigraph_trace is not None:
        delta["digigraph_trace"] = digigraph_trace
    if digigraph_error is not None:
        delta["digigraph_error"] = digigraph_error
    if finish_reason is not None:
        if (
            not content
            and not reasoning_content
            and digigraph_trace is None
            and digigraph_error is None
        ):
            delta = {}
    return json.dumps(
        {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
    )


def _sse_stream(completion: dict) -> str:
    """Emit SSE chunks for streaming. Single content chunk + finish + [DONE]."""
    cid = completion["id"]
    content = completion["choices"][0]["message"]["content"]
    created = completion["created"]
    model = completion["model"]
    return (
        f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"
        f"data: {_sse_chunk(cid, created, model, '', 'stop')}\n\n"
        "data: [DONE]\n\n"
    )


def _stream_completions_progressive(
    req: ChatCompletionRequest,
    prompt: str,
    session_id: str | None,
    openwebui_format: bool = False,
    allowed_tools: list[str] | None = None,
    require_tool_calls: bool | None = None,
    request_id: str | None = None,
    workflow_extras: dict | None = None,
    suppress_tool_stream: bool = False,
    force_tool: str | None = None,
    enable_web_search: bool = False,
):
    """
    Generator: run workflow in thread, consume queue, yield SSE deltas.
    Format of tool_call and tool_result is determined by formatter (openwebui_format → Open WebUI <details>/tables; else neutral).
    session_id isolates digistore and checkpoint state per conversation when provided by the client.
    """
    formatter = get_stream_formatter(openwebui_format)
    event_queue: Queue = Queue(maxsize=256)
    cancel_event = Event()
    wf_kw: dict = {
        "prompt": prompt,
        "session_id": session_id,
        "allowed_tools": allowed_tools,
        "require_tool_calls": require_tool_calls,
        "request_id": request_id,
        "enable_web_search": enable_web_search,
    }
    if workflow_extras:
        wf_kw.update(workflow_extras)
    # Resolved body-or-header force_tool wins over a header-only extras copy.
    wf_kw["force_tool"] = force_tool
    workflow_req = WorkflowRequest(**wf_kw)

    from digigraph.llm_auth import clear_byok_bindings

    # Run the worker inside a copy of *this* frame's context. A bare Thread starts
    # with an empty context, so every ContextVar bound per-request -- above all the
    # three BYOK bindings pushed by ``push_byok_header`` (digigraph's key/provider and
    # model overrides, plus digillm's own) -- reads as its default inside the worker.
    # Streaming BYOK requests were therefore answered on the *operator's* key while
    # the user's was shown as active: the same billing invariant the X-BYOK-Model
    # guard in ``byok_header_context`` refuses a whole request to protect. Copy at
    # spawn rather than re-binding inside the worker: this frame still holds the
    # bindings (measured), and the worker has no request to re-read them from.
    #
    # The copy outlives the request: this thread is neither daemonic nor joined, and
    # ``byok_header_context``'s ``finally`` runs ``pop_byok`` as soon as the response
    # starts streaming -- which resets the *parent's* vars only, a copy being a
    # snapshot rather than a view. So the worker clears its own copy when it finishes,
    # keeping the middleware's "for the duration of the request only" contract true of
    # the process and not just of the request task. The residual window is the worker's
    # own runtime, and that runtime is what has to stay bounded: every event the worker
    # emits goes through ``workflow._emit_event``, which drops rather than blocks once
    # ``cancel_event`` is set. A plain blocking ``put`` would not -- the queue above is
    # bounded and this generator stops draining it on disconnect, so the worker would
    # wedge inside a node, never reach the ``finally``, and strand the key for the
    # lifetime of the process rather than for one more node.
    ctx = contextvars.copy_context()

    def _run_worker() -> None:
        try:
            run_digigraph_workflow_streaming(workflow_req, event_queue, cancel_event)
        finally:
            clear_byok_bindings()

    worker = Thread(target=ctx.run, args=(_run_worker,))
    worker.start()

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = req.model
    pending_tool_calls: list[dict] = []
    reasoning_buffer: list[str] = []

    def flush_reasoning_as_thinking() -> str:
        """Emit reasoning buffer as a single <thinking> block for Open WebUI tag detection."""
        if not reasoning_buffer:
            return ""
        block = (
            "<thinking>\n" + "".join(str(x) for x in reasoning_buffer).strip() + "\n</thinking>\n\n"
        )
        reasoning_buffer.clear()
        return block

    try:
        while True:
            if cancel_event.is_set():
                break
            try:
                ev = event_queue.get(timeout=0.5)
            except Empty:
                continue
            event_type = ev[0]
            data = ev[1] if len(ev) > 1 else None

            if event_type == "done":
                if not suppress_tool_stream:
                    thinking_block = flush_reasoning_as_thinking()
                    if thinking_block:
                        yield f"data: {_sse_chunk(cid, created, model, thinking_block, None)}\n\n"
                else:
                    reasoning_buffer.clear()
                break
            if event_type == "tool_call":
                pending_tool_calls.append(data or {})
            elif event_type == "tool_result":
                if not suppress_tool_stream:
                    call_data = pending_tool_calls.pop(0) if pending_tool_calls else {}
                    content = formatter.format_tool_call_with_result(call_data, data or {})
                    yield f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"
                elif pending_tool_calls:
                    pending_tool_calls.pop(0)
            elif event_type == "reasoning":
                # digichat (and other non–Open WebUI clients) get activity via
                # digigraph_trace; never inject Open WebUI <thinking> chrome.
                if suppress_tool_stream:
                    continue
                if isinstance(data, str):
                    raw = data
                elif isinstance(data, dict):
                    raw = str((data.get("content") or data.get("delta") or ""))
                else:
                    raw = str(data) if data else ""
                if raw:
                    reasoning_buffer.append(raw)
                # Emit only as content later (<thinking> block); skip reasoning_content in delta to avoid breaking clients
            elif event_type == "trace":
                if isinstance(data, dict) and data:
                    yield (
                        f"data: {_sse_chunk(cid, created, model, '', None, digigraph_trace=data)}\n\n"
                    )
            elif event_type == "error":
                # Typed digichat contract (free_quota_exceeded / rate_limit) in delta.digigraph_error.
                if isinstance(data, dict) and data.get("code"):
                    yield (
                        f"data: {_sse_chunk(cid, created, model, '', None, digigraph_error=data)}\n\n"
                    )
            elif event_type == "content":
                if not suppress_tool_stream:
                    thinking_block = flush_reasoning_as_thinking()
                    if thinking_block:
                        yield f"data: {_sse_chunk(cid, created, model, thinking_block, None)}\n\n"
                raw = (
                    data
                    if isinstance(data, str)
                    else (data or {}).get("delta", (data or {}).get("content", ""))
                )
                content = (raw or "").replace("<", "&lt;").replace(">", "&gt;")
                if content:
                    yield f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"
    except GeneratorExit:
        cancel_event.set()
        raise
    except STREAM_SSE_ERRORS as e:
        logger.exception("stream_completions error")
        yield f"data: {_sse_chunk(cid, created, model, f'Error: {e!s}', None)}\n\n"
    finally:
        cancel_event.set()

    yield f"data: {_sse_chunk(cid, created, model, '', 'stop')}\n\n"
    yield "data: [DONE]\n\n"


def _resolve_suppress_tool_stream(request: Request) -> bool:
    """True when client wants tool-call markup omitted from SSE content (activity via digigraph_trace)."""
    header = (request.headers.get("X-Suppress-Tool-Stream") or "").strip().lower()
    return header in ("1", "true", "yes")


def _resolve_openwebui_format(req: ChatCompletionRequest, request: Request) -> bool:
    """True only when the client explicitly requests Open WebUI format.

    ``model=digigraph-rag`` alone does **not** enable ``<details>`` tool chrome
    (that id is the OpenAI-compat discovery name shared by digichat and Open WebUI).
    ``<thinking>`` chrome is separate: it is suppressed only by
    ``X-Suppress-Tool-Stream``, not by this flag.

    Enable with either:

    - ``X-Response-Format: openwebui``
    - ``openwebui_format=true`` in the JSON body

    Opt-outs still force off even if the body asks for Open WebUI:

    - ``X-Suppress-Tool-Stream: 1`` (digichat trace stream)
    - ``X-Response-Format: plain|neutral|none|digichat``
    """
    if _resolve_suppress_tool_stream(request):
        return False
    header = (request.headers.get("X-Response-Format") or "").strip().lower()
    if header in ("plain", "neutral", "none", "digichat"):
        return False
    if header == "openwebui":
        return True
    return bool(getattr(req, "openwebui_format", False))


def _resolve_allowed_tools_chat(req: ChatCompletionRequest, request: Request) -> list[str] | None:
    """Tool allowlist from JSON body or X-Allowed-Tools header. None = use project config / DIGI_ALLOWED_TOOLS."""
    if req.allowed_tools is not None:
        return req.allowed_tools
    h = (request.headers.get("X-Allowed-Tools") or "").strip()
    if h:
        return [p.strip() for p in h.split(",") if p.strip()]
    return None


def _resolve_require_tool_calls_chat(req: ChatCompletionRequest, request: Request) -> bool | None:
    """Per-request tool_choice='required' signal from JSON body or X-Require-Tool-Calls header.

    None = no request-level signal; the deployment-grain floor (project config /
    DIGI_REQUIRE_TOOL_CALLS) still applies downstream in require_tool_calls_for_workflow.
    """
    if req.require_tool_calls is not None:
        return req.require_tool_calls
    h = (request.headers.get("X-Require-Tool-Calls") or "").strip().lower()
    if h in ("1", "true", "yes"):
        return True
    if h in ("0", "false", "no"):
        return False
    return None


def _resolve_force_tool_chat(req: ChatCompletionRequest, request: Request) -> str | None:
    """Locate tool to inject from JSON body or X-Digi-Force-Tool. None = model-driven."""
    from digigraph.retrieval import resolve_force_tool

    return resolve_force_tool(req.force_tool) or resolve_force_tool(
        request.headers.get("X-Digi-Force-Tool")
    )


def _resolve_enable_web_search_chat(req: ChatCompletionRequest, request: Request) -> bool:
    """Opt-in digillm web search (#3420). Body or X-Digi-Enable-Web-Search; default off."""
    if req.enable_web_search:
        return True
    h = (request.headers.get("X-Digi-Enable-Web-Search") or "").strip().lower()
    return h in ("1", "true", "yes")


def _resolve_session_id(req: ChatCompletionRequest, request: Request) -> str | None:
    """Session id from body, then X-Session-Id, then X-Thread-Id. Ensures digistore/checkpoint are per-conversation when client sends it."""
    sid = getattr(req, "session_id", None)
    if sid and str(sid).strip():
        return str(sid).strip()
    sid = (request.headers.get("X-Session-Id") or request.headers.get("X-Thread-Id") or "").strip()
    return sid or None


def _chat_request_summary(
    req: ChatCompletionRequest,
    request: Request,
    prompt: str,
    session_id: str | None,
) -> dict:
    """Build a summary of the chat request for logging and debug endpoint."""
    total_content = sum(len(getattr(m, "content", "") or "") for m in req.messages)
    roles = [getattr(m, "role", "?") for m in req.messages]
    summary = {
        "messages_count": len(req.messages),
        "roles": roles,
        "total_content_chars": total_content,
        "prompt_len": len(prompt),
        "session_id": session_id or "(none → default)",
        "stream": req.stream,
        "prompt_preview": (prompt[:400] + "…") if len(prompt) > 400 else prompt,
    }
    return summary


def _log_and_store_request_summary(summary: dict) -> None:
    """Log request summary and keep last N for GET /v1/debug/input_messages."""
    logger.info(
        "chat/completions request: messages=%s total_content=%s prompt_len=%s session_id=%s",
        summary["messages_count"],
        summary["total_content_chars"],
        summary["prompt_len"],
        summary["session_id"],
    )
    global _DEBUG_REQUEST_LOG
    _DEBUG_REQUEST_LOG = [summary] + _DEBUG_REQUEST_LOG[: _DEBUG_REQUEST_LOG_MAX - 1]


@v1.post("/chat/completions")
def chat_completions(req: ChatCompletionRequest, request: Request):
    """
    OpenAI-compatible chat completions. Runs RAG workflow (LLM + search) and returns
    the response as a chat message. Use as a model in Open WebUI.
    When stream=true: progressive SSE with tool-call blocks then final answer.
    To get Open WebUI–style tool blocks (<details>, markdown tables), send header
    X-Response-Format: openwebui or body openwebui_format=true. model=digigraph-rag alone
    does not enable that chrome. digichat sends X-Suppress-Tool-Stream /
    X-Response-Format: plain as belt-and-suspenders; activity arrives via digigraph_trace.
    """
    if not req.messages:
        content = "No messages provided."
        prompt = ""
    else:
        prompt = messages_to_workflow_prompt(req.messages)

    session_id = _resolve_session_id(req, request)
    subject = auth_subject_from_request(request)
    if subject:
        session_id = workflow_thread_id(subject, session_id)
    allowed_tools = _resolve_allowed_tools_chat(req, request)
    require_tool_calls = _resolve_require_tool_calls_chat(req, request)
    enable_web_search = _resolve_enable_web_search_chat(req, request)
    limited = _enforce_require_tool_calls_budget(require_tool_calls, request)
    if limited is not None:
        return limited
    suppress_tool_stream = _resolve_suppress_tool_stream(request)
    openwebui_format = _resolve_openwebui_format(req, request)
    request_id = _resolve_request_id(request)

    summary = _chat_request_summary(req, request, prompt, session_id)
    _log_and_store_request_summary(summary)

    if req.stream:
        if not req.messages or not prompt:
            completion = _build_completion(req, content="No messages provided.", prompt="")
            return StreamingResponse(
                iter([_sse_stream(completion)]),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        wf_extras = {k: v for k, v in _digi_fields_from_request(request).items() if v is not None}
        return StreamingResponse(
            _stream_completions_progressive(
                req,
                prompt,
                session_id,
                openwebui_format=openwebui_format,
                allowed_tools=allowed_tools,
                require_tool_calls=require_tool_calls,
                request_id=request_id,
                workflow_extras=wf_extras,
                suppress_tool_stream=suppress_tool_stream,
                force_tool=_resolve_force_tool_chat(req, request),
                enable_web_search=enable_web_search,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    if not req.messages:
        content = "No messages provided."
    else:
        wf = WorkflowRequest(
            prompt=prompt,
            session_id=session_id,
            allowed_tools=allowed_tools,
            require_tool_calls=require_tool_calls,
            request_id=request_id,
            force_tool=_resolve_force_tool_chat(req, request),
            enable_web_search=enable_web_search,
        )
        result = run_digigraph_workflow(_with_digi_request_context(request, wf))
        if not result.success and result.error_code in ("free_quota_exceeded", "rate_limit"):
            from digigraph.llm_errors import FREE_QUOTA_EXCEEDED

            status = 429
            return json_error_response(
                status_code=status,
                code=result.error_code,
                message=result.message,
                request=request,
                service="digigraph",
                headers={
                    "X-Digigraph-Error-Code": result.error_code,
                    **({"Retry-After": "60"} if result.error_code == FREE_QUOTA_EXCEEDED else {}),
                },
            )
        content = result.message if result.success else f"Error: {result.message}"
    completion = _build_completion(req, content, prompt)
    return completion


app.include_router(v1)

register_fastapi_error_handlers(app, service="digigraph")
setup_otel_fastapi(app, service_name="digigraph")
