"""Shared utility helpers for DigiThings services."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create the parent directory of *path* if it does not exist. Return the parent Path."""
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent


__all__ = ["ensure_dir"]
