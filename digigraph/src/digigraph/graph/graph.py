"""Build workflow graph: optional supervisor → research subgraph → validate → backtest (profile-driven)."""

from __future__ import annotations

import os
import threading

from langgraph.graph import END, START, StateGraph

from digigraph.graph.nodes import (
    backtest_node,
    optimize_node,
    strategy_validator_node,
    supervisor_node,
)
from digigraph.graph.research_subgraph import build_research_subgraph
from digigraph.graph.state import WorkflowState
from digigraph.project_config import DigiProjectConfig

# Shared checkpointer so thread_id persists across HTTP requests (see LANGGRAPH_REVIEW.md).
_checkpointer_lock = threading.Lock()
_checkpointer_instance: object | None = None
# Hold context managers so they are not garbage-collected (sqlite/postgres).
_cm_holders: list[object] = []

WORKFLOW_PROFILES = frozenset({"full_stack", "research_rag", "quant_backtest", "plan_execute"})


def get_checkpointer():
    """
    Return a process-wide checkpointer for the current DIGI_CHECKPOINTER setting.
    The same instance is reused so thread state persists across requests.

    Env: DIGI_CHECKPOINTER=memory|sqlite|postgres. Unset defaults to **sqlite**
    when a digiproject.yaml is active (SITAAS multi-turn mode) so conversation state
    survives across requests. Falls back to **memory** when no project config is present.
    Use ``none`` to compile without one (not recommended; breaks multi-turn / thread APIs).

    For sqlite: DIGI_CHECKPOINTER_SQLITE_URI (default ~/.digigraph/checkpoints.sqlite).
    For postgres: DIGI_CHECKPOINTER_POSTGRES_URI.
    """
    global _checkpointer_instance, _cm_holders
    raw = (os.environ.get("DIGI_CHECKPOINTER") or "").strip().lower()
    if raw in ("none", "off", "0", "false", "disabled"):
        return None
    if raw:
        kind = raw
    else:
        from digigraph.project_config import _resolve_config_path

        kind = "sqlite" if _resolve_config_path() is not None else "memory"
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
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "langgraph-checkpoint-sqlite not installed; falling back to MemorySaver. "
                    "Install with: pip install 'digigraph[checkpoint-sqlite]'"
                )
                try:
                    from langgraph.checkpoint.memory import MemorySaver
                    _checkpointer_instance = MemorySaver()
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


def resolve_workflow_profile() -> str:
    try:
        p = DigiProjectConfig.load().get_workflow_profile()
    except Exception:
        return "full_stack"
    return p if p in WORKFLOW_PROFILES else "full_stack"


def _route_after_supervisor(state: WorkflowState):
    if state.get("error"):
        return END
    return "research"


def _route_after_research(state: WorkflowState):
    if state.get("error"):
        return END
    profile = (state.get("workflow_profile") or resolve_workflow_profile()).lower()
    if profile == "research_rag":
        return END
    # Document / RAG assistant mode: no strategy extraction → skip quant path.
    if state.get("research_response") and not state.get("strategy_name"):
        return END
    try:
        if "backtest" not in DigiProjectConfig.load().get_enabled_agents():
            return END
    except Exception:
        return END
    return "validate_strategy"


def _route_after_validate(state: WorkflowState):
    if state.get("error"):
        return END
    return "backtest"


def _optimize_after_backtest_enabled() -> bool:
    if os.environ.get("DIGI_GRAPH_OPTIMIZE_AFTER_BACKTEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    try:
        return "optimize" in DigiProjectConfig.load().get_enabled_agents()
    except Exception:
        return False


def _route_after_backtest(state: WorkflowState):
    if state.get("error"):
        return END
    if not state.get("backtest_result"):
        return END
    if _optimize_after_backtest_enabled():
        return "optimize"
    return END


def build_workflow_graph():
    """
    Compile the workflow graph.

    - research step uses a **compiled subgraph** (same state schema).
    - Profiles (``graph.workflow_profile`` or ``DIGI_WORKFLOW_PROFILE``): full_stack,
      research_rag, quant_backtest, plan_execute (plan_execute topology = full_stack;
      use ``agents.planning_mode`` for planner behavior).
    - Optional supervisor when ``DIGI_SUPERVISOR=1``.
    """
    supervisor_on = os.environ.get("DIGI_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")
    research_sg = build_research_subgraph()
    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    if supervisor_on:
        builder.add_node("supervisor", supervisor_node)
    builder.add_node("research", research_sg)
    builder.add_node("validate_strategy", strategy_validator_node)
    builder.add_node("backtest", backtest_node)
    builder.add_node("optimize", optimize_node)
    if supervisor_on:
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges("supervisor", _route_after_supervisor)
    else:
        builder.add_edge(START, "research")
    builder.add_conditional_edges("research", _route_after_research)
    builder.add_conditional_edges("validate_strategy", _route_after_validate)
    builder.add_conditional_edges("backtest", _route_after_backtest)
    builder.add_edge("optimize", END)

    checkpointer = get_checkpointer()
    interrupt_after: list[str] | None = None
    if (os.environ.get("DIGI_INTERRUPT_AFTER_RESEARCH", "").strip().lower()) in (
        "1",
        "true",
        "yes",
    ):
        # Interrupt after the research subgraph completes (outer node name is still "research").
        interrupt_after = ["research"]
    return builder.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)
