"""Apply structured metadata filters to chunk metadata (stub / post-filter)."""

from __future__ import annotations

from typing import Any

from digisearch.core.tables import FilterClause, matches_filters


def chunk_metadata_matches(structured: list[dict[str, Any]] | None, meta: dict[str, Any] | None) -> bool:
    """Return True if *meta* satisfies all structured filter clauses (AND)."""
    if not structured:
        return True
    clauses = [
        FilterClause(field=f.get("field"), op=f.get("op") or "eq", value=f.get("value"))
        for f in structured
        if isinstance(f, dict) and f.get("field") is not None
    ]
    return matches_filters({"metadata": dict(meta or {})}, clauses)
