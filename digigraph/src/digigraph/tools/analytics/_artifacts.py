"""Artifact helpers shared by the analysis and visualization tool families."""

from __future__ import annotations

import re
from pathlib import Path


def artifacts_dir(dataset_path: str | Path) -> Path:
    """Return the dataset's sibling ``artifacts/`` directory, creating it on demand."""
    p = Path(dataset_path).resolve().parent
    out = p / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def next_filename(out_dir: Path, prefix: str, ext: str = "png") -> Path:
    """First unused ``<prefix>_<n>.<ext>``; falls back to ``<prefix>.<ext>`` past 1000."""
    for i in range(1000):
        path = out_dir / f"{prefix}_{i}.{ext}"
        if not path.exists():
            return path
    return out_dir / f"{prefix}.{ext}"


def sanitize_node_id(label: str) -> str:
    """Diagram-safe node id: 50 chars max, non-word characters replaced."""
    s = str(label).strip()[:50]
    return re.sub(r"[^a-zA-Z0-9_]", "_", s) or "n"
