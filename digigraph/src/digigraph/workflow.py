"""Phase 1: run_digigraph_workflow via LangGraph (research → backtest)."""

from __future__ import annotations

from digigraph.audit import audit_log as dg_audit_log
from digigraph.graph import build_workflow_graph
from digigraph.graph.nodes import _heuristic_fallback as _infer_strategy_and_symbols
from digigraph.models import WorkflowRequest, WorkflowResult

__all__ = ["run_digigraph_workflow", "_infer_strategy_and_symbols"]


def run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    Single custom skill entrypoint: chat idea → research (LLM) → backtest.
    Phase 1: full LangGraph supervisor + research node; backtest via DigiQuant.
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
    status = (backtest or {}).get("status", "unknown")
    success = status == "ok"
    msg = (
        f"Backtest completed: {(backtest or {}).get('strategy_name', '')} on {(backtest or {}).get('symbols', [])}. "
        f"Total return: {(backtest or {}).get('total_return_pct', 0):.2f}%, trades: {(backtest or {}).get('num_trades', 0)}."
    )
    result = WorkflowResult(
        success=success,
        message=msg,
        backtest_result=backtest,
    )
    dg_audit_log("workflow_end", agent_id="digigraph", payload={"success": success, "run_id": (backtest or {}).get("run_id", "")})
    return result
