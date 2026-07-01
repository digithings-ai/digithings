"""Filesystem path containment for server-side ingest sources."""

from __future__ import annotations

import os
from pathlib import Path


def ingest_root() -> Path:
    """Allowed root for ``POST /ingest`` ``source`` paths (default: cwd)."""
    raw = os.environ.get("DIGISEARCH_INGEST_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def resolve_ingest_source(source: str) -> Path:
    """Resolve *source* under :func:`ingest_root`; reject traversal escapes."""
    root = ingest_root()
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Ingest source must be under DIGISEARCH_INGEST_ROOT ({root}); got {candidate}"
        ) from exc
    return candidate
