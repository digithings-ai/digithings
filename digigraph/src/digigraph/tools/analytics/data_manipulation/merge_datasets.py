"""Merge/join two datasets. Writes result to Digistore."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset


def merge_datasets(
    dataset_path_left: str | Path,
    dataset_path_right: str | Path,
    session_id: str | None,
    output_name: str,
    left_on: str | list[str],
    right_on: str | list[str] | None = None,
    how: str = "inner",
) -> dict[str, Any]:
    """Join two datasets on key column(s). how: inner, left, outer, cross."""
    df_left = load_dataset(dataset_path_left)
    df_right = load_dataset(dataset_path_right)
    right_on = right_on or left_on
    if isinstance(left_on, str):
        left_on = [left_on]
    if isinstance(right_on, str):
        right_on = [right_on]
    for c in left_on:
        if c not in df_left.columns:
            return {"error": f"Left key {c!r} not found", "dataset_ref": None, "rows": 0}
    for c in right_on:
        if c not in df_right.columns:
            return {"error": f"Right key {c!r} not found", "dataset_ref": None, "rows": 0}
    how = (how or "inner").strip().lower()
    if how not in ("inner", "left", "outer", "cross"):
        how = "inner"
    try:
        df = df_left.join(df_right, left_on=left_on, right_on=right_on, how=how)
    except Exception as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
    return write_result(df, session_id, output_name)
