"""Shared: write DataFrame to Digistore or session dir."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import polars as pl

log = logging.getLogger(__name__)


def write_result(df: pl.DataFrame, session_id: str | None, output_name: str) -> dict[str, Any]:
    """Write DataFrame to Digistore when run_data_dir set; else session datasets dir. Return dataset_ref, rows, columns."""
    try:
        from digigraph.digistore import digistore_put
        from digigraph.run_storage import get_run_data_dir

        if get_run_data_dir() and session_id is not None:
            ref = digistore_put(session_id, output_name, df.to_dicts())
            return {"dataset_ref": ref, "rows": len(df), "columns": df.columns}
    except (ImportError, OSError, ValueError, TypeError) as e:
        log.debug("write_result: digistore unavailable, falling back to session dir: %s", e)
    try:
        from digigraph.run_storage import get_run_data_dir

        root = get_run_data_dir() or "."
        safe_sid = (session_id or "default").replace("..", "_")
        base = Path(root).resolve() / safe_sid / "datasets"
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{output_name}.json"
        path.write_text(json.dumps(df.to_dicts(), default=str), encoding="utf-8")
        return {"dataset_ref": str(path), "rows": len(df), "columns": df.columns}
    except (OSError, ValueError, TypeError) as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0, "columns": []}
