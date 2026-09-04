"""Resolve chat-completion request options from body + headers."""

from __future__ import annotations

import logging

from fastapi import Request

from digigraph.models import ChatCompletionRequest

logger = logging.getLogger("digigraph.server")

# Populated by digigraph.server after app init (shared debug log).
_DEBUG_REQUEST_LOG: list[dict] = []
_DEBUG_REQUEST_LOG_MAX = 5


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
