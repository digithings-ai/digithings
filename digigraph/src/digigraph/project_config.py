"""Digi project configuration. Loads project-level YAML for agents, indexes, MCP."""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path
from typing import Any

import yaml

from digigraph.env_utils import resolve_env_refs

logger = logging.getLogger(__name__)

SUPPORTED_PROJECT_VERSIONS: frozenset[str] = frozenset({"v1alpha1"})


def _subst_env(val: Any) -> Any:
    """Replace ${VAR_NAME} / ${VAR:-default} with os.environ value.

    Delegates to the shared :func:`digigraph.env_utils.resolve_env_refs` helper
    in silent mode (missing vars → ``""``).
    """
    return resolve_env_refs(val)


def _resolve_config_path(path: str | Path | None = None) -> Path | None:
    """Resolve config file path with backward-compat for legacy config.yaml name.

    Search order (when no explicit path):
      digiproject.yaml → config/digiproject.yaml → config/digi_project.yaml
    """
    explicit = path or os.environ.get("DIGI_PROJECT_CONFIG")
    if explicit:
        p = Path(explicit)
        if p.name == "config.yaml":
            preferred = p.parent / "digiproject.yaml"
            if preferred.exists():
                logger.warning(
                    "DEPRECATED: project config at %s; rename to digiproject.yaml (v1alpha1). "
                    "Found digiproject.yaml in the same directory — loading it instead.",
                    p,
                )
                return preferred
            if p.exists():
                logger.warning(
                    "DEPRECATED: project config file %s should be renamed to digiproject.yaml (v1alpha1).",
                    p,
                )
                return p
        return p if p.exists() else None
    for candidate in (
        Path("digiproject.yaml"),
        Path("config") / "digiproject.yaml",
        Path("config") / "digi_project.yaml",
    ):
        if candidate.exists():
            return candidate
    return None


def load_project_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load project YAML. Path from DIGI_PROJECT_CONFIG or default."""
    resolved = _resolve_config_path(path)
    if resolved is None:
        return {}
    raw = resolved.read_text()
    data = yaml.safe_load(raw) or {}
    data = _subst_env(data)
    version = data.get("version")
    if version is not None and version not in SUPPORTED_PROJECT_VERSIONS:
        warnings.warn(
            f"digiproject.yaml declares unsupported version '{version}'. "
            f"Supported versions: {sorted(SUPPORTED_PROJECT_VERSIONS)}. "
            "The file will still be loaded but may not behave as expected.",
            UserWarning,
            stacklevel=2,
        )
    return data


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
        entries.append(
            {
                "name": name,
                "backend": data.get("backend", "azure_search"),
                "config_ref": config_ref,
            }
        )
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
        resolved = _resolve_config_path(path)

        if resolved is not None:
            try:
                mtime = resolved.stat().st_mtime
                cache_key = (str(resolved.resolve()), mtime)
                cached = _config_cache.get(cache_key)
                if cached is not None:
                    return cached
            except OSError:
                pass

        data = load_project_config(path)
        obj = cls(data, config_path=resolved)

        if resolved is not None:
            try:
                mtime = resolved.stat().st_mtime
                _config_cache[(str(resolved.resolve()), mtime)] = obj
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
            return str(indexes[0].get("name", "") or "").strip() or os.environ.get(
                "DIGISEARCH_INDEX", "default"
            )
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
            return str(indexes[0].get("name", "") or "").strip() or os.environ.get(
                "DIGISEARCH_INDEX", "default"
            )
        return os.environ.get("DIGISEARCH_INDEX", "default")

    def get_mcp_tools(self) -> list[str]:
        """Tool names to expose via MCP. When indexes were discovered from indexes_dir, digisearch_{name}_query is added per index."""
        explicit = self.mcp.get("tools", [])
        indexes = self.get_indexes()
        # Auto-add digisearch_*_query for each index only when we have indexes_dir (discovered); avoid duplicates
        digisearch_prefix = "digisearch_"
        digisearch_suffix = "_query"
        seen = {
            t for t in explicit if t.startswith(digisearch_prefix) and t.endswith(digisearch_suffix)
        }
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
        return self.services.get(
            "digisearch_url", os.environ.get("DIGISEARCH_URL", "http://digisearch:8002")
        )

    def get_digiquant_url(self) -> str:
        """DigiQuant service URL."""
        return self.services.get(
            "digiquant_url", os.environ.get("DIGIQUANT_URL", "http://digiquant:8001")
        )

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
