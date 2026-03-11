"""Phase 1: run_digigraph_workflow via LangGraph (research → backtest optional)."""

from __future__ import annotations

from queue import Queue

from digigraph.audit import audit_log as dg_audit_log
from digigraph.graph import build_workflow_graph
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.project_config import DigiProjectConfig

__all__ = ["run_digigraph_workflow", "run_digigraph_workflow_streaming", "run_digigraph_workflow_via_stream"]


def run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    Single custom skill entrypoint: chat idea → research (LLM + DigiSearch) → backtest (optional).
    When backtest disabled (e.g. Sitas): research-only, returns research output.
    """
    dg_audit_log("workflow_start", agent_id="digigraph", payload={"prompt_len": len(req.prompt or ""), "session_id": req.session_id or ""})
    graph = build_workflow_graph()
    initial: dict = {
        "prompt": req.prompt,
        "session_id": req.session_id,
    }
    config: dict = {"configurable": {"thread_id": req.session_id or "default"}}
    final = graph.invoke(initial, config=config)
    payload = {"success": not final.get("error"), "research_only": not final.get("backtest_result")}
    if final.get("error"):
        payload["error"] = final.get("error")
    dg_audit_log("workflow_end", agent_id="digigraph", payload=payload)
    return _workflow_result_from_state(final)


def _workflow_result_from_state(final: dict) -> WorkflowResult:
    """Build WorkflowResult from graph state dict (shared by invoke and stream paths)."""
    error = final.get("error")
    if error:
        return WorkflowResult(success=False, message=f"Workflow error: {error}", backtest_result=None)
    backtest = final.get("backtest_result")
    cfg = DigiProjectConfig.load()
    has_backtest = "backtest" in cfg.get_enabled_agents()
    if has_backtest and backtest:
        status = backtest.get("status", "unknown")
        success = status == "ok"
        msg = (
            f"Backtest completed: {backtest.get('strategy_name', '')} on {backtest.get('symbols', [])}. "
            f"Total return: {backtest.get('total_return_pct', 0):.2f}%, trades: {backtest.get('num_trades', 0)}."
        )
        return WorkflowResult(success=success, message=msg, backtest_result=backtest)
    research_response = final.get("research_response")
    if research_response:
        msg = research_response
    else:
        strategy = final.get("strategy_name")
        symbols = final.get("symbols", [])
        msg = f"Research completed: strategy={strategy}, symbols={symbols}. No backtest (DigiQuant not in project)."
    return WorkflowResult(success=True, message=msg, backtest_result=None)


def run_digigraph_workflow_via_stream(req: WorkflowRequest) -> WorkflowResult:
    """
    Run the workflow using graph.stream(..., stream_mode="updates") then get_state.
    Same result as run_digigraph_workflow but exercises LangGraph native streaming.
    Use for debugging or when you want to consume per-node updates (e.g. map to SSE).
    """
    dg_audit_log("workflow_start", agent_id="digigraph", payload={"prompt_len": len(req.prompt or ""), "session_id": req.session_id or "", "via_stream": True})
    graph = build_workflow_graph()
    initial = {"prompt": req.prompt, "session_id": req.session_id}
    config = {"configurable": {"thread_id": req.session_id or "default"}}
    for _ in graph.stream(initial, config=config, stream_mode="updates"):
        pass
    snapshot = graph.get_state(config)
    final = (snapshot.values if snapshot else None) or {}
    dg_audit_log("workflow_end", agent_id="digigraph", payload={"success": not final.get("error"), "via_stream": True})
    return _workflow_result_from_state(final)


def run_digigraph_workflow_streaming(req: WorkflowRequest, event_queue: Queue) -> None:
    """
    Run the workflow with stream_callback that puts (event_type, data) on event_queue.
    Events: ("tool_call", {name, arguments}), ("tool_result", {content}), then
    ("content", final_message), ("done", None).
    Intended to be run in a thread; the server consumes the queue and emits SSE.
    """
    from digigraph.graph.nodes import _stream_callback_ctx

    def stream_callback(event_type: str, data: dict) -> None:
        event_queue.put((event_type, data))

    dg_audit_log("workflow_start", agent_id="digigraph", payload={"prompt_len": len(req.prompt or ""), "session_id": req.session_id or "", "streaming": True})
    graph = build_workflow_graph()
    # Pass stream_callback via config and context var so the research node gets it even if LangGraph does not pass config.
    token = _stream_callback_ctx.set(stream_callback)
    try:
        initial: dict = {
            "prompt": req.prompt,
            "session_id": req.session_id,
        }
        config: dict = {"configurable": {"thread_id": req.session_id or "default", "stream_callback": stream_callback}}
        final = graph.invoke(initial, config=config)
    except Exception as e:
        event_queue.put(("content", f"Error: {e!s}"))
        event_queue.put(("done", None))
        return
    finally:
        _stream_callback_ctx.reset(token)
    error = final.get("error")
    if error:
        event_queue.put(("content", f"Error: {error}"))
        event_queue.put(("done", None))
        return

    # Do not put the full message again: research node already streamed the final answer token-by-token.
    # Putting ("content", msg) here would duplicate the final answer in the chat UI.
    research_response = final.get("research_response")
    if not research_response:
        strategy = final.get("strategy_name")
        symbols = final.get("symbols", [])
        fallback = f"Research completed: strategy={strategy}, symbols={symbols}. No backtest (DigiQuant not in project)."
        event_queue.put(("content", fallback))
    event_queue.put(("done", None))
