"""ECharts line chart from dataset. Returns echarts_option with embedded data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset


def echarts_line(
    dataset_path: str | Path,
    date_column: str,
    value_column: str | None = None,
    aggregation: str = "count",
    title: str | None = None,
) -> dict[str, Any]:
    """Build ECharts line option. date_column for x-axis; value_column optional (else count)."""
    df = load_dataset(dataset_path)
    if date_column not in df.columns:
        return {"error": f"Column {date_column!r} not found", "echarts_option": None, "data_summary": {}}
    col = df[date_column]
    if col.dtype in (pl.Utf8, pl.String):
        df = df.with_columns(pl.col(date_column).str.to_datetime(strict=False).alias("_ts"))
        date_col = "_ts"
    else:
        date_col = date_column
    if value_column and value_column in df.columns:
        if aggregation == "sum":
            agg_df = df.group_by(date_col).agg(pl.col(value_column).sum().alias("value"))
        elif aggregation == "mean":
            agg_df = df.group_by(date_col).agg(pl.col(value_column).mean().alias("value"))
        else:
            agg_df = df.group_by(date_col).agg(pl.len().alias("value"))
    else:
        agg_df = df.group_by(date_col).agg(pl.len().alias("value"))
    agg_df = agg_df.sort(date_col)
    x_data = [str(x) for x in agg_df[date_col].to_list()]
    y_series = agg_df["value"]
    y_data = [float(x) if x is not None else 0.0 for x in y_series.to_list()]
    option = {
        "title": {"text": title or f"Time series: {date_column}"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": x_data, "name": date_column},
        "yAxis": {"type": "value", "name": "value"},
        "series": [{"type": "line", "data": y_data, "smooth": True}],
    }
    summary = {"points": len(x_data), "x_column": date_column, "value_column": value_column or "count"}
    return {"echarts_option": option, "data_summary": summary}
