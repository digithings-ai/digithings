"""Phase 1: LangGraph workflow graph tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digigraph.graph import build_workflow_graph
from digigraph.graph.state import WorkflowState


@pytest.mark.unit
def test_build_workflow_graph_compiles() -> None:
    """Graph compiles and has invoke."""
    g = build_workflow_graph()
    assert callable(g.invoke)


@pytest.mark.unit
def test_graph_invoke_returns_state_with_expected_keys() -> None:
    """Invoke returns state containing strategy_name, symbols, backtest_result or error."""
    with patch("digigraph.graph.nodes.chat_completion", side_effect=Exception("no-llm")):
        g = build_workflow_graph()
        out = g.invoke({"prompt": "mean reversion on tech"})
    assert "strategy_name" in out
    assert "symbols" in out
    assert out["strategy_name"] == "mean_reversion"
    assert "AAPL" in out["symbols"]
    assert "backtest_result" in out or "error" in out


@pytest.mark.unit
def test_graph_research_fallback_when_llm_raises() -> None:
    """When LLM raises, research node uses heuristic fallback."""
    with patch("digigraph.graph.nodes.chat_completion", side_effect=Exception("unavailable")):
        g = build_workflow_graph()
        out = g.invoke({"prompt": "stat arb tech"})
    assert out.get("strategy_name") == "mean_reversion_stat_arb"
    assert out.get("research_note") == "heuristic-fallback"
