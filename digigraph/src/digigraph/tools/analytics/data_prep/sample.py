"""Sample n rows or frac fraction. Writes to new JSON; returns path as new dataset_ref."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def sample_dataset(
    dataset_path: str | Path,
    n: int | None = None,
    frac: float | None = None,
    random_state: int | None = None,
) -> dict[str, Any]:
    """Sample n rows or frac fraction. Writes to new JSON; returns path as new dataset_ref."""
    df = load_dataset(dataset_path)
    if n is not None and n > 0:
        sampled = df.sample(n=min(n, len(df)), seed=random_state)
    elif frac is not None and 0 < frac <= 1:
        k = max(1, int(len(df) * frac))
        sampled = df.sample(n=k, seed=random_state)
    else:
        return {"error": "Specify n or frac", "dataset_ref": None}
    base = Path(dataset_path).resolve().parent
    path = base / "sampled.json"
    path.write_text(json.dumps(sampled.to_dicts(), default=str), encoding="utf-8")
    return {"dataset_ref": str(path), "rows": len(sampled)}
