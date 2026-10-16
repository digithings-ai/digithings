"""Group by columns and aggregate. Returns aggregated table as list of dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset


def group_by_summary(
    dataset_path: str | Path,
    group_by_columns: list[str],
    agg_columns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Group by columns and aggregate. agg_columns e.g. [{"col": "score", "agg": "mean"}, {"col": "doc_id", "agg": "count"}].
    Returns aggregated table as list of dicts.
    """
    df = load_dataset(dataset_path)
    for c in group_by_columns:
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "table": []}
    if not agg_columns:
        agg_df = df.group_by(group_by_columns).agg(pl.len().alias("count"))
    else:
        exprs = []
        for a in agg_columns:
            col = a.get("col") or a.get("column")
            agg = (a.get("agg") or "count").strip().lower()
            if not col or col not in df.columns:
                continue
            if agg == "count":
                exprs.append(pl.col(col).count().alias(f"{col}_count"))
            elif agg == "mean":
                exprs.append(pl.col(col).mean().alias(f"{col}_mean"))
            elif agg == "sum":
                exprs.append(pl.col(col).sum().alias(f"{col}_sum"))
            elif agg == "min":
                exprs.append(pl.col(col).min().alias(f"{col}_min"))
            elif agg == "max":
                exprs.append(pl.col(col).max().alias(f"{col}_max"))
        if not exprs:
            exprs = [pl.len().alias("count")]
        agg_df = df.group_by(group_by_columns).agg(exprs)
    return {"table": agg_df.to_dicts(), "columns": agg_df.columns}
