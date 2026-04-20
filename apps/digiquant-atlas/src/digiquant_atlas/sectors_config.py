"""Loader for ``config/sectors.yaml``.

Consumed by ``phases.phase5_equities`` to build the 11-way sector fan-out.
One function, one dataclass — kept narrow on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa: F401 — used for YAML-derived dict shape

import yaml


@dataclass(frozen=True)
class SectorConfig:
    """One sector's configuration, consumed as ``phase_inputs.sector_config``."""

    slug: str
    name: str
    etfs: list[str]
    subsegments: list[dict[str, Any]]
    top_tickers: list[str]
    key_drivers: list[str]
    nuance_notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SectorConfig":
        return cls(
            slug=str(raw["slug"]),
            name=str(raw["name"]),
            etfs=list(raw.get("etfs") or []),
            subsegments=list(raw.get("subsegments") or []),
            top_tickers=list(raw.get("top_tickers") or []),
            key_drivers=list(raw.get("key_drivers") or []),
            nuance_notes=str(raw.get("nuance_notes") or "").strip(),
        )


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "sectors.yaml"


@lru_cache(maxsize=1)
def load_sectors() -> list[SectorConfig]:
    """Return every sector declared in ``config/sectors.yaml``, preserving order.

    Cached — the YAML is static per process. Tests that want a fresh read
    should call ``load_sectors.cache_clear()``.
    """
    data = yaml.safe_load(_config_path().read_text(encoding="utf-8")) or {}
    raw_sectors = data.get("sectors") or []
    if not isinstance(raw_sectors, list) or not raw_sectors:
        raise ValueError(f"{_config_path()} must declare a non-empty 'sectors' list")
    return [SectorConfig.from_dict(r) for r in raw_sectors]


__all__ = ["SectorConfig", "load_sectors"]
