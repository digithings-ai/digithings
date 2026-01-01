"""Load stored search results (JSON) into a Polars DataFrame. Shared by all analytics tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl


def load_dataset(dataset_path: str | Path) -> pl.DataFrame:
    """
    Load a run-storage JSON file (array of result dicts) into a Polars DataFrame.
    Each row has content, score, doc_id, rank, and flattened metadata columns.
    """
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    raw = path.read_text(encoding="utf-8")
    results = json.loads(raw)
    if not isinstance(results, list):
        raise ValueError("Dataset JSON must be an array of result objects")
    if not results:
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    for r in results:
        row = {
            "content": r.get("content", ""),
            "score": r.get("score"),
            "doc_id": r.get("doc_id"),
            "rank": r.get("rank"),
        }
        meta = r.get("metadata") or {}
        for k, v in meta.items():
            if k not in row:
                row[k] = v
        rows.append(row)
    return pl.from_dicts(rows, infer_schema_length=10_000)
