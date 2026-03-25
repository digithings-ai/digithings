"""Workflow profiles and graph compilation (unit)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from digigraph.graph.graph import WORKFLOW_PROFILES, build_workflow_graph
from digigraph.project_config import DigiProjectConfig


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
