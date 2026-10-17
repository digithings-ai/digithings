"""Path containment helpers for CLI and API data inputs."""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    raw = os.environ.get("DIGIQUANT_DATA_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def resolve_under_data_root(path: Path, *, label: str = "path") -> Path:
    """Resolve *path* and ensure it stays under :func:`data_root`."""
    root = data_root()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be under DIGIQUANT_DATA_ROOT ({root}); got {resolved}"
        ) from exc
    return resolved


def validate_data_paths(
    *,
    data_path: str | Path | None,
    data_dir: str | Path | None,
) -> None:
    """Ensure optional data_path / data_dir resolve under :func:`data_root` (REM-055)."""
    if data_path is not None and str(data_path).strip():
        resolve_under_data_root(Path(data_path), label="data_path")
    if data_dir is not None and str(data_dir).strip():
        resolve_under_data_root(Path(data_dir), label="data_dir")


def canonicalize_path(path: str | Path) -> Path:
    """Canonicalize *path* (symlinks, ``.``/``..``) without confining it.

    Use for caller-chosen input/output files that legitimately live anywhere
    (tmp dirs, user-specified outputs, installed-layout coefficient files):
    the canonical form is what every later filesystem call acts on, so
    ``..``/symlink ambiguity cannot redirect the operation away from the
    named file. Where the file must additionally stay inside a trusted
    directory, resolve it against that root and require the real path to
    start with the root (the ``_resolve_tearsheet_output`` shape); that
    check is inline at the sink, never only in a helper.
    """
    real = os.path.realpath(os.path.normpath(os.fspath(path)))
    return Path(real)
