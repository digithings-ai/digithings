"""Build Phase 1 workflow graph: research → backtest (optional). Supervisor is linear for now."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from digigraph.graph.nodes import backtest_node, research_node
from digigraph.graph.state import WorkflowState
from digigraph.project_config import DigiProjectConfig


def build_workflow_graph():
    """
    Build and compile the Phase 1 graph.
    When agents.enabled includes backtest: START → research → backtest → END.
    When backtest disabled (e.g. Sitas): START → research → END.
    Returns a compiled graph with invoke(input_state) -> final_state.
    """
    cfg = DigiProjectConfig.load()
    enabled = cfg.get_enabled_agents()

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("research", research_node)
    builder.add_edge(START, "research")

    if "backtest" in enabled:
        builder.add_node("backtest", backtest_node)
        builder.add_edge("research", "backtest")
        builder.add_edge("backtest", END)
    else:
        builder.add_edge("research", END)

    return builder.compile()
