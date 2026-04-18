"""Shared helpers for analysis tools: artifacts dir, next filename."""

from __future__ import annotations

from pathlib import Path


def _artifacts_dir(dataset_path: str | Path) -> Path:
    p = Path(dataset_path).resolve().parent
    out = p / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _next_filename(out_dir: Path, prefix: str, ext: str = "png") -> Path:
    for i in range(1000):
        path = out_dir / f"{prefix}_{i}.{ext}"
        if not path.exists():
            return path
    return out_dir / f"{prefix}.{ext}"
