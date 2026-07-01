"""Hermes-side JSON-Schema loader.

Mirrors :mod:`digiquant.olympus.atlas.schemas` but resolves paths under
``digiquant/src/digiquant/olympus/hermes/templates/``. Each engine's ``load_schema()`` only finds
its own templates. See [ADR-0015](../../../../docs/adr/0015-atlas-vs-hermes.md).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa: F401 — used for JSON-schema payload dict shape

import jsonschema

# Re-export the shared exception so callers can catch a single class
# regardless of which engine raised.
from digiquant.olympus.atlas.schemas import SchemaNotFoundError

__all__ = [
    "SchemaNotFoundError",
    "list_schema_names",
    "load_schema",
    "validate_payload",
]


def _templates_root() -> Path:
    """Return ``digiquant/src/digiquant/olympus/hermes/templates/``.

    Templates ship with the Hermes package — see #486.
    """
    return Path(__file__).resolve().parent / "templates"


def _schema_path(name: str) -> Path:
    """Resolve a logical name to a Hermes-side template path.

    Order of precedence:
    1. ``templates/schemas/<name>.schema.json`` — most schemas live here.
    2. ``templates/<name>-schema.json`` — top-level schemas (kept flat for
       historical reasons; tolerated for symmetry with Atlas's loader).
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
    """Return every schema name discoverable under ``hermes/templates/``. Sorted."""
    root = _templates_root()
    names: set[str] = set()
    nested = root / "schemas"
    if nested.is_dir():
        for p in nested.glob("*.schema.json"):
            names.add(p.name.removesuffix(".schema.json"))
    for p in root.glob("*-schema.json"):
        names.add(p.name.removesuffix("-schema.json"))
    return sorted(names)
