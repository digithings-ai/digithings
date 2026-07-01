"""Sankey diagram of flows from source to target column."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset
from digigraph.tools.analytics.visualization._helpers import _artifacts_dir, _next_filename


def plot_sankey(
    dataset_path: str | Path,
    source_column: str,
    target_column: str,
    value_column: str | None = None,
) -> dict[str, Any]:
    """Sankey diagram of flows from source_column to target_column. Optional value_column for flow size; otherwise counts rows. Returns image_path and summary."""
    df = load_dataset(dataset_path)
    for c in (source_column, target_column):
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "image_path": None, "summary": {}}
    if value_column and value_column not in df.columns:
        return {"error": f"Column {value_column!r} not found", "image_path": None, "summary": {}}

    if value_column and df[value_column].dtype in (pl.Int64, pl.Int32, pl.Float64, pl.Float32):
        agg_df = df.group_by([source_column, target_column]).agg(
            pl.col(value_column).sum().alias("value")
        )
    else:
        agg_df = df.group_by([source_column, target_column]).agg(pl.len().alias("value"))

    agg_df = agg_df.filter(pl.col("value") > 0)
    if agg_df.is_empty():
        return {"error": "No flows after aggregation", "image_path": None, "summary": {}}

    sources = agg_df[source_column].cast(pl.Utf8).to_list()
    targets = agg_df[target_column].cast(pl.Utf8).to_list()
    values = agg_df["value"].to_list()

    seen: set[str] = set()
    labels: list[str] = []
    for s in sources:
        ss = str(s).strip() or "(empty)"
        if ss not in seen:
            seen.add(ss)
            labels.append(ss[:60])
    for t in targets:
        tt = str(t).strip() or "(empty)"
        if tt not in seen:
            seen.add(tt)
            labels.append(tt[:60])
    label_to_idx = {lb: i for i, lb in enumerate(labels)}
    source_idx = [label_to_idx[(str(s).strip() or "(empty)")[:60]] for s in sources]
    target_idx = [label_to_idx[(str(t).strip() or "(empty)")[:60]] for t in targets]

    try:
        import plotly.graph_objects as go
    except ImportError:
        return {
            "error": "plotly not installed",
            "image_path": None,
            "summary": {"nodes": len(labels), "flows": len(values)},
        }

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="gray", width=0.5),
                    label=labels,
                ),
                link=dict(source=source_idx, target=target_idx, value=values),
            )
        ]
    )
    fig.update_layout(
        title_text=f"Sankey: {source_column} → {target_column}", font_size=10, height=500
    )

    out_dir = _artifacts_dir(dataset_path)
    path = _next_filename(out_dir, "sankey", "png")
    try:
        fig.write_image(path, scale=1.5)
    except (OSError, ValueError, RuntimeError) as e:
        return {
            "error": f"Failed to save image: {e}",
            "image_path": None,
            "summary": {"nodes": len(labels), "flows": len(values)},
        }

    summary = {"nodes": len(labels), "flows": len(values), "total_value": sum(values)}
    return {"image_path": str(path), "summary": summary}
