"""Filesystem path containment for server-side ingest sources."""

from __future__ import annotations

import os
from pathlib import Path


def ingest_root() -> Path:
    """Allowed root for ``POST /ingest`` ``source`` paths (default: cwd)."""
    raw = os.environ.get("DIGISEARCH_INGEST_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def assert_within_ingest_root(path: Path) -> Path:
    """Resolve *path* and reject anything outside :func:`ingest_root`.

    ``Path.resolve`` follows symlinks, so a link that sits inside the jail but
    points outside is rejected. Callers that read a second path (a sidecar)
    must use this too: ``is_file`` and ``read_text`` follow that link.
    """
    root = ingest_root()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Ingest path must be under DIGISEARCH_INGEST_ROOT ({root}); got {resolved}"
        ) from exc
    return resolved


def resolve_ingest_source(source: str) -> Path:
    """Resolve *source* under :func:`ingest_root`; reject traversal escapes."""
    root = ingest_root()
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return assert_within_ingest_root(candidate)
