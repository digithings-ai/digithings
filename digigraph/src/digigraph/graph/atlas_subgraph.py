"""Atlas research subgraph — scaffolding spike (issue #146).

Minimal LangGraph StateGraph with three stub nodes (research → synthesize → persist)
and a Pydantic v2 state model. Real LLM calls and DB persistence are intentionally
out of scope for this spike; follow-up tasks under epic #10 will replace the stubs.

This subgraph is *not* wired into the default supervisor — it is exposed only so
parent graphs can invoke it once the rest of the Atlas epic lands.
"""

from __future__ import annotations

import uuid

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


class AtlasResearchState(BaseModel):
    """State for the Atlas research subgraph.

    Populated progressively by the three nodes:
    - ``research_node`` fills ``sources`` and ``findings``.
    - ``synthesize_node`` fills ``synthesis``.
    - ``persist_node`` fills ``persisted_id``.
    """

    query: str
    domain: str | None = None
    sources: list[dict] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    synthesis: str | None = None
    persisted_id: str | None = None


def research_node(state: AtlasResearchState) -> AtlasResearchState:
    """STUB: emit one synthetic source + finding. No real LLM call in this spike."""
    return state.model_copy(
        update={
            "sources": [{"id": "stub-source-1", "title": "Synthetic source", "url": None}],
            "findings": ["Synthetic finding for query: " + state.query],
        }
    )


def synthesize_node(state: AtlasResearchState) -> AtlasResearchState:
    """STUB: trivial synthesis summarizing finding count."""
    return state.model_copy(
        update={"synthesis": f"Synthesized from {len(state.findings)} findings"}
    )


def persist_node(state: AtlasResearchState) -> AtlasResearchState:
    """STUB: generate a UUID. No DB write in this spike."""
    return state.model_copy(update={"persisted_id": str(uuid.uuid4())})


def build_atlas_subgraph():
    """Compile the Atlas research subgraph: research → synthesize → persist."""
    g: StateGraph[AtlasResearchState] = StateGraph(AtlasResearchState)
    g.add_node("research", research_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("persist", persist_node)
    g.add_edge(START, "research")
    g.add_edge("research", "synthesize")
    g.add_edge("synthesize", "persist")
    g.add_edge("persist", END)
    return g.compile()


# Compiled subgraph, importable by parent graphs once Atlas wiring lands.
atlas_subgraph = build_atlas_subgraph()
