"""Append (concatenate) two datasets. Writes result to Digistore."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset


def append_datasets(
    dataset_path_first: str | Path,
    dataset_path_second: str | Path,
    session_id: str | None,
    output_name: str,
) -> dict[str, Any]:
    """Vertical concat of two datasets. Columns aligned by name; missing filled with null."""
    df1 = load_dataset(dataset_path_first)
    df2 = load_dataset(dataset_path_second)
    try:
        df = pl.concat([df1, df2], how="diagonal")
    except Exception as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
    return write_result(df, session_id, output_name)
