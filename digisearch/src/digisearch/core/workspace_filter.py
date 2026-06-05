"""Workspace isolation helpers for multi-tenant query filtering."""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — filter payloads are heterogeneous metadata

from digisearch.core.filter_validator import validate_odata_filter


def build_query_filters(
    *,
    filter_raw: str | None = None,
    filters_struct: list[dict[str, Any]] | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Build query.filters from OData and/or structured clauses; optional workspace isolation."""
    filters: dict[str, Any] = {}
    if filter_raw and filter_raw.strip():
        filters["odata"] = validate_odata_filter(filter_raw.strip())
    if filters_struct:
        filters["structured"] = filters_struct
    wid = (workspace_id or "").strip() or None
    return merge_workspace_filter(filters, wid)


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
