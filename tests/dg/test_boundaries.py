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
