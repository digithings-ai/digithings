"""Unit tests for digigraph.project_config."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from digigraph.project_config import DigiProjectConfig, _resolve_config_path, load_project_config


def test_load_project_config_returns_empty_when_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    result = load_project_config()
    # May find config/digi_project.yaml if it exists; otherwise {}
    assert isinstance(result, dict)


def test_load_project_config_from_path(tmp_path: Path) -> None:
    cfg_file = tmp_path / "digi_project.yaml"
    cfg_file.write_text("""
project:
  name: test-desk
agents:
  enabled: [research, backtest]
  llm_mode: medium
indexes:
  - name: docs
    backend: chroma
mcp:
  enabled: true
  port: 8765
  tools: [digigraph_workflow]
""")
    result = load_project_config(str(cfg_file))
    assert result["project"]["name"] == "test-desk"
    assert result["agents"]["llm_mode"] == "medium"
    assert result["agents"]["enabled"] == ["research", "backtest"]
    assert len(result["indexes"]) == 1
    assert result["indexes"][0]["name"] == "docs"
    assert result["mcp"]["tools"] == ["digigraph_workflow"]


def test_digi_project_config_getters(tmp_path: Path) -> None:
    cfg_file = tmp_path / "digi_project.yaml"
    cfg_file.write_text("""
project:
  name: my-desk
agents:
  enabled: [research]
  llm_mode: best
indexes:
  - name: research_docs
mcp:
  enabled: true
  port: 9000
  tools: [digigraph_workflow, digisearch_research_docs_query]
""")
    cfg = DigiProjectConfig.load(str(cfg_file))
    assert cfg.get_enabled_agents() == ["research"]
    assert cfg.get_llm_mode() == "best"
    assert cfg.get_mcp_port() == 9000
    assert cfg.is_mcp_enabled() is True
    assert cfg.get_mcp_tools() == ["digigraph_workflow", "digisearch_research_docs_query"]
    assert len(cfg.get_indexes()) == 1
    assert cfg.get_indexes()[0]["name"] == "research_docs"


def test_digi_project_config_defaults() -> None:
    cfg = DigiProjectConfig({})
    assert cfg.get_enabled_agents() == ["research", "backtest"]
    assert cfg.get_llm_mode() == "test"
    assert cfg.get_mcp_port() == 8765
    assert cfg.is_mcp_enabled() is True
    assert cfg.get_allowed_tools() == []


def test_digi_project_config_allowed_tools() -> None:
    cfg = DigiProjectConfig({"agents": {"allowed_tools": ["digisearch", "todo"]}})
    assert cfg.get_allowed_tools() == ["digisearch", "todo"]


def test_digi_project_config_indexes_dir_discovery(tmp_path: Path) -> None:
    """When indexes_dir is set, indexes are discovered from that directory."""
    (tmp_path / "indexes").mkdir()
    (tmp_path / "indexes" / "unified-content-index.yaml").write_text("index_name: unified-content-index\n")
    (tmp_path / "config.yaml").write_text("""
project:
  name: sitas
indexes_dir: indexes
mcp:
  tools: [digigraph_workflow]
""")
    cfg = DigiProjectConfig.load(str(tmp_path / "config.yaml"))
    indexes = cfg.get_indexes()
    assert len(indexes) == 1
    assert indexes[0]["name"] == "unified-content-index"
    assert indexes[0]["config_ref"] == "indexes/unified-content-index.yaml"
    tools = cfg.get_mcp_tools()
    assert "digigraph_workflow" in tools
    assert "digisearch_unified_content_index_query" in tools


@pytest.mark.unit
def test_resolve_config_path_prefers_digiproject_yaml_over_config_yaml(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When config.yaml is given but digiproject.yaml sibling exists, prefer digiproject.yaml and warn."""
    (tmp_path / "config.yaml").write_text("project:\n  name: old\n")
    (tmp_path / "digiproject.yaml").write_text("project:\n  name: new\n")
    with caplog.at_level(logging.WARNING, logger="digigraph.project_config"):
        resolved = _resolve_config_path(str(tmp_path / "config.yaml"))
    assert resolved is not None
    assert resolved.name == "digiproject.yaml"
    assert "DEPRECATED" in caplog.text
    assert "digiproject.yaml" in caplog.text


@pytest.mark.unit
def test_resolve_config_path_warns_on_config_yaml_when_no_digiproject(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When config.yaml is given and no digiproject.yaml exists, use config.yaml with deprecation warning."""
    (tmp_path / "config.yaml").write_text("project:\n  name: legacy\n")
    with caplog.at_level(logging.WARNING, logger="digigraph.project_config"):
        resolved = _resolve_config_path(str(tmp_path / "config.yaml"))
    assert resolved is not None
    assert resolved.name == "config.yaml"
    assert "DEPRECATED" in caplog.text


@pytest.mark.unit
def test_resolve_config_path_default_prefers_digiproject_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default search (no explicit path) prefers digiproject.yaml in cwd over config/digi_project.yaml."""
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "digiproject.yaml").write_text("project:\n  name: preferred\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "digi_project.yaml").write_text("project:\n  name: fallback\n")
    resolved = _resolve_config_path()
    assert resolved is not None
    assert resolved.name == "digiproject.yaml"


@pytest.mark.unit
def test_load_project_config_legacy_config_yaml(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """load_project_config honours config.yaml with deprecation warning when no digiproject.yaml."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("project:\n  name: sitaas-legacy\n")
    with caplog.at_level(logging.WARNING, logger="digigraph.project_config"):
        result = load_project_config(str(cfg_file))
    assert result["project"]["name"] == "sitaas-legacy"
    assert "DEPRECATED" in caplog.text


def test_get_search_index_config_loads_index_yaml(tmp_path: Path) -> None:
    """get_search_index_config() returns full index YAML when config_ref exists."""
    (tmp_path / "indexes").mkdir()
    (tmp_path / "indexes" / "unified-content-index.yaml").write_text("""
index_name: unified-content-index
filterable_fields:
  - sourceType
  - itemType
result_metadata_fields:
  - subject
  - fromAddress
""")
    (tmp_path / "config.yaml").write_text("""
project:
  name: sitas
indexes_dir: indexes
mcp:
  tools: []
""")
    cfg = DigiProjectConfig.load(str(tmp_path / "config.yaml"))
    index_config = cfg.get_search_index_config()
    assert index_config.get("index_name") == "unified-content-index"
    assert "sourceType" in (index_config.get("filterable_fields") or [])
    assert "subject" in (index_config.get("result_metadata_fields") or [])


@pytest.mark.unit
def test_unsupported_version_warns(tmp_path: Path) -> None:
    """Given a digiproject.yaml with an unrecognised version, loader emits a UserWarning but still returns a valid config."""
    cfg_file = tmp_path / "digiproject.yaml"
    cfg_file.write_text("""
version: v99alpha1
project:
  name: future-project
agents:
  enabled: [research]
""")
    with pytest.warns(UserWarning, match="v99alpha1"):
        cfg = DigiProjectConfig.load(str(cfg_file))
    # still returns a valid config
    assert cfg.project.get("name") == "future-project"
    assert cfg.get_enabled_agents() == ["research"]
