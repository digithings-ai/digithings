"""Regression coverage for the Finding 1 CRITICAL bug (final whole-branch review):
streaming events from a node running INSIDE a compiled subgraph were silently
dropped by ``graph.stream(..., stream_mode=["updates", "custom"], version="v2")``
because ``subgraphs=True`` was missing.

digigraph's real topology (``graph/research_subgraph.py``): ``build_research_subgraph()``
compiles ``research_node``/``research_brief_builder_node`` into their own
``CompiledStateGraph``, and ``graph/graph.py``'s ``build_workflow_graph()`` adds that
compiled subgraph as a single node -- ``builder.add_node("research", research_sg)`` --
on the OUTER graph. Every ``get_stream_writer()`` write the inner node makes (via
``_safe_stream_writer()`` in ``research.py``) therefore originates from inside a
subgraph, not the top level.

LangGraph filters "custom"/"updates" stream parts sourced from inside a subgraph
unless the outer ``.stream()`` call passes ``subgraphs=True`` -- without it, those
writes never reach the driver loop in ``workflow.py``'s
``run_digigraph_workflow_streaming``, which is exactly the bug this test pins.

This test builds a minimal outer-graph/inner-subgraph pair mirroring that real
shape (not digigraph's actual research_node, to stay independent of its HTTP/LLM
side effects) and proves a writer call from inside the inner subgraph surfaces as
a ``"custom"``-type part in the OUTER ``.stream()`` iteration when ``subgraphs=True``
is set -- and is silently dropped when it is not. The existing migrated test in
test_nodes.py (``test_stream_callback_from_state_rag_path_calls_it``) compiles
``research_node`` as a bare TOP-LEVEL node, which never exercises the parent ->
subgraph boundary, so it could not have caught this regression.
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph


class _InnerState(TypedDict, total=False):
    prompt: str
    inner_ran: bool


def _inner_writer_node(state: _InnerState) -> dict:
    """Mirrors research.py's ``_safe_stream_writer()`` write pattern: a node running
    inside a compiled subgraph calling ``get_stream_writer()`` and writing a
    ``(event_type, data)`` tuple -- exactly the shape ``_run_document_rag_path``'s
    ``stream_callback`` passes to ``writer(...)``."""
    writer = get_stream_writer()
    writer(("tool_call", {"name": "digisearch", "arguments": {"query": "hi"}}))
    return {"inner_ran": True}


def _build_outer_graph_with_inner_subgraph():
    """Outer StateGraph with the inner node compiled as its OWN subgraph and added
    via add_node -- mirrors build_research_subgraph() -> builder.add_node("research",
    research_sg) in graph/research_subgraph.py and graph/graph.py exactly."""
    inner_builder: StateGraph[_InnerState] = StateGraph(_InnerState)
    inner_builder.add_node("inner", _inner_writer_node)
    inner_builder.add_edge(START, "inner")
    inner_builder.add_edge("inner", END)
    inner_subgraph = inner_builder.compile()

    outer_builder: StateGraph[_InnerState] = StateGraph(_InnerState)
    outer_builder.add_node("research", inner_subgraph)
    outer_builder.add_edge(START, "research")
    outer_builder.add_edge("research", END)
    return outer_builder.compile()


@pytest.mark.unit
def test_subgraph_custom_write_surfaces_with_subgraphs_true() -> None:
    """The fix: with subgraphs=True, a get_stream_writer() write from inside the
    inner subgraph node arrives as a "custom"-type part in the OUTER stream()
    iteration."""
    outer_graph = _build_outer_graph_with_inner_subgraph()

    custom_parts: list[tuple[str, object]] = []
    for part in outer_graph.stream(
        {"prompt": "hi"},
        stream_mode=["updates", "custom"],
        version="v2",
        subgraphs=True,
    ):
        if part["type"] == "custom":
            custom_parts.append(part["data"])

    assert ("tool_call", {"name": "digisearch", "arguments": {"query": "hi"}}) in custom_parts


@pytest.mark.unit
def test_subgraph_custom_write_is_silently_dropped_without_subgraphs_true() -> None:
    """The regression, pinned directly: the exact same graph, the exact same writer
    call, but WITHOUT subgraphs=True on the outer .stream() call -- the "custom"
    part sourced from inside the subgraph never reaches the outer iteration at all.
    This is what run_digigraph_workflow_streaming did before the Finding 1 fix."""
    outer_graph = _build_outer_graph_with_inner_subgraph()

    custom_parts: list[tuple[str, object]] = []
    for part in outer_graph.stream(
        {"prompt": "hi"},
        stream_mode=["updates", "custom"],
        version="v2",
        # subgraphs=True deliberately omitted here.
    ):
        if part["type"] == "custom":
            custom_parts.append(part["data"])

    assert custom_parts == [], (
        "a custom write from inside a subgraph node must NOT surface without "
        "subgraphs=True -- if this assertion fails, LangGraph's behavior changed "
        "and the whole premise of the Finding 1 fix needs re-checking"
    )


@pytest.mark.unit
def test_top_level_updates_are_not_duplicated_by_inner_subgraph_updates() -> None:
    """The companion half of the Finding 1 fix: subgraphs=True also makes "updates"
    parts start arriving for nodes INSIDE the subgraph (non-empty ns), which would
    double-report a graph_update trace for both the inner node's completion and the
    outer "research" node's completion if not filtered. Only ns == () (top-level)
    updates should be treated as the outer graph's own per-node updates."""
    outer_graph = _build_outer_graph_with_inner_subgraph()

    top_level_updates: list[dict] = []
    inner_updates: list[dict] = []
    for part in outer_graph.stream(
        {"prompt": "hi"},
        stream_mode=["updates", "custom"],
        version="v2",
        subgraphs=True,
    ):
        if part["type"] != "updates":
            continue
        if part["ns"]:
            inner_updates.append(part["data"])
        else:
            top_level_updates.append(part["data"])

    # Exactly one top-level update ("research" completing) and at least one
    # non-empty-ns update (the inner "inner" node completing) -- proving both halves
    # of workflow.py's `if part["ns"]: continue` guard are actually exercised here:
    # without subgraphs=True there would be no inner_updates at all to filter.
    assert len(top_level_updates) == 1
    assert top_level_updates[0]["research"]["inner_ran"] is True
    assert len(inner_updates) >= 1
