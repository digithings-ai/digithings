"""Wave 7h: shared error boundaries and workflow profile fallback."""

from __future__ import annotations

from queue import Queue
from unittest.mock import MagicMock, patch

import pytest
from digigraph.boundaries import GRAPH_RUNTIME_ERRORS, PROJECT_CONFIG_ERRORS, STREAM_SSE_ERRORS
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state, run_digigraph_workflow_streaming


@pytest.mark.unit
def test_project_config_errors_tuple() -> None:
    assert OSError in PROJECT_CONFIG_ERRORS
    assert ValueError in PROJECT_CONFIG_ERRORS


@pytest.mark.unit
def test_graph_runtime_errors_subset_of_stream_sse() -> None:
    for exc in GRAPH_RUNTIME_ERRORS:
        assert exc in STREAM_SSE_ERRORS


@pytest.mark.unit
def test_initial_graph_state_logs_and_falls_back_on_config_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("digigraph.workflow.DigiProjectConfig.load", side_effect=OSError("no config")):
        state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-1")
    assert state["workflow_profile"] == "full_stack"
    assert "workflow_profile load failed" in caplog.text


@pytest.mark.unit
def test_streaming_maps_graph_runtime_errors_to_sse_content() -> None:
    queue: Queue = Queue()

    def _boom(*_a, **_kw):
        raise RuntimeError("graph blew up")

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = _boom

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="x"), queue)

    events = []
    while not queue.empty():
        events.append(queue.get())

    assert ("content", "Error: graph blew up") in events
    assert events[-1] == ("done", None)


@pytest.mark.unit
def test_zero_hit_tool_result_reaches_browser_as_a_rag_sources_trace() -> None:
    """End-to-end: a zero-hit tool_result event — the exact payload shape digillm's
    run_tools builds from execute_search's dict, ``{"name": ..., "results": [],
    "rag_sources": [], "hit_count": 0, "query": ...}`` (see
    test_a_zero_hit_search_still_emits_a_trace in test_nodes.py) — must reach
    run_digigraph_workflow_streaming's real stream_callback and come out the other
    side as a ``trace`` event of type ``rag_sources`` carrying ``hit_count`` and
    ``query``. That event is exactly what the server forwards over SSE, so this is
    the payload the browser's activity UI actually receives.

    Before this fix, two things were broken here: the gate was
    ``data.get("rag_sources")`` (falsy on ``[]``), so a zero-hit search never
    produced a trace event at all; and even when a trace did fire, the payload
    only forwarded ``sources``/``tool`` — hit_count/query never left research.py.
    """
    queue: Queue = Queue()

    def fake_stream(
        initial, config=None, stream_mode=None, version=None, durability=None, subgraphs=None
    ):
        # Simulate the tool loop's get_stream_writer() call (research.py's
        # stream_callback) for a digisearch call that ran but found nothing,
        # arriving as a stream_mode=["updates","custom"], version="v2" custom part:
        # {"type": "custom", "ns": (), "data": (event_type, payload)}, exactly what
        # run_digigraph_workflow_streaming's driver loop unpacks.
        yield {
            "type": "custom",
            "ns": (),
            "data": (
                "tool_result",
                {
                    "name": "digisearch",
                    "content": "{}",
                    "results": [],
                    "rag_sources": [],
                    "hit_count": 0,
                    "query": "jwt",
                },
            ),
        }

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = fake_stream
    mock_graph.get_state.return_value = MagicMock(values={})

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="jwt"), queue)

    # Pin subgraphs=True at the real call site: research_node runs inside a compiled
    # subgraph (graph.py's build_research_subgraph()), not top-level, so without this
    # flag every custom/updates event from it is silently dropped by LangGraph -- the
    # exact regression the final whole-branch review caught (fixed in cc199942f).
    # fake_stream's default (subgraphs=None) means this suite would otherwise stay
    # green even if the flag were deleted from workflow.py again.
    assert mock_graph.stream.call_args.kwargs.get("subgraphs") is True

    events = []
    while not queue.empty():
        events.append(queue.get())

    rag_traces = [
        data
        for (kind, data) in events
        if kind == "trace" and isinstance(data, dict) and data.get("type") == "rag_sources"
    ]
    assert len(rag_traces) == 1, "a zero-hit tool_result must still emit a rag_sources trace"
    payload = rag_traces[0]["payload"]
    assert payload["sources"] == []
    assert payload["tool"] == "digisearch"
    assert payload["hit_count"] == 0
    assert payload["query"] == "jwt"


@pytest.mark.unit
def test_round_boundary_reaches_browser_as_its_own_trace_type() -> None:
    """#2306 follow-up: run_tools's on_tool_step("round_boundary", ...) — fired the
    moment a round's tool_calls becomes known, marking that round's already-streamed
    content as not the final answer — must reach the real stream_callback and come
    out as a `trace` event of type `round_boundary`, not silently dropped and not
    conflated with the plain `content` event type.

    This matters because `content` is the ONE event type server.py's
    _stream_completions_progressive still forwards to a client with
    suppress_tool_stream=True (digichat always sets this) — `tool_call`/
    `tool_result`/`reasoning` are all suppressed for that client, and an
    unrecognized event_type falls through every branch and reaches nothing. `trace`
    is the only channel left that still reaches such a client, so this fires on
    that channel specifically (same as code_block/rag_sources above), or the signal
    never leaves digigraph at all.
    """
    queue: Queue = Queue()

    def fake_stream(
        initial, config=None, stream_mode=None, version=None, durability=None, subgraphs=None
    ):
        # Simulate run_tools's on_tool_step("round_boundary", ...) (fired after a
        # round streamed narration content alongside its tool_calls) arriving as a
        # stream_mode=["updates","custom"], version="v2" custom part:
        # {"type": "custom", "ns": (), "data": (event_type, payload)}, exactly what
        # run_digigraph_workflow_streaming's driver loop unpacks.
        yield {
            "type": "custom",
            "ns": (),
            "data": (
                "round_boundary",
                {"round_idx": 1, "narration": "I will load the full notes now."},
            ),
        }

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = fake_stream
    mock_graph.get_state.return_value = MagicMock(values={})

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="occ"), queue)

    # Pin subgraphs=True at the real call site -- see the sibling test above for why.
    assert mock_graph.stream.call_args.kwargs.get("subgraphs") is True

    events = []
    while not queue.empty():
        events.append(queue.get())

    boundary_traces = [
        data
        for (kind, data) in events
        if kind == "trace" and isinstance(data, dict) and data.get("type") == "round_boundary"
    ]
    assert len(boundary_traces) == 1
    payload = boundary_traces[0]["payload"]
    assert payload["round_idx"] == 1
    assert payload["narration"] == "I will load the full notes now."
    # The bare, un-wrapped event ALSO still reaches the queue once (the final
    # unconditional `event_queue.put((event_type, data))`, same as tool_call/
    # tool_result alongside their own code_block/rag_sources traces above) -- this
    # is harmless: server.py's SSE loop has no branch matching a raw "round_boundary"
    # event_type, so it is silently ignored there. What matters is that the WRAPPED
    # trace event above exists at all.


@pytest.mark.unit
def test_tool_call_reaches_browser_as_a_started_trace() -> None:
    """#3417: digichat sets X-Suppress-Tool-Stream, so raw tool_call events never
    become SSE content. Without a wrapped ``trace`` the embed shows a bare caret
    until rag_sources arrives already-checked. The started trace is the running
    affordance.
    """
    queue: Queue = Queue()

    def fake_stream(
        initial, config=None, stream_mode=None, version=None, durability=None, subgraphs=None
    ):
        yield {
            "type": "custom",
            "ns": (),
            "data": (
                "tool_call",
                {"name": "digisearch", "arguments": {"query": "RS256 token exchange"}},
            ),
        }

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = fake_stream
    mock_graph.get_state.return_value = MagicMock(values={})

    with patch("digigraph.workflow.build_workflow_graph", return_value=mock_graph):
        run_digigraph_workflow_streaming(WorkflowRequest(prompt="RS256 token exchange"), queue)

    events = []
    while not queue.empty():
        events.append(queue.get())

    started = [
        data
        for (kind, data) in events
        if kind == "trace" and isinstance(data, dict) and data.get("type") == "tool_call"
    ]
    assert len(started) == 1
    payload = started[0]["payload"]
    assert payload["tool"] == "digisearch"
    assert payload["query"] == "RS256 token exchange"
    assert payload["status"] == "started"
