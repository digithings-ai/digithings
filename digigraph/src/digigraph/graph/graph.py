"""Build Phase 1 workflow graph: research → backtest (optional). Supervisor is linear for now."""

from __future__ import annotations

import os
import threading

from langgraph.graph import END, START, StateGraph

from digigraph.graph.nodes import backtest_node, research_node
from digigraph.graph.state import WorkflowState
from digigraph.project_config import DigiProjectConfig

# Shared checkpointer so thread_id persists across HTTP requests (see LANGGRAPH_REVIEW.md).
_checkpointer_lock = threading.Lock()
_checkpointer_instance: object | None = None
# Hold context managers so they are not garbage-collected (sqlite/postgres).
_cm_holders: list[object] = []


def get_checkpointer():
    """
    Return a process-wide checkpointer for the current DIGI_CHECKPOINTER setting.
    When set (memory, sqlite, or postgres), the same instance is reused so
    thread state persists across requests. Without this, thread_id would only
    persist within a single request.
    Env: DIGI_CHECKPOINTER=memory|sqlite|postgres. For sqlite: DIGI_CHECKPOINTER_SQLITE_URI
    (default ~/.digigraph/checkpoints.sqlite). For postgres: DIGI_CHECKPOINTER_POSTGRES_URI.
    """
    global _checkpointer_instance, _cm_holders
    kind = (os.environ.get("DIGI_CHECKPOINTER") or "").strip().lower()
    if not kind:
        return None
    with _checkpointer_lock:
        if _checkpointer_instance is not None:
            return _checkpointer_instance
        if kind == "memory":
            try:
                from langgraph.checkpoint.memory import MemorySaver
                _checkpointer_instance = MemorySaver()
            except ImportError:
                pass
        elif kind == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
                uri = os.environ.get("DIGI_CHECKPOINTER_SQLITE_URI", "").strip()
                if not uri:
                    uri = os.path.join(os.path.expanduser("~"), ".digigraph", "checkpoints.sqlite")
                    os.makedirs(os.path.dirname(uri), exist_ok=True)
                cm = SqliteSaver.from_conn_string(uri)
                _cm_holders.append(cm)
                _checkpointer_instance = cm.__enter__()
            except ImportError:
                pass
        elif kind == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                conn_string = os.environ.get("DIGI_CHECKPOINTER_POSTGRES_URI", "").strip()
                if conn_string:
                    cm = PostgresSaver.from_conn_string(conn_string)
                    _cm_holders.append(cm)
                    _checkpointer_instance = cm.__enter__()
                    _checkpointer_instance.setup()
            except ImportError:
                pass
        return _checkpointer_instance


def _route_after_research(state: WorkflowState):
    """Route to backtest or END. Uses conditional edge so graph shape is fixed."""
    if state.get("error"):
        return END
    try:
        if "backtest" not in DigiProjectConfig.load().get_enabled_agents():
            return END
    except Exception:
        return END
    return "backtest"


def build_workflow_graph():
    """
    Build and compile the Phase 1 graph.
    Single graph shape: START → research → (backtest | END) via conditional edge.
    When agents.enabled includes backtest and state has no error, runs backtest; else END.
    When DIGI_CHECKPOINTER is set, uses get_checkpointer() so state persists across requests.
    Returns a compiled graph with invoke(input_state, config) -> final_state.
    """
    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("research", research_node)
    builder.add_node("backtest", backtest_node)
    builder.add_edge(START, "research")
    builder.add_conditional_edges("research", _route_after_research)
    builder.add_edge("backtest", END)

    checkpointer = get_checkpointer()
    interrupt_after: list[str] | None = None
    if (os.environ.get("DIGI_INTERRUPT_AFTER_RESEARCH", "").strip().lower()) in ("1", "true", "yes"):
        interrupt_after = ["research"]
    return builder.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)
