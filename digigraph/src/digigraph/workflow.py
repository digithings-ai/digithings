"""Phase 1: run_digigraph_workflow via LangGraph (research → backtest optional)."""

from __future__ import annotations

from queue import Queue

from digigraph.audit import audit_log as dg_audit_log
from digigraph.graph import build_workflow_graph
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.project_config import DigiProjectConfig

__all__ = ["run_digigraph_workflow", "run_digigraph_workflow_streaming"]


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
    final = graph.invoke(initial)

    error = final.get("error")
    if error:
        dg_audit_log("workflow_end", agent_id="digigraph", payload={"success": False, "error": str(error)[:200]})
        return WorkflowResult(
            success=False,
            message=f"Workflow error: {error}",
            backtest_result=None,
        )

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
        dg_audit_log("workflow_end", agent_id="digigraph", payload={"success": success, "run_id": backtest.get("run_id", "")})
        return WorkflowResult(success=success, message=msg, backtest_result=backtest)

    # Research-only (e.g. Sitaas): no DigiQuant
    research_response = final.get("research_response")
    if research_response:
        msg = research_response
    else:
        strategy = final.get("strategy_name")
        symbols = final.get("symbols", [])
        msg = f"Research completed: strategy={strategy}, symbols={symbols}. No backtest (DigiQuant not in project)."
    dg_audit_log("workflow_end", agent_id="digigraph", payload={"success": True, "research_only": True})
    return WorkflowResult(success=True, message=msg, backtest_result=None)


def run_digigraph_workflow_streaming(req: WorkflowRequest, event_queue: Queue) -> None:
    """
    Run the workflow with stream_callback that puts (event_type, data) on event_queue.
    Events: ("tool_call", {name, arguments}), ("tool_result", {content}), then
    ("content", final_message), ("done", None).
    Intended to be run in a thread; the server consumes the queue and emits SSE.
    """
    def stream_callback(event_type: str, data: dict) -> None:
        event_queue.put((event_type, data))

    dg_audit_log("workflow_start", agent_id="digigraph", payload={"prompt_len": len(req.prompt or ""), "session_id": req.session_id or "", "streaming": True})
    graph = build_workflow_graph()
    initial: dict = {
        "prompt": req.prompt,
        "session_id": req.session_id,
        "stream_callback": stream_callback,
    }
    try:
        final = graph.invoke(initial)
    except Exception as e:
        event_queue.put(("content", f"Error: {e!s}"))
        event_queue.put(("done", None))
        return

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
