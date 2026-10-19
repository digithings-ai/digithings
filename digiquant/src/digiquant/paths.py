"""Path containment helpers for CLI and API data inputs."""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    raw = os.environ.get("DIGIQUANT_DATA_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def resolve_under_data_root(path: str | Path, *, label: str = "path") -> Path:
    """Resolve *path* and ensure it stays under :func:`data_root`."""
    root = data_root()
    resolved = Path(os.fspath(path)).expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be under DIGIQUANT_DATA_ROOT ({root}); got {resolved}"
        ) from exc
    return resolved


def resolve_under(root: str | Path, path: str | Path, *, label: str = "path") -> Path:
    """The shared safe-path helper: resolve *path*, refuse anything outside *root*.

    Resolve symlinks/``.``/``..`` on both sides and return the real position
    when it is inside ``root``; raise ``ValueError`` otherwise. The returned
    value is the resolved real path — every later filesystem call must use
    it, never the original argument, so ``..``/symlink ambiguity cannot
    redirect the operation. This is the CodeQL-counted check for
    py/path-injection sinks: the containment lives at the sink, not only at
    the request boundary (see REM-055 / DIG-4057 batch A).
    """
    base = Path(os.fspath(root)).expanduser().resolve()
    resolved = Path(os.fspath(path)).expanduser().resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"{label} must resolve under {base}; got {resolved}"
        ) from exc
    return resolved


def validate_data_paths(
    *,
    data_path: str | Path | None,
    data_dir: str | Path | None,
) -> None:
    """Ensure optional data_path / data_dir resolve under :func:`data_root` (REM-055)."""
    if data_path is not None and str(data_path).strip():
        resolve_under_data_root(data_path, label="data_path")
    if data_dir is not None and str(data_dir).strip():
        resolve_under_data_root(data_dir, label="data_dir")


def canonicalize_path(path: str | Path) -> Path:
    """Canonicalize *path* (symlinks, ``.``/``..``) without confining it.

    .. deprecated:: DIG-4057 batch B
       For any path that crosses a caller/request boundary use
       :func:`resolve_under_data_root` (data inputs) or the explicit-base
       :func:`resolve_under` (named-output sinks) instead — ``py/path-injection``
       counts the containment at the sink, and pure canonicalization keeps the
       taint alive (DIG-4057 batch B evidence). Retained for the remaining
       installed-layout constant paths only.
    """
    real = os.path.realpath(os.path.normpath(os.fspath(path)))
    return Path(real)
