"""Shared helpers for visualization tools: artifacts dir, next filename, sanitize node id."""

from __future__ import annotations

import re
from pathlib import Path


def _artifacts_dir(dataset_path: str | Path) -> Path:
    """Artifacts dir next to the dataset (session dir / artifacts)."""
    p = Path(dataset_path).resolve().parent
    out = p / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _next_filename(out_dir: Path, prefix: str, ext: str = "png") -> Path:
    """Unique path for a new image (prefix_0.png, prefix_1.png, ...)."""
    for i in range(1000):
        path = out_dir / f"{prefix}_{i}.{ext}"
        if not path.exists():
            return path
    return out_dir / f"{prefix}.{ext}"


def _sanitize_node_id(label: str) -> str:
    """Mermaid-safe node id: alphanumeric and underscore only."""
    s = str(label).strip()[:50]
    return re.sub(r"[^a-zA-Z0-9_]", "_", s) or "n"
