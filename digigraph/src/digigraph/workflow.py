"""Phase 1: run_digigraph_workflow via LangGraph (research → backtest optional)."""

from __future__ import annotations

import json
import logging
import uuid
from queue import Full, Queue
from threading import Event
from typing import Any

from digigraph.audit import audit_log as dg_audit_log
from digigraph.boundaries import GRAPH_RUNTIME_ERRORS, PROJECT_CONFIG_ERRORS
from digigraph.graph import build_workflow_graph
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.project_config import DigiProjectConfig
from digigraph.thread_scope import workflow_thread_id
from digigraph.tool_policy import (
    allowed_tool_names_for_workflow,
    require_tool_calls_for_workflow,
    state_list_from_frozen,
)

__all__ = [
    "run_digigraph_workflow",
    "run_digigraph_workflow_streaming",
    "run_digigraph_workflow_via_stream",
]

logger = logging.getLogger(__name__)

_RETRIEVAL_TOOL_NAMES = frozenset(
    {
        "digisearch",
        "digisearch_fetch_all",
        "digisearch_research_delegate",
        "digivault_search_notes",
        "digivault_get_note",
        "web_search",
    }
)


def _clip_tool_arguments(args: dict[str, Any]) -> dict[str, Any]:
    """Size-capped MCP args for the BFF tool-row UI (never a raw prompt dump)."""
    clipped: dict[str, Any] = {}
    for i, (key, val) in enumerate(args.items()):
        if i >= 16 or not isinstance(key, str) or not key.strip():
            continue
        if isinstance(val, str):
            clipped[key] = val[:300]
        elif isinstance(val, bool):
            clipped[key] = val
        elif isinstance(val, int | float):
            clipped[key] = val
        elif isinstance(val, list):
            items = [item[:300] for item in val if isinstance(item, str) and item.strip()][:20]
            if items:
                clipped[key] = items
    return clipped


def _audit_digi_kwargs(req: WorkflowRequest) -> dict[str, str]:
    out: dict[str, str] = {}
    if req.digi_trace_key_prefix:
        out["key_prefix"] = req.digi_trace_key_prefix
    if req.digi_trace_tenant:
        out["tenant"] = req.digi_trace_tenant
    if req.digi_trace_project_id:
        out["project_id"] = req.digi_trace_project_id
    if req.digi_trace_jti:
        out["jti"] = req.digi_trace_jti
    return out


def _initial_graph_state(req: WorkflowRequest, workflow_id: str) -> dict[str, Any]:
    initial: dict[str, Any] = {
        "prompt": req.prompt,
        "session_id": req.session_id,
        "request_id": req.request_id,
        "workflow_id": workflow_id,
    }
    if req.digi_bearer:
        initial["digi_bearer"] = req.digi_bearer
    cfg = None
    try:
        cfg = DigiProjectConfig.load()
        initial["workflow_profile"] = cfg.get_workflow_profile()
    except PROJECT_CONFIG_ERRORS as e:
        logger.warning("workflow_profile load failed; using full_stack: %s", e)
        initial["workflow_profile"] = "full_stack"
    frozen = allowed_tool_names_for_workflow(req, cfg=cfg)
    names = state_list_from_frozen(frozen)
    if names is not None:
        initial["allowed_tool_names"] = names
    initial["require_tool_calls"] = require_tool_calls_for_workflow(req, cfg=cfg)
    if req.trading_profile:
        initial["trading_profile"] = req.trading_profile
    if req.strategy_params:
        initial["strategy_params"] = req.strategy_params
    if req.research_filters:
        initial["research_filters"] = req.research_filters
    if req.evidence_tier_preference:
        initial["evidence_tier_preference"] = req.evidence_tier_preference
    # Corpus + subject must be written unconditionally (including explicit None).
    # LangGraph checkpoints use per-key last-write-wins: omitting a key leaves the
    # prior turn's value sticky. server.py's DIGI_TENANT_CORPUS_MAP path clears
    # digisearch_index / vault_path_prefix / research_system_prompt_override to None
    # for unmapped tenants (CWE-639 — digisearch has no server-side tenant→index
    # bind), and clears digi_subject when auth is absent. If those Nones never reach
    # initial state, a later turn on the same thread_id keeps querying the previous
    # tenant's corpus. digichat embeds share subject ``embed:anonymous`` across
    # tenants and clients control X-Digichat-Session, so reuse is a concrete trigger.
    # Same pattern as response_language (#2103).
    initial["digisearch_index"] = req.digisearch_index
    initial["vault_path_prefix"] = req.vault_path_prefix
    initial["research_system_prompt_override"] = req.research_system_prompt_override
    initial["digi_subject"] = req.digi_subject
    initial["response_language"] = req.response_language
    initial["force_tool"] = req.force_tool
    initial["enable_web_search"] = bool(req.enable_web_search)
    # Unconditional — empty list must clear a prior tenant's MCP URLs.
    initial["mcp_servers"] = [
        s.model_dump(exclude_none=True)
        if hasattr(s, "model_dump")
        else {"id": s["id"], "url": s["url"]}
        for s in (req.mcp_servers or [])
    ]
    initial["disabled_tools"] = list(req.disabled_tools) if req.disabled_tools else None
    initial["effort"] = req.effort
    return initial


def _graph_thread_config(req: WorkflowRequest) -> dict:
    return {"configurable": {"thread_id": workflow_thread_id(req.digi_subject, req.session_id)}}


def _workflow_start_payload(
    req: WorkflowRequest, workflow_id: str, **flags: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt_len": len(req.prompt or ""),
        "session_id": req.session_id or "",
        "request_id": req.request_id or "",
        "workflow_id": workflow_id,
    }
    if req.digi_trace_key_prefix:
        payload["key_prefix"] = req.digi_trace_key_prefix
    if req.digi_trace_tenant:
        payload["tenant"] = req.digi_trace_tenant
    if req.digi_trace_project_id:
        payload["project_id"] = req.digi_trace_project_id
    if req.digi_trace_jti:
        payload["jti"] = req.digi_trace_jti
    for k, v in flags.items():
        if v:
            payload[k] = True
    return payload


def _workflow_end_payload(
    final: dict[str, Any],
    req: WorkflowRequest,
    workflow_id: str,
    *,
    streaming: bool = False,
    via_stream: bool = False,
) -> dict[str, Any]:
    err = final.get("error")
    payload: dict[str, Any] = {
        "success": not bool(err),
        "workflow_id": workflow_id,
        "request_id": req.request_id or "",
        "session_id": req.session_id or "",
        "had_backtest": final.get("backtest_result") is not None,
        "research_only": not final.get("backtest_result") and not err,
    }
    if final.get("strategy_name") is not None:
        payload["strategy_name"] = final.get("strategy_name")
    if final.get("symbols") is not None:
        payload["symbols"] = final.get("symbols")
    if final.get("backtest_job_id"):
        payload["backtest_job_id"] = final.get("backtest_job_id")
    if err:
        payload["error"] = err
    if final.get("error_code"):
        payload["error_code"] = final.get("error_code")
    if streaming:
        payload["streaming"] = True
    if via_stream:
        payload["via_stream"] = True
    return payload


def run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    Single custom skill entrypoint: chat idea → research (LLM + digisearch) → backtest (optional).
    When backtest disabled (e.g. Sitas): research-only, returns research output.
    """
    workflow_id = str(uuid.uuid4())
    dg_audit_log(
        "workflow_start",
        agent_id="digigraph",
        payload=_workflow_start_payload(req, workflow_id),
        **_audit_digi_kwargs(req),
    )
    graph = build_workflow_graph()
    initial: dict[str, Any] = _initial_graph_state(req, workflow_id)
    config: dict = _graph_thread_config(req)
    final = graph.invoke(initial, config=config, durability="sync")
    dg_audit_log(
        "workflow_end",
        agent_id="digigraph",
        payload=_workflow_end_payload(final, req, workflow_id),
        **_audit_digi_kwargs(req),
    )
    return _workflow_result_from_state(final)


def _workflow_result_from_state(final: dict) -> WorkflowResult:
    """Build WorkflowResult from graph state dict (shared by invoke and stream paths)."""
    error = final.get("error")
    error_code = final.get("error_code")
    if error:
        return WorkflowResult(
            success=False,
            message=f"Workflow error: {error}",
            error_code=str(error_code) if error_code else None,
            backtest_result=None,
            optimize_result=None,
            optimize_error=final.get("optimize_error"),
            research_brief=final.get("research_brief")
            if isinstance(final.get("research_brief"), dict)
            else None,
            rag_sources=final.get("rag_sources")
            if isinstance(final.get("rag_sources"), list)
            else None,
            profiling_questions=final.get("profiling_questions")
            if isinstance(final.get("profiling_questions"), list)
            else None,
        )
    backtest = final.get("backtest_result")
    opt_res = final.get("optimize_result")
    opt_err = final.get("optimize_error")
    cfg = DigiProjectConfig.load()
    has_backtest = "backtest" in cfg.get_enabled_agents()
    if has_backtest and backtest:
        status = backtest.get("status", "unknown")
        success = status == "ok"
        msg = (
            f"Backtest completed: {backtest.get('strategy_name', '')} on {backtest.get('symbols', [])}. "
            f"Total return: {backtest.get('total_return_pct', 0):.2f}%, trades: {backtest.get('num_trades', 0)}."
        )
        if opt_res:
            msg += (
                f" Optimization: best_params={opt_res.get('best_params', {})}, "
                f"evaluations={opt_res.get('num_evaluations', 0)}."
            )
        if opt_err:
            msg += f" (Optimize warning: {opt_err})"
        return WorkflowResult(
            success=success,
            message=msg,
            backtest_result=backtest,
            optimize_result=opt_res if isinstance(opt_res, dict) else None,
            optimize_error=str(opt_err) if opt_err else None,
            research_brief=final.get("research_brief")
            if isinstance(final.get("research_brief"), dict)
            else None,
            rag_sources=final.get("rag_sources")
            if isinstance(final.get("rag_sources"), list)
            else None,
            profiling_questions=final.get("profiling_questions")
            if isinstance(final.get("profiling_questions"), list)
            else None,
        )
    research_response = final.get("research_response")
    if research_response:
        msg = research_response
    else:
        strategy = final.get("strategy_name")
        symbols = final.get("symbols", [])
        msg = f"Research completed: strategy={strategy}, symbols={symbols}. No backtest (digiquant not in project)."
    return WorkflowResult(
        success=True,
        message=msg,
        backtest_result=None,
        optimize_result=opt_res if isinstance(opt_res, dict) else None,
        optimize_error=str(opt_err) if opt_err else None,
        research_brief=final.get("research_brief")
        if isinstance(final.get("research_brief"), dict)
        else None,
        rag_sources=final.get("rag_sources")
        if isinstance(final.get("rag_sources"), list)
        else None,
        profiling_questions=final.get("profiling_questions")
        if isinstance(final.get("profiling_questions"), list)
        else None,
    )


def run_digigraph_workflow_via_stream(req: WorkflowRequest) -> WorkflowResult:
    """
    Run the workflow using graph.stream(..., stream_mode="updates") then get_state.
    Same result as run_digigraph_workflow but exercises LangGraph native streaming.
    Use for debugging or when you want to consume per-node updates (e.g. map to SSE).
    """
    workflow_id = str(uuid.uuid4())
    dg_audit_log(
        "workflow_start",
        agent_id="digigraph",
        payload=_workflow_start_payload(req, workflow_id, via_stream=True),
        **_audit_digi_kwargs(req),
    )
    graph = build_workflow_graph()
    initial = _initial_graph_state(req, workflow_id)
    config = _graph_thread_config(req)
    for _ in graph.stream(initial, config=config, stream_mode="updates", durability="sync"):
        pass
    snapshot = graph.get_state(config)
    final = (snapshot.values if snapshot else None) or {}
    dg_audit_log(
        "workflow_end",
        agent_id="digigraph",
        payload=_workflow_end_payload(final, req, workflow_id, via_stream=True),
        **_audit_digi_kwargs(req),
    )
    return _workflow_result_from_state(final)


def _stream_update_summary(update: dict[str, Any]) -> dict[str, Any]:
    """Lightweight payload for trace (avoid serializing large state values)."""
    summary: dict[str, Any] = {}
    for node, delta in update.items():
        if isinstance(delta, dict):
            summary[node] = {"keys": list(delta.keys())[:24]}
        else:
            summary[node] = {"type": type(delta).__name__}
    return summary


# How long a single blocking attempt to hand an event to the SSE consumer may wait
# before ``_emit_event`` re-checks cancellation. Small enough that a disconnect is
# noticed promptly, large enough that a healthy-but-slow consumer still gets
# backpressure rather than a spin.
_EMIT_POLL_SECONDS = 0.1


def _emit_event(
    event_queue: Queue,
    cancel_event: Event | None,
    item: tuple[str, Any],
) -> None:
    """Hand one streaming event to the SSE consumer, giving up if it has gone away.

    ``event_queue`` is deliberately bounded (``maxsize=256`` in ``server.py``) so a fast
    graph cannot outrun a slow client -- but the consumer stops draining the instant
    ``cancel_event`` is set: a client disconnect raises ``GeneratorExit`` into
    ``_stream_completions_progressive``, which sets the event and breaks out of its
    ``get`` loop without emptying the queue. A plain blocking ``put`` on a full queue
    then waits for a reader that will never arrive, and it waits *inside* a graph node,
    so the worker never reaches the cancellation poll between nodes (the ``graph.stream``
    loop below) and never runs its ``finally``. That ``finally`` is where the request's
    BYOK credentials are cleared from this thread's context copy (``server.py``,
    ``clear_byok_bindings``), so the hang would strand a user's API key in a leaked
    non-daemon thread for the lifetime of the process -- not for the bounded "one more
    node" this module used to claim.

    So poll rather than block, and once nobody is listening, drop the event instead of
    waiting to deliver it to no one.
    """
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return
        try:
            event_queue.put(item, timeout=_EMIT_POLL_SECONDS)
            return
        except Full:
            continue


def _tool_result_error(data: dict[str, Any]) -> str | None:
    """Surface a failed vault/search invoke instead of a fake zero-hit retrieve."""
    if data.get("ok") is False:
        err = data.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
        content = data.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()[:500]
        return "tool failed"
    content = data.get("content")
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("ok") is False:
        err = parsed.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
        return "tool failed"
    return None


def run_digigraph_workflow_streaming(
    req: WorkflowRequest,
    event_queue: Queue,
    cancel_event: Event | None = None,
) -> None:
    """
    Run the workflow with stream_callback that puts (event_type, data) on event_queue.
    Events: ("tool_call", ...), ("tool_result", ...), ("trace", TraceEventV1 dict),
    ("content", str | delta), ("reasoning", ...), ("done", None).

    Uses ``graph.stream(..., stream_mode="updates")`` as the primary driver; the research
    tool loop still emits tool/content events via the same callback.
    Intended to be run in a thread; the server consumes the queue and emits SSE.
    """
    from digigraph.trace_events import TraceEventV1

    workflow_id = str(uuid.uuid4())
    content_streamed = False
    pending_tool_args: dict[str, list[dict[str, Any]]] = {}
    trace_ctx = {
        "workflow_id": workflow_id,
        "request_id": req.request_id,
        "session_id": req.session_id,
    }

    def emit(item: tuple[str, Any]) -> None:
        _emit_event(event_queue, cancel_event, item)

    def stream_callback(event_type: str, data: Any) -> None:
        nonlocal content_streamed
        if cancel_event is not None and cancel_event.is_set():
            # The consumer is gone, so every emit below would be dropped anyway
            # (see :func:`_emit_event`) -- skip building the trace payloads too.
            return
        if event_type == "content" and data:
            raw = (
                data if isinstance(data, str) else (data.get("delta") or data.get("content") or "")
            )
            if raw:
                content_streamed = True
        if event_type == "tool_call" and isinstance(data, dict):
            name = data.get("name")
            args = data.get("arguments") or data.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            from digigraph.retrieval import query_from_tool_args

            tool_query = query_from_tool_args(args)
            if isinstance(name, str) and name.strip():
                tool_payload: dict[str, Any] = {
                    "tool": name.strip(),
                    "status": "started",
                }
                if tool_query:
                    tool_payload["query"] = tool_query
                if args:
                    clipped = _clip_tool_arguments(args)
                    if clipped:
                        tool_payload["arguments"] = clipped
                        pending_tool_args.setdefault(name.strip(), []).append(clipped)
                emit(
                    (
                        "trace",
                        TraceEventV1(
                            type="tool_call",
                            workflow_id=trace_ctx["workflow_id"],
                            request_id=trace_ctx["request_id"],
                            session_id=trace_ctx["session_id"],
                            payload=tool_payload,
                        ).model_dump(),
                    )
                )
            if name in ("data_engineer_agent", "data_engineer"):
                code = args.get("code") if isinstance(args.get("code"), str) else None
                task = args.get("task") if isinstance(args.get("task"), str) else None
                body = (code or task or "").strip()
                if body:
                    emit(
                        (
                            "trace",
                            TraceEventV1(
                                type="code_block",
                                workflow_id=trace_ctx["workflow_id"],
                                request_id=trace_ctx["request_id"],
                                session_id=trace_ctx["session_id"],
                                payload={
                                    "language": "python" if code else "text",
                                    "phase": "submitted",
                                    "content": body[:24_000],
                                },
                            ).model_dump(),
                        )
                    )
        if event_type == "round_boundary" and isinstance(data, dict):
            # #2306 follow-up: run_tools fires this the moment a round's tool_calls
            # becomes known, marking that round's already-streamed "content" as NOT
            # the final answer. Forwarded as a "trace"/digigraph_trace event — the
            # same channel code_block/rag_sources use above — because that is the
            # ONLY event type server.py's _stream_completions_progressive still
            # forwards to a client with suppress_tool_stream=True (digichat always
            # sets this): "content" itself is the visible answer channel and cannot
            # double as this signal without a consumer misreading narration as the
            # answer, which is precisely the bug this closes.
            emit(
                (
                    "trace",
                    TraceEventV1(
                        type="round_boundary",
                        workflow_id=trace_ctx["workflow_id"],
                        request_id=trace_ctx["request_id"],
                        session_id=trace_ctx["session_id"],
                        payload={
                            "round_idx": data.get("round_idx"),
                            # Capped defensively, matching code_block's 24_000-char cap
                            # above -- narration is normally short model prose, not
                            # arbitrary user/tool content, but nothing enforces that.
                            "narration": str(data.get("narration") or "")[:24_000],
                        },
                    ).model_dump(),
                )
            )
        if event_type == "tool_result" and isinstance(data, dict):
            # Fire on any retrieval tool's result, hit or miss. "rag_sources" is a key
            # only retrieval handlers set on their return dict (digisearch,
            # digisearch_fetch_all, digivault_search_notes, digivault_get_note,
            # digisearch_research_delegate) — present even when empty on a zero-hit
            # search. String error returns omit the key; still emit a completion
            # trace so the BFF does not leave Allow/Deny on the started row.
            tool_name = data.get("name")
            name = tool_name.strip() if isinstance(tool_name, str) and tool_name.strip() else ""
            has_sources = "rag_sources" in data
            if has_sources or name in _RETRIEVAL_TOOL_NAMES:
                sources = data.get("rag_sources") if has_sources else []
                if not isinstance(sources, list):
                    sources = []
                rag_payload: dict[str, Any] = {
                    "sources": sources,
                    "tool": name or data.get("name", "digisearch"),
                }
                queued = pending_tool_args.get(name) if name else None
                if queued:
                    rag_payload["arguments"] = queued.pop(0)
                if "query" in data:
                    rag_payload["query"] = data["query"]
                if "hit_count" in data:
                    rag_payload["hit_count"] = data["hit_count"]
                err = _tool_result_error(data)
                if err:
                    rag_payload["error"] = err[:500]
                    rag_payload["status"] = "failed"
                emit(
                    (
                        "trace",
                        TraceEventV1(
                            type="rag_sources",
                            workflow_id=trace_ctx["workflow_id"],
                            request_id=trace_ctx["request_id"],
                            session_id=trace_ctx["session_id"],
                            payload=rag_payload,
                        ).model_dump(),
                    )
                )
        emit((event_type, data))

    dg_audit_log(
        "workflow_start",
        agent_id="digigraph",
        payload=_workflow_start_payload(req, workflow_id, streaming=True),
        **_audit_digi_kwargs(req),
    )
    graph = build_workflow_graph()
    final: dict[str, Any] = {}
    try:
        initial = _initial_graph_state(req, workflow_id)
        config: dict = {
            "configurable": {
                "thread_id": workflow_thread_id(req.digi_subject, req.session_id),
            },
        }
        for part in graph.stream(
            initial,
            config=config,
            stream_mode=["updates", "custom"],
            version="v2",
            durability="sync",
            subgraphs=True,
        ):
            if cancel_event is not None and cancel_event.is_set():
                emit(("done", None))
                return
            if part["type"] == "custom":
                # "custom" parts are NOT filtered by ns: research_node and
                # research_brief_builder_node run inside the compiled "research"
                # subgraph (graph.py builds it via build_research_subgraph() and adds
                # it as a single node), so every _safe_stream_writer() write from
                # _run_document_rag_path (tool_call, tool_result, content, reasoning,
                # round_boundary) arrives here with a non-empty ns -- without
                # subgraphs=True above, LangGraph drops these silently before they
                # ever reach this loop.
                event_type, data = part["data"]
                stream_callback(event_type, data)
                continue
            if part["ns"]:
                # subgraphs=True also makes "updates" parts start arriving for nodes
                # INSIDE the research subgraph (ns=("research:<uuid>",)), which would
                # double-report a graph_update trace event for both the inner node's
                # completion and the outer "research" node's completion. Only
                # top-level graph updates (ns == ()) are reported as graph_update
                # trace events; this does not affect the "custom" branch above.
                continue
            update = part["data"]
            emit(
                (
                    "trace",
                    TraceEventV1(
                        type="graph_update",
                        workflow_id=trace_ctx["workflow_id"],
                        request_id=trace_ctx["request_id"],
                        session_id=trace_ctx["session_id"],
                        payload={"update": _stream_update_summary(update)},
                    ).model_dump(),
                )
            )
        snapshot = graph.get_state(config)
        final = dict(snapshot.values) if snapshot and snapshot.values else {}
    except GRAPH_RUNTIME_ERRORS as e:
        dg_audit_log(
            "workflow_end",
            agent_id="digigraph",
            payload={
                "success": False,
                "workflow_id": workflow_id,
                "request_id": req.request_id or "",
                "session_id": req.session_id or "",
                "streaming": True,
                "error": str(e),
            },
            **_audit_digi_kwargs(req),
        )
        from digigraph.llm_errors import LLM_ERROR, sanitize_user_facing_error

        message = sanitize_user_facing_error(str(e), limit=280) or "The workflow failed."
        detail = sanitize_user_facing_error(str(e))
        payload: dict[str, str] = {"code": LLM_ERROR, "message": message}
        if detail and detail != message:
            payload["detail"] = detail
        emit(("error", payload))
        emit(("done", None))
        return

    dg_audit_log(
        "workflow_end",
        agent_id="digigraph",
        payload=_workflow_end_payload(final, req, workflow_id, streaming=True),
        **_audit_digi_kwargs(req),
    )
    error = final.get("error")
    if error:
        from digigraph.llm_errors import LLM_ERROR, sanitize_user_facing_error

        err_code = str(final.get("error_code") or LLM_ERROR)
        message = sanitize_user_facing_error(str(error), limit=280) or "The request failed."
        payload: dict[str, str] = {"code": err_code, "message": message}
        detail_raw = final.get("error_detail")
        detail = sanitize_user_facing_error(str(detail_raw)) if detail_raw else None
        if not detail:
            extra = sanitize_user_facing_error(str(error))
            if extra and extra != message:
                detail = extra
        if detail and detail != message:
            payload["detail"] = detail
        emit(("error", payload))
        emit(("done", None))
        return

    research_response = final.get("research_response")
    if research_response and not content_streamed:
        emit(("content", str(research_response)))
    elif not research_response and not content_streamed:
        strategy = final.get("strategy_name")
        symbols = final.get("symbols", [])
        fallback = (
            f"Research completed: strategy={strategy}, symbols={symbols}. "
            "No assistant text was streamed; check backtest or tool results."
        )
        backtest = final.get("backtest_result")
        if backtest:
            fallback = (
                f"Backtest completed: {backtest.get('strategy_name', '')} "
                f"on {backtest.get('symbols', [])}. "
                f"Return: {backtest.get('total_return_pct', 0):.2f}%."
            )
        emit(("content", fallback))
    emit(("done", None))
