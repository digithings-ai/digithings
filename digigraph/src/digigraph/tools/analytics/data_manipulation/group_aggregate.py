"""Group by columns and aggregate. Writes result to Digistore."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset


def group_and_aggregate(
    dataset_path: str | Path,
    session_id: str | None,
    output_name: str,
    group_by_columns: list[str],
    agg_columns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Group by group_by_columns and apply aggregations. agg_columns: [{"col": "score", "agg": "mean"}, ...].
    agg: sum, mean, count, min, max.
    """
    df = load_dataset(dataset_path)
    for c in group_by_columns:
        if c not in df.columns:
            return {"error": f"Group column {c!r} not found", "dataset_ref": None, "rows": 0}
    agg_exprs: list[pl.Expr] = []
    for a in agg_columns or []:
        col_name = a.get("col") or a.get("column")
        agg_type = (a.get("agg") or a.get("aggfunc") or "count").strip().lower()
        if not col_name or col_name not in df.columns:
            continue
        if agg_type == "sum":
            agg_exprs.append(pl.col(col_name).sum().alias(f"{col_name}_sum"))
        elif agg_type == "mean":
            agg_exprs.append(pl.col(col_name).mean().alias(f"{col_name}_mean"))
        elif agg_type == "count":
            agg_exprs.append(pl.col(col_name).count().alias(f"{col_name}_count"))
        elif agg_type == "min":
            agg_exprs.append(pl.col(col_name).min().alias(f"{col_name}_min"))
        elif agg_type == "max":
            agg_exprs.append(pl.col(col_name).max().alias(f"{col_name}_max"))
    if not agg_exprs:
        agg_exprs = [pl.len().alias("count")]
    df = df.group_by(group_by_columns).agg(agg_exprs)
    return write_result(df, session_id, output_name)
