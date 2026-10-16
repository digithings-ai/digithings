"""Summary statistics: mean, median, std, min, max, nulls per column."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset


def summary_stats(
    dataset_path: str | Path,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Per-column summary: mean, median, std, min, max, null_count. Columns optional (default all)."""
    df = load_dataset(dataset_path)
    cols = list(columns) if columns else df.columns
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return {"error": "No valid columns", "stats": {}}
    stats = {}
    for c in cols:
        s = df[c]
        d = {"null_count": s.null_count()}
        n = s.drop_nulls()
        if len(n) > 0:
            d["count"] = len(n)
            if n.dtype in (pl.Int64, pl.Float64, pl.UInt32, pl.Float32):
                d["min"] = n.min()
                d["max"] = n.max()
                d["mean"] = n.mean()
                d["median"] = n.median()
                if len(n) > 1:
                    d["std"] = n.std()
        stats[c] = d
    return {"stats": stats}
