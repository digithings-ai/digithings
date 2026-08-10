"""ECharts pie chart from dataset. Returns echarts_option with embedded data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def echarts_pie(
    dataset_path: str | Path,
    column: str,
    top_n: int = 15,
    title: str | None = None,
) -> dict[str, Any]:
    """Build ECharts pie option: categorical column value counts."""
    df = load_dataset(dataset_path)
    if column not in df.columns:
        return {"error": f"Column {column!r} not found", "echarts_option": None, "data_summary": {}}
    counts = df[column].value_counts().head(top_n)
    data = [
        {"name": str(counts[column].to_list()[i]), "value": counts["count"].to_list()[i]}
        for i in range(len(counts))
    ]
    if not data:
        return {"error": "No data", "echarts_option": None, "data_summary": {}}
    option = {
        "title": {"text": title or f"Pie: {column}"},
        "tooltip": {"trigger": "item"},
        "series": [{"type": "pie", "radius": "60%", "data": data}],
    }
    summary = {"categories": len(data), "column": column}
    return {"echarts_option": option, "data_summary": summary}
