"""Paths under gitignored `data/agent-cache/` used only by migration/recovery and some fetch scripts.

Database-only workflows do not require this tree; see `data/README.md`. Canonical state is Supabase.
"""
from __future__ import annotations

from pathlib import Path

from lib.roots import AGENT_CACHE_ROOT


def daily_dir(date_str: str) -> Path:
    return AGENT_CACHE_ROOT / "daily" / date_str


def daily_data_dir(date_str: str) -> Path:
    return daily_dir(date_str) / "data"
