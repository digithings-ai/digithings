"""Unit tests for the response-language directive builder."""

from __future__ import annotations

import pytest
from digigraph.graph.state import WorkflowState
from digigraph.languages import LANGUAGE_NAMES, resolve_language_directive
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit


def test_language_names_covers_the_curated_list() -> None:
    assert LANGUAGE_NAMES == {
        "en": "English",
        "de": "German",
        "it": "Italian",
        "es": "Spanish",
        "fr": "French",
    }


def test_resolve_language_directive_for_known_non_english_code() -> None:
    directive = resolve_language_directive("de")
    assert directive is not None
    assert "German" in directive


def test_resolve_language_directive_is_case_insensitive() -> None:
    assert resolve_language_directive("DE") == resolve_language_directive("de")


def test_resolve_language_directive_none_for_english() -> None:
    assert resolve_language_directive("en") is None


@pytest.mark.parametrize("bad", [None, "", "  ", "xx", "klingon", "<script>"])
def test_resolve_language_directive_none_for_unknown_or_missing(bad: str | None) -> None:
    assert resolve_language_directive(bad) is None


def test_workflow_state_declares_response_language() -> None:
    """LangGraph drops undeclared TypedDict keys — see #2097."""
    assert "response_language" in WorkflowState.__annotations__


def test_initial_graph_state_carries_response_language() -> None:
    state = _initial_graph_state(
        WorkflowRequest(prompt="hi", response_language="de"),
        "wf-lang",
    )
    assert state["response_language"] == "de"


def test_initial_graph_state_omits_response_language_when_unset() -> None:
    state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-lang-2")
    assert "response_language" not in state


def test_langgraph_preserves_response_language_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip response_language."""
    from langgraph.graph import END, START, StateGraph

    seen: dict[str, str | None] = {}

    def _capture(state: WorkflowState) -> dict:
        seen["response_language"] = state.get("response_language")
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile()
    graph.invoke({"prompt": "x", "response_language": "de"})
    assert seen["response_language"] == "de"
