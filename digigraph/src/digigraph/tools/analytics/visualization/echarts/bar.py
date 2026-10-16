"""ECharts bar chart from dataset. Returns echarts_option with embedded data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def echarts_bar(
    dataset_path: str | Path,
    column: str,
    top_n: int = 20,
    title: str | None = None,
) -> dict[str, Any]:
    """Build ECharts bar option: categorical column value counts."""
    df = load_dataset(dataset_path)
    if column not in df.columns:
        return {"error": f"Column {column!r} not found", "echarts_option": None, "data_summary": {}}
    counts = df[column].value_counts().head(top_n)
    labels = [str(x) for x in counts[column].to_list()]
    values = counts["count"].to_list()
    if not labels:
        return {"error": "No data", "echarts_option": None, "data_summary": {}}
    option = {
        "title": {"text": title or f"Bar: {column}"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 45}},
        "yAxis": {"type": "value", "name": "count"},
        "series": [{"type": "bar", "data": values}],
    }
    summary = {"categories": len(labels), "column": column}
    return {"echarts_option": option, "data_summary": summary}
