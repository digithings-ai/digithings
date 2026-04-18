"""Digi project configuration. Loads project-level YAML for agents, indexes, MCP."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


def _subst_env(val: Any) -> Any:
    """Replace ${VAR_NAME} with os.environ value."""
    if isinstance(val, str):
        for m in re.finditer(r"\$\{([^}]+)\}", val):
            key = m.group(1)
            val = val.replace(m.group(0), os.environ.get(key, ""))
        return val
    if isinstance(val, dict):
        return {k: _subst_env(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_subst_env(v) for v in val]
    return val


def load_project_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load project YAML. Path from DIGI_PROJECT_CONFIG or default."""
    cfg_path = path or os.environ.get("DIGI_PROJECT_CONFIG")
    if not cfg_path:
        default = Path("config") / "digi_project.yaml"
        if default.exists():
            cfg_path = default
        else:
            return {}
    p = Path(cfg_path)
    if not p.exists():
        return {}
    raw = p.read_text()
    data = yaml.safe_load(raw) or {}
    return _subst_env(data)


def _discover_indexes_from_dir(project_root: Path, indexes_dir: str) -> list[dict[str, Any]]:
    """Discover index definitions from a directory: each *.yaml is one index (index_name, backend from file)."""
    dir_path = (project_root / indexes_dir).resolve()
    if not dir_path.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for yaml_path in sorted(dir_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            continue
        name = (data.get("index_name") or yaml_path.stem or "").strip()
        if not name:
            continue
        # config_ref relative to project root (so loaders can resolve from DIGI_PROJECT_CONFIG parent)
        try:
            rel = yaml_path.relative_to(project_root)
        except ValueError:
            rel = Path(yaml_path.name)
        config_ref = str(rel).replace("\\", "/")
        entries.append({
            "name": name,
            "backend": data.get("backend", "azure_search"),
            "config_ref": config_ref,
        })
    return entries


# Config cache: (resolved_path, mtime) -> DigiProjectConfig. Eliminates repeated disk reads per request.
_config_cache: dict[tuple[str, float], "DigiProjectConfig"] = {}


class DigiProjectConfig:
    """Project-level config: agents, indexes, MCP exposure."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        config_path: str | Path | None = None,
    ) -> None:
        data = data or {}
        self._data = data
        self._config_path = Path(config_path).resolve() if config_path else None
        self.project = data.get("project", {})
        self.agents = data.get("agents", {})
        indexes = data.get("indexes", [])
        indexes_dir = (data.get("indexes_dir") or "").strip()
        if indexes_dir and self._config_path:
            project_root = self._config_path.parent
            discovered = _discover_indexes_from_dir(project_root, indexes_dir)
            if discovered:
                indexes = discovered
        self.indexes = indexes
        self.mcp = data.get("mcp", {})
        self.services = data.get("services", {})

    @classmethod
    def load(cls, path: str | Path | None = None) -> "DigiProjectConfig":
        """Load from DIGI_PROJECT_CONFIG or path. Results are cached by (path, mtime)."""
        cfg_path = path or os.environ.get("DIGI_PROJECT_CONFIG")
        if not cfg_path:
            default = Path("config") / "digi_project.yaml"
            cfg_path = str(default) if default.exists() else None

        if cfg_path:
            p = Path(cfg_path)
            if p.exists():
                try:
                    mtime = p.stat().st_mtime
                    cache_key = (str(p.resolve()), mtime)
                    cached = _config_cache.get(cache_key)
                    if cached is not None:
                        return cached
                except OSError:
                    pass

        data = load_project_config(cfg_path) if cfg_path else load_project_config()
        obj = cls(data, config_path=cfg_path)

        if cfg_path:
            p = Path(cfg_path)
            if p.exists():
                try:
                    mtime = p.stat().st_mtime
                    _config_cache[(str(p.resolve()), mtime)] = obj
                except OSError:
                    pass
        return obj

    def get_enabled_agents(self) -> list[str]:
        """List of enabled agent names."""
        return self.agents.get("enabled", ["research", "backtest"])

    def get_llm_mode(self) -> str:
        """LLM mode: test | medium | best."""
        return self.agents.get("llm_mode", "test")

    def get_indexes(self) -> list[dict[str, Any]]:
        """Index configs for DigiSearch."""
        return self.indexes

    def get_search_index_name(self) -> str:
        """Index name for API calls (first index entry name). Fallback: DIGISEARCH_INDEX env or 'default'."""
        indexes = self.get_indexes()
        if indexes and isinstance(indexes[0], dict):
            return str(indexes[0].get("name", "") or "").strip() or os.environ.get("DIGISEARCH_INDEX", "default")
        return os.environ.get("DIGISEARCH_INDEX", "default")

    def get_search_index_config(self) -> dict[str, Any]:
        """Load full index YAML for the search index (first index's config_ref). Returns {} if not found."""
        indexes = self.get_indexes()
        if not indexes or not isinstance(indexes[0], dict):
            return {}
        entry = indexes[0]
        config_ref = entry.get("config_ref") or entry.get("config_ref_path")
        if not config_ref or not isinstance(config_ref, str):
            return {}
        base = self._config_path.parent if self._config_path else Path.cwd()
        index_yaml = (base / config_ref).resolve()
        if not index_yaml.exists():
            return {}
        try:
            return yaml.safe_load(index_yaml.read_text()) or {}
        except Exception:
            return {}

    def get_search_index_display_name(self) -> str:
        """Index name for UI display: from index definition (config_ref) index_name when present, else get_search_index_name()."""
        data = self.get_search_index_config()
        if data:
            name = (data.get("index_name") or "").strip()
            if name:
                return name
        indexes = self.get_indexes()
        if indexes and isinstance(indexes[0], dict):
            return str(indexes[0].get("name", "") or "").strip() or os.environ.get("DIGISEARCH_INDEX", "default")
        return os.environ.get("DIGISEARCH_INDEX", "default")

    def get_mcp_tools(self) -> list[str]:
        """Tool names to expose via MCP. When indexes were discovered from indexes_dir, digisearch_{name}_query is added per index."""
        explicit = self.mcp.get("tools", [])
        indexes = self.get_indexes()
        # Auto-add digisearch_*_query for each index only when we have indexes_dir (discovered); avoid duplicates
        digisearch_prefix = "digisearch_"
        digisearch_suffix = "_query"
        seen = {t for t in explicit if t.startswith(digisearch_prefix) and t.endswith(digisearch_suffix)}
        out = list(explicit)
        for entry in indexes:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or ""
            if not name:
                continue
            tool_name = f"{digisearch_prefix}{name.replace('-', '_')}{digisearch_suffix}"
            if tool_name not in seen:
                seen.add(tool_name)
                out.append(tool_name)
        return out

    def get_mcp_port(self) -> int:
        """MCP server port."""
        return int(self.mcp.get("port", 8765))

    def is_mcp_enabled(self) -> bool:
        """Whether MCP server should run."""
        return self.mcp.get("enabled", True)

    def get_digisearch_url(self) -> str:
        """DigiSearch service URL."""
        return self.services.get("digisearch_url", os.environ.get("DIGISEARCH_URL", "http://digisearch:8002"))

    def get_digiquant_url(self) -> str:
        """DigiQuant service URL."""
        return self.services.get("digiquant_url", os.environ.get("DIGIQUANT_URL", "http://digiquant:8001"))

    def get_research_system_prompt(self) -> str | None:
        """Custom system prompt for research node. When set, LLM responds in natural language (no JSON)."""
        return self.agents.get("research_system_prompt")

    def get_run_data_dir(self) -> str | None:
        """Run storage root for temporary dataset files (session/run-scoped). None = feature disabled."""
        return (
            self._data.get("run_data_dir")
            or (self._data.get("run_storage") or {}).get("dir")
            or None
        )

    def get_enabled_skills(self) -> list[str]:
        """Skill ids to enable for the research node (e.g. search, sitaas_rag).
        From project YAML skills.enabled, or default [\"search\", \"sitaas_rag\"] when
        document mode and run_data_dir are in use.
        """
        skills_cfg = self._data.get("skills") or {}
        explicit = skills_cfg.get("enabled")
        if isinstance(explicit, list) and explicit:
            return [str(s) for s in explicit]
        # Default: search + sitaas_rag so registry returns search tools and delegate agents when run_data_dir set
        return ["search", "sitaas_rag"]

    def get_planning_mode(self) -> bool:
        """Whether to use plan-and-execute: after create_plan tool, run executor and then synthesis."""
        return bool(self.agents.get("planning_mode"))

    def get_allowed_tools(self) -> list[str]:
        """Orchestrator tool names allowed for this project (empty if unset). From agents.allowed_tools."""
        raw = self.agents.get("allowed_tools")
        if not isinstance(raw, list) or not raw:
            return []
        return [str(x).strip() for x in raw if x and str(x).strip()]

    def get_workflow_profile(self) -> str:
        """Workflow topology profile. Env DIGI_WORKFLOW_PROFILE overrides YAML.

        Values: full_stack (default), research_rag, quant_backtest, plan_execute.
        plan_execute uses the same graph as full_stack; enable agents.planning_mode for planner behavior.
        """
        env = (os.environ.get("DIGI_WORKFLOW_PROFILE") or "").strip().lower()
        if env:
            return env
        graph_cfg = self._data.get("graph") or {}
        raw = graph_cfg.get("workflow_profile") or self.agents.get("workflow_profile")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower()
        return "full_stack"
