"""Authoritative-schema loader.

JSON Schemas under ``apps/digiquant-atlas/templates/`` are the system of
record for segment payload shapes. Pydantic models in later commits are
validated *against* these schemas — never re-authored from scratch.

This module:
- Loads a schema by logical name (``load_schema("sector-report")``).
- Validates a payload dict against a schema with one call.
- Provides ``list_schema_names()`` for the commit-9 drift check that pairs
  segments to schemas.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa: F401 — used for JSON-schema payload dict shape

import jsonschema


class SchemaNotFoundError(FileNotFoundError):
    """Raised when a schema name does not resolve to a file on disk."""


def _templates_root() -> Path:
    return Path(__file__).resolve().parents[3] / "atlas" / "templates"


def _schema_path(name: str) -> Path:
    """Resolve a logical name to one of two on-disk locations.

    Order of precedence:
    1. ``templates/schemas/<name>.schema.json`` — most schemas live here.
    2. ``templates/<name>-schema.json`` — top-level schemas (digest snapshot,
       delta request, snapshot). Kept flat for historical reasons; we tolerate
       both so callers don't have to remember which bucket a schema is in.
    """
    nested = _templates_root() / "schemas" / f"{name}.schema.json"
    if nested.is_file():
        return nested
    flat = _templates_root() / f"{name}-schema.json"
    if flat.is_file():
        return flat
    raise SchemaNotFoundError(f"schema not found: {name!r} (looked at {nested} and {flat})")


@lru_cache(maxsize=64)
def load_schema(name: str) -> dict[str, Any]:
    """Return the JSON Schema dict for ``name``. Cached per process."""
    return json.loads(_schema_path(name).read_text(encoding="utf-8"))


def validate_payload(name: str, payload: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` if ``payload`` does not match ``name``."""
    schema = load_schema(name)
    jsonschema.validate(instance=payload, schema=schema)


def list_schema_names() -> list[str]:
    """Return every schema name discoverable under ``templates/``. Sorted."""
    root = _templates_root()
    names: set[str] = set()
    nested = root / "schemas"
    if nested.is_dir():
        for p in nested.glob("*.schema.json"):
            names.add(p.name.removesuffix(".schema.json"))
    for p in root.glob("*-schema.json"):
        names.add(p.name.removesuffix("-schema.json"))
    return sorted(names)
