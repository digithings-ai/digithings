"""Research subgraph: research node then optional ResearchBrief builder."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from digigraph.graph.research import research_node
from digigraph.graph.research_brief import research_brief_builder_node
from digigraph.graph.state import WorkflowState
from digigraph.project_config import is_research_brief_enabled


def build_research_subgraph() -> CompiledStateGraph:
    """Research node, then ResearchBrief when enabled (else END after answer)."""
    g: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    g.add_node("research_inner", research_node)
    g.add_edge(START, "research_inner")
    if is_research_brief_enabled():
        g.add_node("research_brief_builder", research_brief_builder_node)
        g.add_edge("research_inner", "research_brief_builder")
        g.add_edge("research_brief_builder", END)
    else:
        g.add_edge("research_inner", END)
    return g.compile()
