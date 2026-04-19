"""DigiGraph HTTP API. Phase 0: run_digigraph_workflow. Phase 1+: LangGraph + MCP."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from queue import Queue
from threading import Thread

logger = logging.getLogger(__name__)

# Last N chat completion request summaries for debugging (inspect input messages).
_DEBUG_REQUEST_LOG: list[dict] = []
_DEBUG_REQUEST_LOG_MAX = 5

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from digibase.cors import install_cors, resolve_cors_origins
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware, digigraph_path_scopes
from digigraph.formatters import get_stream_formatter
from digigraph.llm import chat_completion, get_model_for_mode
from digigraph.models import ChatCompletionRequest, WorkflowRequest, WorkflowResult
from digigraph.policy import debug_endpoints_enabled, thread_api_enabled
from digigraph.workflow import run_digigraph_workflow, run_digigraph_workflow_streaming


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
    title="DigiGraph",
    description="Orchestration brain: run_digigraph_workflow (DigiClaw custom skill)",
    version="0.1.0",
)
install_metrics(app, service="digigraph")
install_cors(app, service="digigraph")
app.add_middleware(DigiAuthMiddleware, service="digigraph", path_scopes=digigraph_path_scopes)


@app.middleware("http")
async def lite_llm_proxy_header_context(request: Request, call_next):
    """Apply per-request LiteLLM Bearer from X-LiteLLM-Proxy-Key (DigiKey funnel via DigiChat)."""
    from digigraph.llm import pop_lite_llm_proxy, push_lite_llm_proxy_header

    tok = push_lite_llm_proxy_header(request)
    try:
        return await call_next(request)
    finally:
        pop_lite_llm_proxy(tok)


from digigraph.rate_limit import RateLimiter as _RateLimiter

_rate_limiter = _RateLimiter()
# Expensive endpoints: 10 req/min. Ingest/query: 30 req/min. Health: unlimited.
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/workflow": (10, 60),
    "/v1/chat/completions": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health", "/healthz"}


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


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    """Propagate X-Request-ID header; generate one if absent; expose on request.state."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# OpenAI-compatible API (expose DigiGraph as a model in Open WebUI)
v1 = APIRouter(prefix="/v1", tags=["openai-compatible"])


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check for Docker and DigiClaw (kept for back-compat)."""
    return {"status": "ok", "service": "digigraph"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Contract: returns HTTP 200 with ``{"ok": true}``. Intended for load
    balancers and k8s probes. For richer diagnostics, see DigiSmith's
    ``/v1/status``.
    """
    return {"ok": True}


def _digi_fields_from_request(http_request: Request) -> dict[str, str | None]:
    bearer = getattr(http_request.state, "digi_bearer", None)
    auth = getattr(http_request.state, "digi_auth", None)
    updates: dict[str, str | None] = {"digi_bearer": bearer}
    if auth is not None:
        if auth.key_prefix:
            updates["digi_trace_key_prefix"] = auth.key_prefix
        if auth.tenant_slug:
            updates["digi_trace_tenant"] = auth.tenant_slug
        if auth.project_id:
            updates["digi_trace_project_id"] = auth.project_id
        if auth.jti:
            updates["digi_trace_jti"] = auth.jti
    return updates


def _with_digi_request_context(http_request: Request, req: WorkflowRequest) -> WorkflowRequest:
    return req.model_copy(update=_digi_fields_from_request(http_request))


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
    Test DigiGraph → LiteLLM → Ollama (or configured provider).
    Same code path as workflow research node; no backtest.
    """
    try:
        model = get_model_for_mode()
        reply = chat_completion(
            model,
            [{"role": "user", "content": "Reply with exactly: OK"}],
        )
        return {"ok": True, "model": model, "reply": reply or "(empty)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "model": "", "reply": "", "error": str(e)}


def _resolve_request_id(request: Request) -> str | None:
    """HTTP request id from middleware (request.state) or X-Request-ID header."""
    rid = getattr(request.state, "request_id", None)
    if rid and str(rid).strip():
        return str(rid).strip()
    h = (request.headers.get("X-Request-ID") or "").strip()
    return h or None


@app.post("/workflow", response_model=WorkflowResult, operation_id="run_digigraph_workflow")
def api_run_digigraph_workflow(http_request: Request, req: WorkflowRequest) -> WorkflowResult:
    """
    DigiClaw custom skill: run_digigraph_workflow.
    Phase 0: user idea → backtest via DigiQuant → result in < 10s.
    """
    rid = _resolve_request_id(http_request)
    if rid and not (req.request_id and str(req.request_id).strip()):
        req = req.model_copy(update={"request_id": rid})
    req = _with_digi_request_context(http_request, req)
    return run_digigraph_workflow(req)


# --- Thread state (LangGraph get_state) ---

# Keys we expose from checkpointed state (exclude stream_callback and other internals).
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
def get_thread_state(thread_id: str, checkpoint_id: str | None = None):
    """
    Return current (or specified) checkpoint state for a thread.
    Requires a checkpointer (default: memory when DIGI_CHECKPOINTER unset). Returns stored_datasets, research_response, error, etc.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config: dict = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = checkpoint_id
    try:
        snapshot = graph.get_state(config)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
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
def get_thread_history(thread_id: str):
    """
    Return checkpoint history for a thread (debug). Most recent first.
    Requires a checkpointer. Each entry is a safe subset of state values.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        history = list(graph.get_state_history(config))
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
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
def resume_thread(thread_id: str, body: dict | None = None):
    """
    Resume a thread that was interrupted (e.g. after research when DIGI_INTERRUPT_AFTER_RESEARCH=1).
    Optional body: {"resume": <value>} passed to LangGraph Command(resume=...). Same graph config required.
    """
    from digigraph.graph import build_workflow_graph

    graph = build_workflow_graph()
    config = {"configurable": {"thread_id": thread_id}}
    resume_value = (body or {}).get("resume") if isinstance(body, dict) else None
    try:
        if resume_value is not None:
            try:
                from langgraph.types import Command

                result = graph.invoke(Command(resume=resume_value), config=config)
            except ImportError:
                result = graph.invoke(None, config=config)
        else:
            result = graph.invoke(None, config=config)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    return {"thread_id": thread_id, "values": _safe_state_values(result)}


# --- OpenAI-compatible (expose as model in Open WebUI) ---


@v1.get("/model-info")
def model_info() -> dict:
    """Return the LLM model used for Sitaas RAG completions. Use to validate config."""
    from digigraph.llm import get_model_for_mode

    mode = os.environ.get("DIGI_LLM_MODE", "test")
    try:
        from digigraph.project_config import DigiProjectConfig

        cfg = DigiProjectConfig.load()
        mode = cfg.get_llm_mode() or mode
    except Exception:
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
    except Exception:  # noqa: BLE001
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
    """List available models. Open WebUI discovers sitaas-rag here."""
    return {
        "object": "list",
        "data": [
            {
                "id": "sitaas-rag",
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
) -> str:
    """One SSE data line for chat.completion.chunk. Optionally include reasoning_content or digigraph_trace in delta."""
    delta: dict = {}
    if content:
        delta["content"] = content
    if reasoning_content:
        delta["reasoning_content"] = reasoning_content
    if digigraph_trace is not None:
        delta["digigraph_trace"] = digigraph_trace
    if finish_reason is not None:
        if not content and not reasoning_content and digigraph_trace is None:
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
    request_id: str | None = None,
    workflow_extras: dict | None = None,
):
    """
    Generator: run workflow in thread, consume queue, yield SSE deltas.
    Format of tool_call and tool_result is determined by formatter (openwebui_format → Open WebUI <details>/tables; else neutral).
    session_id isolates digistore and checkpoint state per conversation when provided by the client.
    """
    formatter = get_stream_formatter(openwebui_format)
    event_queue: Queue = Queue()
    wf_kw: dict = {
        "prompt": prompt,
        "session_id": session_id,
        "allowed_tools": allowed_tools,
        "request_id": request_id,
    }
    if workflow_extras:
        wf_kw.update(workflow_extras)
    workflow_req = WorkflowRequest(**wf_kw)
    thread = Thread(target=run_digigraph_workflow_streaming, args=(workflow_req, event_queue))
    thread.start()

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
            ev = event_queue.get()
            event_type = ev[0]
            data = ev[1] if len(ev) > 1 else None

            if event_type == "done":
                thinking_block = flush_reasoning_as_thinking()
                if thinking_block:
                    yield f"data: {_sse_chunk(cid, created, model, thinking_block, None)}\n\n"
                break
            if event_type == "tool_call":
                pending_tool_calls.append(data or {})
            elif event_type == "tool_result":
                call_data = pending_tool_calls.pop(0) if pending_tool_calls else {}
                content = formatter.format_tool_call_with_result(call_data, data or {})
                yield f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"
            elif event_type == "reasoning":
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
            elif event_type == "content":
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
    except Exception as e:
        logger.exception("stream_completions error")
        yield f"data: {_sse_chunk(cid, created, model, f'Error: {e!s}', None)}\n\n"

    yield f"data: {_sse_chunk(cid, created, model, '', 'stop')}\n\n"
    yield "data: [DONE]\n\n"


def _resolve_openwebui_format(req: ChatCompletionRequest, request: Request) -> bool:
    """True when client requests Open WebUI format: header X-Response-Format: openwebui, or openwebui_format=true, or model=sitaas-rag."""
    if getattr(req, "openwebui_format", False):
        return True
    if (getattr(req, "model", "") or "").strip().lower() == "sitaas-rag":
        return True
    header = (request.headers.get("X-Response-Format") or "").strip().lower()
    return header == "openwebui"


def _resolve_allowed_tools_chat(req: ChatCompletionRequest, request: Request) -> list[str] | None:
    """Tool allowlist from JSON body or X-Allowed-Tools header. None = use project config / DIGI_ALLOWED_TOOLS."""
    if req.allowed_tools is not None:
        return req.allowed_tools
    h = (request.headers.get("X-Allowed-Tools") or "").strip()
    if h:
        return [p.strip() for p in h.split(",") if p.strip()]
    return None


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
    To get Open WebUI–style tool blocks (<details>, markdown tables), send header X-Response-Format: openwebui (or openwebui_format=true, or model=sitaas-rag).
    """
    if not req.messages:
        content = "No messages provided."
        prompt = ""
    else:
        user_parts: list[str] = []
        for m in req.messages:
            if m.role == "user" and m.content:
                user_parts.append(m.content)
        prompt = "\n\n".join(user_parts) if user_parts else req.messages[-1].content or ""

    session_id = _resolve_session_id(req, request)
    allowed_tools = _resolve_allowed_tools_chat(req, request)
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
                request_id=request_id,
                workflow_extras=wf_extras,
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
            request_id=request_id,
        )
        result = run_digigraph_workflow(_with_digi_request_context(request, wf))
        content = result.message if result.success else f"Error: {result.message}"
    completion = _build_completion(req, content, prompt)
    return completion


app.include_router(v1)

register_fastapi_error_handlers(app, service="digigraph")
setup_otel_fastapi(app, service_name="digigraph")
