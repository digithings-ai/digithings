"""Temporary run-scoped storage for retrieval results. Enables dataset_ref for downstream tools."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path


def _sanitize_session_id(session_id: str | None) -> str:
    """Allow only alphanumeric, hyphen, underscore. Max 64 chars. Default to 'default' if empty."""
    if not session_id or not str(session_id).strip():
        return "default"
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", str(session_id).strip())
    return s[:64] or "default"


def get_run_data_dir() -> str | None:
    """Run data root from DIGI_RUN_DATA_DIR or project config. None = feature disabled."""
    import os

    path = os.environ.get("DIGI_RUN_DATA_DIR", "").strip()
    if path:
        return path
    try:
        from digigraph.project_config import DigiProjectConfig

        cfg = DigiProjectConfig.load()
        path = cfg.get_run_data_dir()
        if path and str(path).strip():
            return str(path).strip()
    except Exception:
        pass
    return None


def write_search_results(
    session_id: str | None,
    results: list[dict],
    run_id: str | None = None,
) -> str:
    """
    Write search results to a session/run-scoped JSON file and to Digistore (when available).
    Returns absolute path (dataset_ref). Call only when run_data_dir is set; otherwise do not call.
    """
    root = get_run_data_dir()
    if not root:
        raise ValueError("run_data_dir not set; cannot write search results")
    base = Path(root).resolve()
    safe_sid = _sanitize_session_id(session_id)
    run_id = run_id or str(uuid.uuid4())[:8]
    # One file per run: {session_id}/{run_id}.json (legacy)
    session_dir = base / safe_sid
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"{run_id}.json"
    path.write_text(json.dumps(results, default=str), encoding="utf-8")
    ref = str(path.resolve())
    # Also write to Digistore with stable name for session (search_1, search_2, ...)
    try:
        from digigraph.digistore import digistore_get, digistore_list, digistore_put

        existing = digistore_list(session_id, include_row_count=False)
        next_idx = len(existing) + 1
        digistore_name = f"search_{next_idx}"
        digistore_put(session_id, digistore_name, results)
        ref = str(digistore_get(session_id, digistore_name))
    except Exception:
        pass
    return ref


def resolve_dataset_ref(session_id: str | None, dataset_ref: str) -> Path:
    """
    Resolve and validate dataset_ref to a Path. Must be under run_data_dir and session-scoped.
    Accepts absolute path, relative path, or Digistore logical name (no path separators).
    Raises ValueError if ref is invalid or escapes the allowed root.
    """
    try:
        from digigraph.digistore import digistore_get

        return digistore_get(session_id, dataset_ref)
    except ImportError:
        pass
    root = get_run_data_dir()
    if not root:
        raise ValueError("run_data_dir not set; cannot resolve dataset_ref")
    base = Path(root).resolve()
    ref = dataset_ref.strip()
    if not ref:
        raise ValueError("dataset_ref is empty")
    candidate = Path(ref)
    if not candidate.is_absolute():
        safe_sid = _sanitize_session_id(session_id)
        path = (base / safe_sid / ref).resolve()
    else:
        path = candidate.resolve()
    if not path.is_relative_to(base):
        raise ValueError("dataset_ref must be under run_data_dir")
    if not path.exists():
        raise ValueError(f"dataset_ref file not found: {path}")
    return path


def path_relative_to_run_data_dir(absolute_path: str | Path) -> str | None:
    """
    Return path relative to run_data_dir if the file is under it; else None.
    Used to build download URLs for exports (e.g. default/export.csv).
    """
    root = get_run_data_dir()
    if not root:
        return None
    base = Path(root).resolve()
    path = Path(absolute_path).resolve()
    try:
        rel = path.relative_to(base)
    except ValueError:
        return None
    if ".." in str(rel) or str(rel).startswith(".."):
        return None
    return str(rel).replace("\\", "/")
