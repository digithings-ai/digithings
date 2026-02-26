"""DigiGraph HTTP API. Phase 0: run_digigraph_workflow. Phase 1+: LangGraph + MCP."""

from __future__ import annotations

import json
import os
import time
import uuid
from queue import Queue
from threading import Thread

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from digigraph.formatters import get_stream_formatter
from digigraph.llm import chat_completion, get_model_for_mode
from digigraph.models import ChatCompletionRequest, WorkflowRequest, WorkflowResult
from digigraph.workflow import run_digigraph_workflow, run_digigraph_workflow_streaming

app = FastAPI(
    title="DigiGraph",
    description="Orchestration brain: run_digigraph_workflow (DigiClaw custom skill)",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI-compatible API (expose DigiGraph as a model in Open WebUI)
v1 = APIRouter(prefix="/v1", tags=["openai-compatible"])


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for Docker and DigiClaw."""
    return {"status": "ok", "service": "digigraph"}


def _serve_run_data_file(path: str) -> FileResponse | dict:
    """Serve a file under run_data_dir. path is relative (e.g. default/export.csv). Returns 404 dict if disabled or invalid."""
    from pathlib import Path

    from digigraph.run_storage import get_run_data_dir

    root = get_run_data_dir()
    if not root:
        return {"detail": "File serving disabled (run_data_dir not set)"}
    base = Path(root).resolve()
    # Disallow path traversal
    clean = path.strip().lstrip("/")
    if ".." in clean or clean.startswith(".."):
        return {"detail": "Invalid path"}
    full = (base / clean).resolve()
    if not str(full).startswith(str(base)):
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


@app.post("/workflow", response_model=WorkflowResult, operation_id="run_sitaas_rag")
def api_run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    DigiClaw custom skill: run_digigraph_workflow.
    Phase 0: user idea → backtest via DigiQuant → result in < 10s.
    """
    return run_digigraph_workflow(req)


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


def _build_completion(
    req: ChatCompletionRequest, content: str, prompt: str
) -> dict:
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
        },
    }


def _sse_chunk(cid: str, created: int, model: str, content: str, finish_reason: str | None = None) -> str:
    """One SSE data line for chat.completion.chunk."""
    delta: dict = {"content": content} if content else {}
    if finish_reason is not None:
        delta = {} if not content else delta
    return json.dumps({
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {"index": 0, "delta": delta, "finish_reason": finish_reason}
        ],
    })


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
    req: ChatCompletionRequest, prompt: str, openwebui_format: bool = False
):
    """
    Generator: run workflow in thread, consume queue, yield SSE deltas.
    Format of tool_call and tool_result is determined by formatter (openwebui_format → Open WebUI <details>/tables; else neutral).
    """
    formatter = get_stream_formatter(openwebui_format)
    event_queue: Queue = Queue()
    workflow_req = WorkflowRequest(prompt=prompt)
    thread = Thread(target=run_digigraph_workflow_streaming, args=(workflow_req, event_queue))
    thread.start()

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = req.model
    pending_tool_calls: list[dict] = []

    while True:
        ev = event_queue.get()
        event_type = ev[0]
        data = ev[1] if len(ev) > 1 else None

        if event_type == "done":
            break
        if event_type == "tool_call":
            pending_tool_calls.append(data or {})
        elif event_type == "tool_result":
            call_data = pending_tool_calls.pop(0) if pending_tool_calls else {}
            content = formatter.format_tool_call_with_result(call_data, data or {})
            yield f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"
        elif event_type == "content":
            raw = data if isinstance(data, str) else (data or {}).get("delta", (data or {}).get("content", ""))
            content = (raw or "").replace("<", "&lt;").replace(">", "&gt;")
            if content:
                yield f"data: {_sse_chunk(cid, created, model, content, None)}\n\n"

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

    openwebui_format = _resolve_openwebui_format(req, request)

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
        return StreamingResponse(
            _stream_completions_progressive(req, prompt, openwebui_format=openwebui_format),
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
        result = run_digigraph_workflow(WorkflowRequest(prompt=prompt))
        content = result.message if result.success else f"Error: {result.message}"
    completion = _build_completion(req, content, prompt)
    return completion


app.include_router(v1)
