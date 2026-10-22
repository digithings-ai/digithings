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


def _patch_research_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )


@pytest.mark.parametrize("effort", ["low", "high", None])
def test_research_node_forwards_chat_effort_as_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch, effort: str | None
) -> None:
    """The chat's /effort reaches the tool loop; None keeps the model default."""
    from digigraph.graph.research import research_node

    _patch_research_settings(monkeypatch)
    captured: dict[str, object] = {}

    def fake_run_tools(**kwargs: object) -> str:
        captured["reasoning_effort"] = kwargs.get("reasoning_effort", "missing")
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "hi", "effort": effort})
    assert captured["reasoning_effort"] == effort


def test_llm_client_run_tools_passes_reasoning_effort_to_digillm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import digigraph.llm_client as llm_client

    captured: dict[str, object] = {}

    def fake_digillm_run_tools(*_args: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(llm_client, "_digillm_run_tools", fake_digillm_run_tools)
    llm_client.run_tools(
        "deepseek/deepseek-v4.1-flash-1017",
        [{"role": "user", "content": "hi"}],
        [],
        lambda *_: "",
        on_tool_step=lambda *_: None,
        reasoning_effort="high",
    )
    assert captured["reasoning_effort"] == "high"
    assert captured["stream_deltas"] is True
