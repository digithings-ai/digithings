"""Research subgraph: research node then ResearchBrief builder."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from digigraph.graph.research import research_node
from digigraph.graph.research_brief import research_brief_builder_node
from digigraph.graph.state import WorkflowState


def build_research_subgraph() -> CompiledStateGraph:
    """Research node then structured ResearchBrief + optional quant extraction."""
    g: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    g.add_node("research_inner", research_node)
    g.add_node("research_brief_builder", research_brief_builder_node)
    g.add_edge(START, "research_inner")
    g.add_edge("research_inner", "research_brief_builder")
    g.add_edge("research_brief_builder", END)
    return g.compile()
