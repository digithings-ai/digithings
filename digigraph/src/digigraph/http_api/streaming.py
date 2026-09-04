"""OpenAI-compatible SSE chunk helpers and progressive workflow streaming."""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from queue import Empty, Queue
from threading import Event, Thread

from digigraph.boundaries import STREAM_SSE_ERRORS
from digigraph.formatters import get_stream_formatter
from digigraph.models import ChatCompletionRequest, WorkflowRequest

logger = logging.getLogger("digigraph.server")


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
        # Late-bind through digigraph.server so tests can patch
        # ``digigraph.server.run_digigraph_workflow_streaming``.
        from digigraph import server as _server

        try:
            _server.run_digigraph_workflow_streaming(workflow_req, event_queue, cancel_event)
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
