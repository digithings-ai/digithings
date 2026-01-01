"""Round numeric column to N decimals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset


def round_column(
    dataset_path: str | Path,
    session_id: str | None,
    output_name: str,
    column: str,
    decimals: int = 2,
) -> dict[str, Any]:
    """Round numeric column to N decimal places. Writes to Digistore."""
    df = load_dataset(dataset_path)
    if column not in df.columns:
        return {"error": f"Column {column!r} not found", "dataset_ref": None, "rows": 0}
    df = df.with_columns(pl.col(column).round(decimals).alias(column))
    return write_result(df, session_id, output_name)
