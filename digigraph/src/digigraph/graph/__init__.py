"""LangGraph orchestration: supervisor + sub-graph pattern (Phase 1+)."""

from digigraph.graph.graph import build_workflow_graph
from digigraph.graph.product_graphs import (
    ProductGraphRunRequest,
    ProductGraphRunState,
    ProductGraphSpec,
    build_research_portfolio_product_graph,
    get_product_graph_spec,
    list_product_graphs,
    run_product_graph,
)
from digigraph.graph.research_spike_subgraph import (
    ResearchState,
    build_research_subgraph,
    research_subgraph,
)

__all__ = [
    "ResearchState",
    "research_subgraph",
    "build_research_subgraph",
    "build_workflow_graph",
    "ProductGraphSpec",
    "ProductGraphRunRequest",
    "ProductGraphRunState",
    "list_product_graphs",
    "get_product_graph_spec",
    "build_research_portfolio_product_graph",
    "run_product_graph",
]
