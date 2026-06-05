"""Workspace isolation helpers for multi-tenant query filtering."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — filter payloads are heterogeneous metadata


def workspace_structured_clause(workspace_id: str | None) -> dict[str, Any] | None:
    """Return a structured filter clause for *workspace_id*, or None when unset."""
    wid = (workspace_id or "").strip()
    if not wid:
        return None
    return {"field": "workspace_id", "op": "eq", "value": wid}


def merge_workspace_filter(
    filters: dict[str, Any] | None,
    workspace_id: str | None,
) -> dict[str, Any]:
    """Inject mandatory workspace_id into structured filters when provided."""
    clause = workspace_structured_clause(workspace_id)
    if clause is None:
        return dict(filters or {})
    out = dict(filters or {})
    structured = out.get("structured")
    if isinstance(structured, list):
        merged = list(structured)
    else:
        merged = []
    merged.append(clause)
    out["structured"] = merged
    return out


def chunk_matches_workspace(metadata: dict[str, Any] | None, workspace_id: str | None) -> bool:
    """Post-filter stub results by chunk metadata workspace_id."""
    wid = (workspace_id or "").strip()
    if not wid:
        return True
    meta = metadata or {}
    chunk_wid = meta.get("workspace_id")
    if chunk_wid is None:
        return False
    return str(chunk_wid).strip() == wid
