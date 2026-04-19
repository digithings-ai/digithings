"""Phase 1: LangGraph workflow graph tests."""

from __future__ import annotations

import digigraph.graph.graph as _graph_module
from unittest.mock import patch

import pytest

from digigraph.graph import build_workflow_graph


@pytest.fixture(autouse=False)
def reset_checkpointer():
    """Reset the process-wide checkpointer singleton between tests."""
    original_instance = _graph_module._checkpointer_instance
    original_cm_holders = list(_graph_module._cm_holders)
    _graph_module._checkpointer_instance = None
    _graph_module._cm_holders = []
    yield
    _graph_module._checkpointer_instance = original_instance
    _graph_module._cm_holders = original_cm_holders


@pytest.mark.unit
def test_checkpointer_defaults_to_sqlite_when_project_active(
    tmp_path, monkeypatch, reset_checkpointer
):
    """When digiproject.yaml is present and DIGI_CHECKPOINTER is unset, resolved checkpointer is sqlite."""
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text("version: v1alpha1\nproject:\n  name: test\n")
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    monkeypatch.setenv("DIGI_CHECKPOINTER_SQLITE_URI", str(tmp_path / "ckpt.sqlite"))

    ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    assert type(ckpt).__name__ == "SqliteSaver", (
        f"Expected SqliteSaver when project active, got {type(ckpt).__name__!r}"
    )


@pytest.mark.unit
def test_checkpointer_defaults_to_memory_without_project(monkeypatch, reset_checkpointer):
    """When no digiproject.yaml is present and DIGI_CHECKPOINTER is unset, resolved checkpointer is memory."""
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)

    with patch("digigraph.project_config._resolve_config_path", return_value=None):
        ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    # LangGraph >= 1.x aliases MemorySaver -> InMemorySaver
    assert type(ckpt).__name__ in ("MemorySaver", "InMemorySaver"), (
        f"Expected memory-based checkpointer without project, got {type(ckpt).__name__!r}"
    )


@pytest.mark.unit
def test_checkpointer_env_overrides_project_default(tmp_path, monkeypatch, reset_checkpointer):
    """DIGI_CHECKPOINTER env var overrides the project-based default."""
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text("version: v1alpha1\nproject:\n  name: test\n")
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.setenv("DIGI_CHECKPOINTER", "memory")

    ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    # LangGraph >= 1.x aliases MemorySaver -> InMemorySaver
    assert type(ckpt).__name__ in ("MemorySaver", "InMemorySaver"), (
        f"Expected memory-based checkpointer (env override), got {type(ckpt).__name__!r}"
    )


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
        out = g.invoke(
            {"prompt": "mean reversion on tech"}, config={"configurable": {"thread_id": "test"}}
        )
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
