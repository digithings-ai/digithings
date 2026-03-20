"""Session-scoped store for named datasets. Complements run_storage; blob data on disk, refs can be persisted in LangGraph state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from digigraph.run_storage import _sanitize_session_id, get_run_data_dir


def _datasets_dir(session_id: str | None) -> Path:
    """Base path for session datasets: {run_data_dir}/{session_id}/datasets/."""
    root = get_run_data_dir()
    if not root:
        raise ValueError("run_data_dir not set; Digistore unavailable")
    base = Path(root).resolve()
    safe_sid = _sanitize_session_id(session_id)
    return base / safe_sid / "datasets"


def _safe_name(name: str) -> str:
    """Allow alphanumeric, hyphen, underscore. Reject path separators."""
    if not name or not name.strip():
        raise ValueError("dataset name must be non-empty")
    s = name.strip()
    if "/" in s or "\\" in s or ".." in s:
        raise ValueError("dataset name must not contain path separators or ..")
    return s


def digistore_put(session_id: str | None, name: str, rows: list[dict]) -> str:
    """
    Write a dataset to the session store. Returns dataset_ref (path or logical ref).
    """
    base = _datasets_dir(session_id)
    base.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(name)
    path = base / f"{safe}.json"
    path.write_text(json.dumps(rows, default=str), encoding="utf-8")
    return str(path.resolve())


def digistore_get(session_id: str | None, name_or_ref: str) -> Path:
    """
    Resolve name or path to absolute Path. Accepts logical name (e.g. search_1)
    or path (absolute or relative to session). Raises ValueError if not found or invalid.
    """
    root = get_run_data_dir()
    if not root:
        raise ValueError("run_data_dir not set; cannot resolve dataset_ref")
    base = Path(root).resolve()
    safe_sid = _sanitize_session_id(session_id)
    ref = name_or_ref.strip()
    if not ref:
        raise ValueError("dataset_ref is empty")
    candidate = Path(ref)
    if candidate.is_absolute():
        path = candidate.resolve()
        if not path.is_relative_to(base):
            raise ValueError("dataset_ref must be under run_data_dir")
        if not path.exists():
            raise ValueError(f"dataset_ref file not found: {path}")
        return path

    # Relative: try session/datasets/name.json then session/ref
    if "/" not in ref and "\\" not in ref:
        candidates = [
            base / safe_sid / "datasets" / f"{ref}.json",
            base / safe_sid / ref,
        ]
        for p in candidates:
            resolved = p.resolve()
            if resolved.exists() and resolved.is_relative_to(base):
                return resolved
        raise ValueError(f"dataset_ref not found: {ref}")

    path = (base / safe_sid / ref).resolve()
    if not path.is_relative_to(base):
        raise ValueError("dataset_ref must be under run_data_dir")
    if not path.exists():
        raise ValueError(f"dataset_ref file not found: {path}")
    return path


def digistore_list(session_id: str | None, include_row_count: bool = False) -> list[dict[str, Any]]:
    """
    List datasets in the session. Returns list of {"name": str, "row_count": int?}.
    """
    base = _datasets_dir(session_id)
    if not base.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(base.glob("*.json")):
        name = p.stem
        entry: dict[str, Any] = {"name": name}
        if include_row_count:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                entry["row_count"] = len(data) if isinstance(data, list) else 0
            except Exception:
                entry["row_count"] = None
        out.append(entry)
    return out


def digistore_profile(session_id: str | None, name_or_ref: str, sample_size: int = 5) -> dict[str, Any]:
    """
    Return profile: columns, dtypes, row_count, sample_rows. Used by orchestrator for context.
    """
    path = digistore_get(session_id, name_or_ref)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        return {"error": "Dataset is not a list of rows", "row_count": 0, "columns": [], "sample_rows": []}
    if not data:
        return {"row_count": 0, "columns": [], "dtypes": {}, "sample_rows": []}
    # Infer columns from first row(s)
    rows = data
    all_keys: set[str] = set()
    for r in rows[: 100]:
        if isinstance(r, dict):
            all_keys.update(r.keys())
    columns = sorted(all_keys)
    # Simple dtype heuristic from first non-null values
    dtypes: dict[str, str] = {}
    for c in columns:
        for r in rows:
            v = r.get(c) if isinstance(r, dict) else None
            if v is None:
                continue
            if isinstance(v, bool):
                dtypes[c] = "bool"
            elif isinstance(v, (int, float)):
                dtypes[c] = "number"
            elif isinstance(v, str):
                dtypes[c] = "string"
            else:
                dtypes[c] = "string"
            break
    sample = rows[:sample_size]
    return {
        "row_count": len(rows),
        "columns": columns,
        "dtypes": dtypes,
        "sample_rows": sample,
    }
