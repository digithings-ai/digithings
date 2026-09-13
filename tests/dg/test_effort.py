"""Unit tests for X-Digi-Effort directive."""

from __future__ import annotations

import pytest
from digigraph.effort import resolve_effort_directive
from digigraph.graph.state import WorkflowState
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit


def test_resolve_effort_directive() -> None:
    assert resolve_effort_directive("low") is not None
    assert "short" in (resolve_effort_directive("low") or "")
    assert resolve_effort_directive("high") is not None
    assert resolve_effort_directive("medium") is None
    assert resolve_effort_directive("nope") is None
    assert resolve_effort_directive("<script>") is None


def test_workflow_state_declares_effort() -> None:
    assert "effort" in WorkflowState.__annotations__


def test_initial_graph_state_carries_effort() -> None:
    state = _initial_graph_state(WorkflowRequest(prompt="hi", effort="high"), "wf-e")
    assert state["effort"] == "high"
    cleared = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-e")
    assert "effort" in cleared
    assert cleared["effort"] is None
