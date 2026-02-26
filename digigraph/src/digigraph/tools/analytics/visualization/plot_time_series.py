"""Time series plot by date column."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename


def plot_time_series(
    dataset_path: str | Path,
    date_column: str,
    value_column: str | None = None,
    aggregation: str = "count",
) -> dict[str, Any]:
    """Plot time series: aggregate by date_column (count or value_column sum/mean). Returns image_path and summary."""
    df = load_dataset(dataset_path)
    if date_column not in df.columns:
        return {"error": f"Column {date_column!r} not found", "image_path": None, "summary": {}}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"error": "matplotlib not installed", "image_path": None, "summary": {}}
    col = df[date_column]
    if col.dtype == pl.Utf8 or col.dtype == pl.String:
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
    out_dir = _artifacts_dir(dataset_path)
    path = _next_filename(out_dir, "ts")
    fig, ax = plt.subplots()
    ax.plot(agg_df[date_col].to_list(), agg_df["value"].to_list(), marker="o", markersize=3)
    ax.set_title(f"Time series: {date_column}" + (f" ({aggregation} of {value_column})" if value_column else " (count)"))
    ax.set_ylabel("value")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    v = agg_df["value"]
    summary = {"points": len(agg_df), "min": v.min(), "max": v.max()}
    return {"image_path": str(path), "summary": summary}
