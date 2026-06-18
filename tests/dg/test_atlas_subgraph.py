"""Scaffolding-spike tests for the Atlas research subgraph (issue #146)."""

from __future__ import annotations

import uuid

import pytest

from digigraph.graph import AtlasResearchState, atlas_subgraph, build_atlas_subgraph


@pytest.mark.unit
def test_atlas_subgraph_populates_all_state_fields():
    """Invoking the compiled subgraph walks research → synthesize → persist."""
    result = atlas_subgraph.invoke(AtlasResearchState(query="test"))

    # LangGraph returns either a dict or a state model depending on version; normalize.
    state = result if isinstance(result, dict) else result.model_dump()

    assert state["query"] == "test"
    assert isinstance(state["sources"], list) and len(state["sources"]) == 1
    assert isinstance(state["findings"], list) and len(state["findings"]) == 1
    assert isinstance(state["synthesis"], str) and state["synthesis"]
    # persisted_id should be a valid UUID string.
    uuid.UUID(state["persisted_id"])


@pytest.mark.unit
def test_build_atlas_subgraph_returns_fresh_compiled_graph():
    """Factory returns a compiled graph distinct from the module-level singleton."""
    sg = build_atlas_subgraph()
    assert sg is not atlas_subgraph
    result = sg.invoke(AtlasResearchState(query="x", domain="macro"))
    state = result if isinstance(result, dict) else result.model_dump()
    assert state["domain"] == "macro"
    assert state["persisted_id"] is not None
