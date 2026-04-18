"""Pivot table: index, columns, values, aggfunc (sum | mean | count). Returns table as list of dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


from digigraph.tools.analytics.load import load_dataset


def pivot_table(
    dataset_path: str | Path,
    index: str,
    columns: str,
    values: str,
    aggfunc: str = "sum",
) -> dict[str, Any]:
    """Pivot table: index, columns, values, aggfunc (sum | mean | count). Returns table as list of dicts."""
    df = load_dataset(dataset_path)
    for c in (index, columns, values):
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "table": []}
    agg = aggfunc.strip().lower()
    if agg == "mean":
        pivot_df = df.pivot(values=values, index=index, columns=columns, aggregate_function="mean")
    elif agg == "count":
        pivot_df = df.pivot(values=values, index=index, columns=columns, aggregate_function="len")
    else:
        pivot_df = df.pivot(values=values, index=index, columns=columns, aggregate_function="sum")
    return {"table": pivot_df.to_dicts(), "columns": pivot_df.columns}
