"""Phase 1: LangGraph workflow graph tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digigraph.graph import build_workflow_graph


@pytest.mark.unit
def test_build_workflow_graph_compiles() -> None:
    """Graph compiles and has invoke."""
    g = build_workflow_graph()
    assert callable(g.invoke)
    graph_inner = g.get_graph()
    assert "optimize" in graph_inner.nodes


@pytest.mark.unit
def test_graph_invoke_returns_state_with_expected_keys() -> None:
    """Invoke returns state. When LLM fails, research returns error (no fallback)."""
    with patch("digigraph.graph.research.chat_completion", side_effect=Exception("no-llm")):
        g = build_workflow_graph()
        out = g.invoke({"prompt": "mean reversion on tech"}, config={"configurable": {"thread_id": "test"}})
    assert "strategy_name" in out
    assert "symbols" in out
    assert out.get("research_note") == "error"
    assert out.get("error")
    assert "backtest_result" in out or "error" in out


@pytest.mark.unit
def test_graph_research_returns_error_when_llm_raises() -> None:
    """When LLM raises, research node returns error; no heuristic fallback."""
    with patch("digigraph.graph.research.chat_completion", side_effect=Exception("unavailable")):
        g = build_workflow_graph()
        out = g.invoke({"prompt": "stat arb tech"}, config={"configurable": {"thread_id": "test"}})
    assert out.get("strategy_name") is None
    assert out.get("research_note") == "error"
    assert "unavailable" in str(out.get("error", ""))


@pytest.mark.unit
def test_graph_research_only_when_backtest_disabled() -> None:
    """When agents.enabled excludes backtest (e.g. Sitas), graph goes research → END."""
    mock_cfg = type("Cfg", (), {"get_enabled_agents": lambda self: ["research"]})()
    with patch("digigraph.graph.graph.DigiProjectConfig") as m:
        m.load.return_value = mock_cfg
        g = build_workflow_graph()
    with patch("digigraph.graph.research.chat_completion", side_effect=Exception("no-llm")):
        out = g.invoke({"prompt": "search docs"}, config={"configurable": {"thread_id": "test"}})
    assert "backtest_result" not in out or out.get("backtest_result") is None
    assert out.get("error")
