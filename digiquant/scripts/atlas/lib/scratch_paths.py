"""Paths under gitignored `data/agent-cache/` used only by migration/recovery and some fetch scripts.

Database-only workflows do not require this tree; see `data/README.md`. Canonical state is Supabase.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
AGENT_CACHE_ROOT = _ROOT / "data" / "agent-cache"


def daily_dir(date_str: str) -> Path:
    return AGENT_CACHE_ROOT / "daily" / date_str


def daily_data_dir(date_str: str) -> Path:
    return daily_dir(date_str) / "data"
