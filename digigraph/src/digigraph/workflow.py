"""Phase 1: run_digigraph_workflow via LangGraph (research → backtest optional)."""

from __future__ import annotations

import uuid
from queue import Queue
from threading import Event
from typing import Any

import yaml

from digigraph.audit import audit_log as dg_audit_log
from digigraph.graph import build_workflow_graph
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.project_config import DigiProjectConfig
from digigraph.thread_scope import workflow_thread_id
from digigraph.tool_policy import allowed_tool_names_for_workflow, state_list_from_frozen

__all__ = [
    "run_digigraph_workflow",
    "run_digigraph_workflow_streaming",
    "run_digigraph_workflow_via_stream",
]

_PROJECT_CONFIG_ERRORS = (OSError, yaml.YAMLError, AttributeError, TypeError, ValueError)


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
    try:
        initial["workflow_profile"] = DigiProjectConfig.load().get_workflow_profile()
    except _PROJECT_CONFIG_ERRORS:
        initial["workflow_profile"] = "full_stack"
    frozen = allowed_tool_names_for_workflow(req)
    names = state_list_from_frozen(frozen)
    if names is not None:
        initial["allowed_tool_names"] = names
    if req.trading_profile:
        initial["trading_profile"] = req.trading_profile
    if req.strategy_params:
        initial["strategy_params"] = req.strategy_params
    if req.research_filters:
        initial["research_filters"] = req.research_filters
    if req.evidence_tier_preference:
        initial["evidence_tier_preference"] = req.evidence_tier_preference
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
    if streaming:
        payload["streaming"] = True
    if via_stream:
        payload["via_stream"] = True
    return payload


def run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    Single custom skill entrypoint: chat idea → research (LLM + DigiSearch) → backtest (optional).
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
    final = graph.invoke(initial, config=config)
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
    if error:
        return WorkflowResult(
            success=False,
            message=f"Workflow error: {error}",
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
        msg = f"Research completed: strategy={strategy}, symbols={symbols}. No backtest (DigiQuant not in project)."
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
    for _ in graph.stream(initial, config=config, stream_mode="updates"):
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
    from digigraph.graph.research import _stream_callback_ctx
    from digigraph.trace_events import TraceEventV1

    workflow_id = str(uuid.uuid4())
    content_streamed = False
    trace_ctx = {
        "workflow_id": workflow_id,
        "request_id": req.request_id,
        "session_id": req.session_id,
    }

    def stream_callback(event_type: str, data: Any) -> None:
        nonlocal content_streamed
        if event_type == "content" and data:
            raw = (
                data if isinstance(data, str) else (data.get("delta") or data.get("content") or "")
            )
            if raw:
                content_streamed = True
        if event_type == "tool_call" and isinstance(data, dict):
            name = data.get("name")
            args = data.get("arguments") or {}
            if name in ("data_engineer_agent", "data_engineer"):
                code = args.get("code") if isinstance(args.get("code"), str) else None
                task = args.get("task") if isinstance(args.get("task"), str) else None
                body = (code or task or "").strip()
                if body:
                    event_queue.put(
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
        if event_type == "tool_result" and isinstance(data, dict) and data.get("rag_sources"):
            event_queue.put(
                (
                    "trace",
                    TraceEventV1(
                        type="rag_sources",
                        workflow_id=trace_ctx["workflow_id"],
                        request_id=trace_ctx["request_id"],
                        session_id=trace_ctx["session_id"],
                        payload={
                            "sources": data["rag_sources"],
                            "tool": data.get("name", "digisearch"),
                        },
                    ).model_dump(),
                )
            )
        event_queue.put((event_type, data))

    dg_audit_log(
        "workflow_start",
        agent_id="digigraph",
        payload=_workflow_start_payload(req, workflow_id, streaming=True),
        **_audit_digi_kwargs(req),
    )
    graph = build_workflow_graph()
    token = _stream_callback_ctx.set(stream_callback)
    final: dict[str, Any] = {}
    try:
        initial = _initial_graph_state(req, workflow_id)
        config: dict = {
            "configurable": {
                "thread_id": workflow_thread_id(req.digi_subject, req.session_id),
                "stream_callback": stream_callback,
            },
        }
        for update in graph.stream(initial, config=config, stream_mode="updates"):
            if cancel_event is not None and cancel_event.is_set():
                event_queue.put(("done", None))
                return
            event_queue.put(
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
    except Exception as e:
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
        event_queue.put(("content", f"Error: {e!s}"))
        event_queue.put(("done", None))
        return
    finally:
        _stream_callback_ctx.reset(token)

    dg_audit_log(
        "workflow_end",
        agent_id="digigraph",
        payload=_workflow_end_payload(final, req, workflow_id, streaming=True),
        **_audit_digi_kwargs(req),
    )
    error = final.get("error")
    if error:
        event_queue.put(("content", f"Error: {error}"))
        event_queue.put(("done", None))
        return

    research_response = final.get("research_response")
    if research_response and not content_streamed:
        event_queue.put(("content", str(research_response)))
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
        event_queue.put(("content", fallback))
    event_queue.put(("done", None))
