"""Shared: write DataFrame to Digistore or session dir."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import polars as pl

log = logging.getLogger(__name__)


def _safe_output_name(output_name: str) -> str:
    """Logical dataset leaf name only — reject path separators and ``..``.

    Same rules as :func:`digigraph.digistore._safe_name`. Callers historically
    passed LLM-chosen ``output_name`` straight into a ``Path`` join; a rejected
    digistore write then fell back to that join and could overwrite another
    session's dataset under ``DIGI_RUN_DATA_DIR``.
    """
    if not output_name or not str(output_name).strip():
        raise ValueError("dataset name must be non-empty")
    s = str(output_name).strip()
    if "/" in s or "\\" in s or ".." in s:
        raise ValueError("dataset name must not contain path separators or ..")
    if Path(s).is_absolute():
        raise ValueError("dataset name must be a logical leaf, not an absolute path")
    return s


def write_result(df: pl.DataFrame, session_id: str | None, output_name: str) -> dict[str, Any]:
    """Write DataFrame to Digistore when run_data_dir set; else session datasets dir.

    Returns ``dataset_ref``, ``rows``, ``columns``. Invalid ``output_name`` or a
    digistore size-cap rejection fails closed — never falls back to an unsanitized
    path join that could escape the current session.
    """
    try:
        safe_name = _safe_output_name(output_name)
    except ValueError as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0, "columns": []}

    try:
        from digigraph.digistore import digistore_put
        from digigraph.run_storage import get_run_data_dir

        if get_run_data_dir() and session_id is not None:
            try:
                ref = digistore_put(session_id, safe_name, df.to_dicts())
                return {"dataset_ref": ref, "rows": len(df), "columns": df.columns}
            except ValueError as e:
                # Size cap / digistore rejection — do not bypass via filesystem fallback.
                return {"error": str(e), "dataset_ref": None, "rows": 0, "columns": []}
    except ImportError as e:
        log.debug("write_result: digistore unavailable, falling back to session dir: %s", e)

    try:
        from digigraph.run_storage import _sanitize_session_id, get_run_data_dir

        root = get_run_data_dir() or "."
        safe_sid = _sanitize_session_id(session_id)
        base = (Path(root).resolve() / safe_sid / "datasets").resolve()
        base.mkdir(parents=True, exist_ok=True)
        path = (base / f"{safe_name}.json").resolve()
        if not path.is_relative_to(base):
            return {
                "error": "dataset_ref must stay under the session datasets dir",
                "dataset_ref": None,
                "rows": 0,
                "columns": [],
            }
        path.write_text(json.dumps(df.to_dicts(), default=str), encoding="utf-8")
        return {"dataset_ref": str(path), "rows": len(df), "columns": df.columns}
    except (OSError, ValueError, TypeError) as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0, "columns": []}
