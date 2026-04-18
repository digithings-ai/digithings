"""ECharts option from template/code with column refs. Injects dataset into option."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def echarts_from_code(
    dataset_path: str | Path,
    option_spec: str | dict[str, Any],
    column_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build ECharts option from a spec (JSON string or dict). column_refs maps placeholder keys to dataset column names;
    data is injected into option.dataset.source or series[].data as needed.
    If option_spec is a string, parse as JSON. Then replace placeholders like {{column:x}} with column x from dataset.
    """
    df = load_dataset(dataset_path)
    if isinstance(option_spec, str):
        try:
            option = json.loads(option_spec.strip())
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}", "echarts_option": None, "data_summary": {}}
    else:
        option = dict(option_spec)
    column_refs = column_refs or {}
    # If option has "dataset": {"source": []}, fill with df columns
    if "dataset" in option and isinstance(option["dataset"], dict):
        cols = column_refs.get("columns", "")
        if isinstance(cols, str):
            cols = [c.strip() for c in cols.split(",") if c.strip()] or list(df.columns)
        else:
            cols = list(column_refs.values()) if column_refs else list(df.columns)
        header = [c for c in cols if c in df.columns]
        if header:
            option["dataset"]["source"] = [header] + [[df[c].to_list()[i] for c in header] for i in range(len(df))]
    # If option has series[].dataRef pointing to a column name, inject that column
    for series in option.get("series", []):
        if isinstance(series, dict) and "dataRef" in series:
            col = series.pop("dataRef", None)
            if col and col in df.columns:
                series["data"] = df[col].to_list()
    summary = {"rows": len(df), "columns": df.columns}
    return {"echarts_option": option, "data_summary": summary}
