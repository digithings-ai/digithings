"""Packaged JSON Schemas for digigraph (e.g. DigiProject v1alpha1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).parent


def load_schema(name: str) -> dict[str, Any]:
    """Load a packaged JSON Schema by filename (e.g. 'digiproject.v1alpha1.json')."""
    path = _SCHEMA_DIR / name
    return json.loads(path.read_text())


def schema_path(name: str) -> Path:
    """Return the on-disk path of a packaged schema file."""
    return _SCHEMA_DIR / name


DIGIPROJECT_V1ALPHA1 = "digiproject.v1alpha1.json"
