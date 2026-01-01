"""Export dataset to JSON, CSV, or Parquet. Returns path, format, rows, and optional download_url."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from digigraph.tools.analytics.load import load_dataset


def export_dataset(
    dataset_path: str | Path,
    format: str = "json",
    columns: list[str] | None = None,
    files_base_url: str | None = None,
) -> dict[str, Any]:
    """Export dataset to CSV, Parquet, or JSON in the same session dir. Returns path, format, rows, and optional download_url."""
    df = load_dataset(dataset_path)
    if columns:
        cols = [c for c in columns if c in df.columns]
        if cols:
            df = df.select(cols)
    base = Path(dataset_path).resolve().parent
    fmt = (format or "json").strip().lower()
    if fmt == "csv":
        path = base / "export.csv"
        df.write_csv(path)
    elif fmt == "parquet":
        path = base / "export.parquet"
        df.write_parquet(path)
    else:
        path = base / "export.json"
        path.write_text(json.dumps(df.to_dicts(), default=str), encoding="utf-8")

    out: dict[str, Any] = {"path": str(path), "format": fmt, "rows": len(df)}
    if files_base_url and files_base_url.strip():
        from digigraph.run_storage import path_relative_to_run_data_dir

        rel = path_relative_to_run_data_dir(path)
        if rel:
            base_url = files_base_url.strip().rstrip("/")
            out["download_url"] = f"{base_url}/files/{rel}"
    return out
