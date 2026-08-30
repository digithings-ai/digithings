"""Unit tests for the tool-calling requirement gate's terminal wiring: research_node
reads WorkflowState["require_tool_calls"] and threads tool_choice into run_tools.
"""

from __future__ import annotations

import logging

import pytest
from digigraph.graph.research import RESEARCH_SYSTEM, research_node

pytestmark = pytest.mark.unit

_SCOPE_WARN = "quant/augmented path"


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


def test_research_node_rejects_quant_path_when_require_tool_calls_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2384: quant/augmented path has no tool loop — fail closed when the mandate is set."""
    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", RESEARCH_SYSTEM),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._run_quant_or_augmented_path",
        lambda **_kwargs: {
            "strategy_name": None,
            "symbols": None,
            "research_note": "ok",
        },
    )

    out = research_node({"prompt": "build me a strategy", "require_tool_calls": True})
    assert out.get("research_note") == "error"
    assert "require_tool_calls" in (out.get("error") or "")


def test_research_node_does_not_warn_on_quant_path_when_require_tool_calls_false(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", RESEARCH_SYSTEM),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._run_quant_or_augmented_path",
        lambda **_kwargs: {
            "strategy_name": None,
            "symbols": None,
            "research_note": "ok",
        },
    )

    with caplog.at_level(logging.WARNING, logger="digigraph.graph.research"):
        research_node({"prompt": "build me a strategy", "require_tool_calls": False})

    assert not any(_SCOPE_WARN in r.message for r in caplog.records)


def test_research_node_does_not_warn_on_document_rag_path(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Document RAG is the one path that enforces tool_choice — no scope warning."""
    _patch_research_settings(monkeypatch)
    monkeypatch.setattr(
        "digigraph.graph.research.run_tools",
        lambda **_kwargs: "ok",
    )

    with caplog.at_level(logging.WARNING, logger="digigraph.graph.research"):
        research_node({"prompt": "build me a strategy", "require_tool_calls": True})

    assert not any(_SCOPE_WARN in r.message for r in caplog.records)
