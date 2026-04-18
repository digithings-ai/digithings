"""Column math and unary transforms. Writes result to Digistore; returns dataset_ref."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset


def transform_columns(
    dataset_path: str | Path,
    session_id: str | None,
    output_name: str,
    column_ops: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Add columns from expressions. column_ops: [{"new_col": "a + b"}, {"out": "col * 2"}, {"x_log": "log(x)"}].
    Supports: col_a + col_b, col - col2, col * 2, col / 3, log(col), exp(col), sqrt(col).
    """
    df = load_dataset(dataset_path)
    for op in column_ops or []:
        for new_col, expr in op.items():
            if not expr or not isinstance(expr, str):
                continue
            expr = expr.strip()
            try:
                # Unary: log(col), exp(col), sqrt(col)
                m = re.match(r"(log|exp|sqrt)\s*\(\s*(\w+)\s*\)", expr, re.IGNORECASE)
                if m and m.group(2) in df.columns:
                    fn, col = m.group(1).lower(), m.group(2)
                    if fn == "log":
                        df = df.with_columns(pl.col(col).log().alias(new_col))
                    elif fn == "exp":
                        df = df.with_columns(pl.col(col).exp().alias(new_col))
                    elif fn == "sqrt":
                        df = df.with_columns(pl.col(col).sqrt().alias(new_col))
                    continue
                # Binary: col_a + col_b, col_a - col_b, col_a * 2, col_a / 2
                for sep in (" + ", " - ", " * ", " / "):
                    if sep not in expr:
                        continue
                    left, _, right = expr.partition(sep)
                    left, right = left.strip(), right.strip()
                    try:
                        const = float(right)
                        if left in df.columns:
                            if sep == " + ":
                                df = df.with_columns((pl.col(left) + const).alias(new_col))
                            elif sep == " - ":
                                df = df.with_columns((pl.col(left) - const).alias(new_col))
                            elif sep == " * ":
                                df = df.with_columns((pl.col(left) * const).alias(new_col))
                            elif sep == " / ":
                                df = df.with_columns((pl.col(left) / const).alias(new_col))
                            break
                    except ValueError:
                        if left in df.columns and right in df.columns:
                            if sep == " + ":
                                df = df.with_columns((pl.col(left) + pl.col(right)).alias(new_col))
                            elif sep == " - ":
                                df = df.with_columns((pl.col(left) - pl.col(right)).alias(new_col))
                            elif sep == " * ":
                                df = df.with_columns((pl.col(left) * pl.col(right)).alias(new_col))
                            elif sep == " / ":
                                df = df.with_columns((pl.col(left) / pl.col(right)).alias(new_col))
                            break
            except Exception as e:
                return {"error": str(e), "dataset_ref": None, "rows": 0, "columns": []}
    return write_result(df, session_id, output_name)
