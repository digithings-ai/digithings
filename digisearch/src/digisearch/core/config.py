"""DigiSearch configuration. YAML/TOML loader with env var substitution."""

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


def load_config(path: str | Path) -> dict[str, Any]:
    """Load YAML or TOML config, substitute ${VAR} with env."""
    path = Path(path)
    if not path.exists():
        return {}
    raw = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(raw) or {}
    elif path.suffix == ".toml":
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        data = tomllib.loads(raw)
    else:
        return {}
    return _subst_env(data)


class DigiSearchConfig:
    """DigiSearch configuration. Built from YAML/TOML or defaults."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self._data = data
        self.embedding = data.get("embedding", {})
        self.indexes = data.get("indexes", [])
        self.search = data.get("search", {})
        self.mcp = data.get("mcp", {})

    @classmethod
    def from_config(cls, path: str | Path) -> "DigiSearchConfig":
        """Load from YAML/TOML file."""
        return cls(load_config(path))

    @classmethod
    def from_env(cls) -> "DigiSearchConfig":
        """Load from DIGISEARCH_CONFIG_PATH or return defaults."""
        path = os.environ.get("DIGISEARCH_CONFIG_PATH")
        if path:
            return cls.from_config(path)
        return cls()

    def get_embedding_provider(self) -> str:
        """Default embedding provider name."""
        return self.embedding.get("provider", "openai")

    def get_embedding_model(self) -> str:
        """Default embedding model."""
        return self.embedding.get("model", "text-embedding-3-small")

    def get_index_config(self, name: str) -> dict[str, Any] | None:
        """Get config for named index."""
        for idx in self.indexes:
            if isinstance(idx, dict) and idx.get("name") == name:
                return idx
        return None

    def get_mcp_expose(self) -> list[str]:
        """Index names to expose via MCP."""
        return self.mcp.get("expose", [])

    def get_mcp_port(self) -> int:
        """MCP server port."""
        return int(self.mcp.get("port", 8765))


def load_index_config(path: str | Path) -> dict[str, Any]:
    """Load index YAML (index_name, field_mapping, schema)."""
    p = Path(path)
    if not p.exists():
        return {}
    raw = p.read_text()
    data = yaml.safe_load(raw) or {}
    return _subst_env(data)


def get_index_config_path() -> Path | None:
    """Path from DIGISEARCH_INDEX_CONFIG env. Resolved relative to cwd."""
    p = os.environ.get("DIGISEARCH_INDEX_CONFIG")
    if not p:
        return None
    path = Path(p)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path if path.exists() else None
