"""Filesystem path containment for server-side ingest sources."""

from __future__ import annotations

import os
import stat
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


def assert_hardlink_within_ingest_root(path: Path) -> None:
    """Reject a regular file that also has a directory entry outside the jail.

    ``Path.resolve`` follows symlinks and does not notice a hard link, so an
    in-jail name can still be the same inode as a file outside the root.
    ``st_nlink == 1`` has no other name. A higher count is allowed only when
    every name found under the jail accounts for it.
    """
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink <= 1:
        return
    root = ingest_root()
    found = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            candidate = Path(dirpath) / name
            try:
                other = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(other.st_mode):
                continue
            if other.st_dev == info.st_dev and other.st_ino == info.st_ino:
                found += 1
    if found < info.st_nlink:
        raise ValueError(
            f"Ingest path must be under DIGISEARCH_INGEST_ROOT ({root}); got hard link {path}"
        )


def resolve_ingest_source(source: str) -> Path:
    """Resolve *source* under :func:`ingest_root`; reject traversal escapes."""
    root = ingest_root()
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = assert_within_ingest_root(candidate)
    if resolved.is_file():
        assert_hardlink_within_ingest_root(resolved)
    return resolved
