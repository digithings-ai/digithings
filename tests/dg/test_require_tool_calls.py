"""Unit tests for the tool-calling requirement gate's terminal wiring: research_node
reads WorkflowState["require_tool_calls"] and threads tool_choice into run_tools.
"""

from __future__ import annotations

import pytest
from digigraph.graph.research import research_node

pytestmark = pytest.mark.unit


def _patch_research_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )


def test_research_node_forces_tool_choice_required_when_state_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy", "require_tool_calls": True})
    assert captured["tool_choice"] == "required"


def test_research_node_defaults_tool_choice_auto_when_state_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy", "require_tool_calls": False})
    assert captured["tool_choice"] == "auto"


def test_research_node_defaults_tool_choice_auto_when_state_key_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workflow invoked before this feature existed (or via a code path that never
    calls _initial_graph_state) has no require_tool_calls key at all — must not crash,
    must default to today's unchanged 'auto' behavior."""
    _patch_research_settings(monkeypatch)
    captured: dict = {}

    def fake_run_tools(*, tool_choice: str = "auto", **kwargs):
        captured["tool_choice"] = tool_choice
        return "ok"

    monkeypatch.setattr("digigraph.graph.research.run_tools", fake_run_tools)
    research_node({"prompt": "build me a strategy"})
    assert captured["tool_choice"] == "auto"
