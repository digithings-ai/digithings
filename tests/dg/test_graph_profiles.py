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
