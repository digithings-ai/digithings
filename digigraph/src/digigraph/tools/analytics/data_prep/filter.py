"""Filter rows by structured filters. Writes filtered result to new JSON; returns path as new dataset_ref."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from digigraph.tools.analytics.load import load_dataset


def filter_dataset(
    dataset_path: str | Path,
    filters: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Filter rows by structured filters [{field, op, value}]. Writes filtered result to new JSON; returns path as new dataset_ref.
    """
    df = load_dataset(dataset_path)
    for f in filters:
        field = f.get("field")
        op = (f.get("op") or "eq").strip().lower()
        val = f.get("value")
        if field not in df.columns:
            continue
        if op == "eq":
            df = df.filter(pl.col(field) == val)
        elif op == "ne":
            df = df.filter(pl.col(field) != val)
        elif op == "gt":
            df = df.filter(pl.col(field) > val)
        elif op == "ge":
            df = df.filter(pl.col(field) >= val)
        elif op == "lt":
            df = df.filter(pl.col(field) < val)
        elif op == "le":
            df = df.filter(pl.col(field) <= val)
    if columns:
        cols = [c for c in columns if c in df.columns]
        if cols:
            df = df.select(cols)
    base = Path(dataset_path).resolve().parent
    path = base / "filtered.json"
    path.write_text(json.dumps(df.to_dicts(), default=str), encoding="utf-8")
    return {"dataset_ref": str(path), "rows": len(df)}
