"""ECharts scatter chart from dataset. Returns echarts_option with embedded data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def echarts_scatter(
    dataset_path: str | Path,
    x_column: str,
    y_column: str,
    color_by: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Build ECharts scatter option. Optional color_by for series grouping."""
    df = load_dataset(dataset_path)
    for c in [x_column, y_column]:
        if c not in df.columns:
            return {"error": f"Column {c!r} not found", "echarts_option": None, "data_summary": {}}
    df = df.drop_nulls([x_column, y_column])
    if len(df) == 0:
        return {"error": "No non-null rows", "echarts_option": None, "data_summary": {}}
    if color_by and color_by not in df.columns:
        color_by = None
    if color_by:
        series_list = []
        for name, g in df.group_by(color_by):
            name_val = name[0] if isinstance(name, tuple) else name
            x_vals = g[x_column].to_list()
            y_vals = g[y_column].to_list()
            try:
                data = [[float(x_vals[i]), float(y_vals[i])] for i in range(len(g))]
            except (TypeError, ValueError):
                data = [[x_vals[i], y_vals[i]] for i in range(len(g))]
            series_list.append({
                "name": str(name_val),
                "type": "scatter",
                "data": data,
            })
        option = {
            "title": {"text": title or f"Scatter: {x_column} vs {y_column}"},
            "tooltip": {"trigger": "item"},
            "legend": {"data": [s["name"] for s in series_list]},
            "xAxis": {"type": "value", "name": x_column},
            "yAxis": {"type": "value", "name": y_column},
            "series": series_list,
        }
    else:
        x_vals = df[x_column].to_list()
        y_vals = df[y_column].to_list()
        try:
            data = [[float(x_vals[i]), float(y_vals[i])] for i in range(len(df))]
        except (TypeError, ValueError):
            data = [[x_vals[i], y_vals[i]] for i in range(len(df))]
        option = {
            "title": {"text": title or f"Scatter: {x_column} vs {y_column}"},
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "value", "name": x_column},
            "yAxis": {"type": "value", "name": y_column},
            "series": [{"type": "scatter", "data": data, "symbolSize": 8}],
        }
    summary = {"n": len(df), "x_column": x_column, "y_column": y_column}
    return {"echarts_option": option, "data_summary": summary}
