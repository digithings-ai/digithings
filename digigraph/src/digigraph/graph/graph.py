"""Build Phase 1 workflow graph: research → backtest. Supervisor is linear for now."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from digigraph.graph.nodes import backtest_node, research_node
from digigraph.graph.state import WorkflowState


def build_workflow_graph():
    """
    Build and compile the Phase 1 graph: START → research → backtest → END.
    Returns a compiled graph with invoke(input_state) -> final_state.
    """
    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("research", research_node)
    builder.add_node("backtest", backtest_node)
    builder.add_edge(START, "research")
    builder.add_edge("research", "backtest")
    builder.add_edge("backtest", END)
    return builder.compile()
