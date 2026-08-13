"""Workflow profiles and graph compilation (unit)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from digigraph.graph.graph import (
    WORKFLOW_PROFILES,
    _route_after_research,
    build_workflow_graph,
)
from digigraph.project_config import DigiProjectConfig
from langgraph.graph import END


@pytest.mark.unit
def test_workflow_profile_names() -> None:
    assert "full_stack" in WORKFLOW_PROFILES
    assert "research_rag" in WORKFLOW_PROFILES
    assert "quant_backtest" in WORKFLOW_PROFILES


@pytest.mark.unit
def test_build_workflow_graph_compiles() -> None:
    g = build_workflow_graph()
    assert g is not None


@pytest.mark.unit
def test_get_workflow_profile_env_override() -> None:
    with patch.dict(os.environ, {"DIGI_WORKFLOW_PROFILE": "quant_backtest"}, clear=False):
        assert DigiProjectConfig({}).get_workflow_profile() == "quant_backtest"


@pytest.mark.unit
def test_get_workflow_profile_yaml() -> None:
    with patch.dict(os.environ, {"DIGI_WORKFLOW_PROFILE": ""}, clear=False):
        cfg = DigiProjectConfig({"graph": {"workflow_profile": "research_rag"}})
        assert cfg.get_workflow_profile() == "research_rag"


@pytest.mark.unit
def test_route_after_research_ends_on_research_rag() -> None:
    state = {
        "workflow_profile": "research_rag",
        "strategy_name": "ema_cross",
        "symbols": ["AAPL"],
        "research_response": "ok",
    }
    assert _route_after_research(state) == END


@pytest.mark.unit
def test_route_after_research_ends_when_digiquant_url_empty() -> None:
    """Profile A / chat-only: empty DIGIQUANT_URL must never enter backtest."""
    state = {
        "workflow_profile": "full_stack",
        "strategy_name": "ema_cross",
        "symbols": ["AAPL"],
        "research_response": "ok",
    }
    with patch.dict(os.environ, {"DIGIQUANT_URL": ""}, clear=False):
        assert _route_after_research(state) == END


@pytest.mark.unit
def test_profile_a_digiproject_is_chat_only() -> None:
    """Bundled Profile A digiproject must not enable backtest / digiquant tools."""
    path = (
        Path(__file__).resolve().parents[2]
        / "infra"
        / "digichat-release"
        / "config"
        / "digiproject.yaml"
    )
    assert path.is_file(), f"missing Profile A digiproject: {path}"
    with patch.dict(os.environ, {"DIGI_WORKFLOW_PROFILE": ""}, clear=False):
        cfg = DigiProjectConfig.load(path)
        assert cfg.get_workflow_profile() == "research_rag"
        assert "backtest" not in cfg.get_enabled_agents()
        assert "optimize" not in cfg.get_enabled_agents()
        tools = set(cfg.get_allowed_tools())
        assert "digisearch" in tools
        assert "digivault_search_notes" in tools
        assert not any("digiquant" in t or "backtest" in t for t in tools)


@pytest.fixture(autouse=False)
def reset_workflow_graph_cache():
    """Reset the process-wide compiled-graph cache so build_workflow_graph() rebuilds
    with this test's env/module state, instead of returning whatever a prior test in
    this session already compiled and cached (graph.py:23-24, no invalidation)."""
    import digigraph.graph.graph as _graph_module

    original = _graph_module._workflow_graph_cache
    _graph_module._workflow_graph_cache = None
    yield
    _graph_module._workflow_graph_cache = original


@pytest.mark.unit
def test_build_workflow_graph_has_a_store(reset_workflow_graph_cache) -> None:
    """Cross-thread memory (Store) is distinct from the checkpointer (thread-scoped) --
    the compiled graph must have one so nodes can call get_store() successfully instead
    of silently no-op'ing."""
    graph = build_workflow_graph()
    assert graph.store is not None


@pytest.fixture(autouse=False)
def reset_store():
    """Reset the process-wide Store singleton between tests.

    Mirrors reset_checkpointer's save/restore pattern (test_graph.py) for the
    analogous get_store() singleton (graph.py) -- without this, a test that sets
    _store_instance = None to force a fresh get_store() call leaves a live
    InMemoryStore for the rest of the pytest session with no teardown.
    """
    import digigraph.graph.graph as _graph_module

    original_instance = _graph_module._store_instance
    _graph_module._store_instance = None
    yield
    _graph_module._store_instance = original_instance


@pytest.mark.unit
def test_get_store_defaults_to_in_memory(
    monkeypatch: pytest.MonkeyPatch, reset_store
) -> None:
    from digigraph.graph.graph import get_store

    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    store = get_store()
    assert type(store).__name__ == "InMemoryStore"


@pytest.mark.unit
def test_backtest_and_optimize_nodes_have_retry_policy(reset_workflow_graph_cache) -> None:
    """A single dropped network packet must not fail the whole backtest/optimize run —
    RetryPolicy scoped to httpx.RequestError (transient network failures) only, never
    HTTPStatusError (a 4xx/5xx is a real rejection and must not be blindly retried)."""
    import httpx

    graph = build_workflow_graph()
    for name in ("backtest", "optimize"):
        node = graph.nodes[name]
        assert node.retry_policy, f"{name} node has no retry_policy"
        policy = node.retry_policy[0]
        assert policy.retry_on is httpx.RequestError
        assert policy.max_attempts == 3
