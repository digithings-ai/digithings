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
