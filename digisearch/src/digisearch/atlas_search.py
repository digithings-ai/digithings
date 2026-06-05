"""Atlas research search helpers (MCP-free).

``search_strategies`` is the typed query surface used by the DigiSearch MCP
tool and unit tests. Keeping it out of ``mcp_server.py`` avoids importing
``mcp`` in stub-only test environments.
"""

from __future__ import annotations

from typing import Any

from digisearch.atlas_ingest import ATLAS_FILTERABLE_FIELDS, ATLAS_INDEX_NAME
from digisearch.core.models import Query
from digisearch.search._stub import query_index


def _atlas_filters(
    *,
    date_from_ymd: int | None,
    date_to_ymd: int | None,
    doc_type: str | None,
    segment: str | None,
    sector: str | None,
    run_type: str | None,
) -> list[dict[str, Any]]:
    """Build structured filters for ``search_strategies`` from keyword args."""
    clauses: list[dict[str, Any]] = []
    if date_from_ymd is not None:
        clauses.append({"field": "date_ordinal", "op": "ge", "value": int(date_from_ymd)})
    if date_to_ymd is not None:
        clauses.append({"field": "date_ordinal", "op": "le", "value": int(date_to_ymd)})
    for field, value in (
        ("doc_type", doc_type),
        ("segment", segment),
        ("sector", sector),
        ("run_type", run_type),
    ):
        if value is None or not str(value).strip():
            continue
        if field not in ATLAS_FILTERABLE_FIELDS:
            continue
        clauses.append({"field": field, "op": "eq", "value": str(value).strip()})
    return clauses


def search_strategies(
    query: str,
    top_k: int = 10,
    date_from_ymd: int | None = None,
    date_to_ymd: int | None = None,
    doc_type: str | None = None,
    segment: str | None = None,
    sector: str | None = None,
    run_type: str | None = None,
    index_name: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over the Atlas research library indexed by DigiSearch."""
    idx = (index_name or ATLAS_INDEX_NAME or "atlas").strip() or "atlas"
    structured = _atlas_filters(
        date_from_ymd=date_from_ymd,
        date_to_ymd=date_to_ymd,
        doc_type=doc_type,
        segment=segment,
        sector=sector,
        run_type=run_type,
    )
    q = Query(
        text=query,
        top_k=max(1, min(int(top_k), 100)),
        mode="hybrid",
        filters={"structured": structured} if structured else {},
    )
    response = query_index(q, index_name=idx)
    out: list[dict[str, Any]] = []
    for r in response.results[: q.top_k]:
        content = r.chunk.content
        out.append(
            {
                "chunk_id": r.chunk.id,
                "doc_id": r.chunk.doc_id,
                "score": float(r.score),
                "content": content[:1000] + ("..." if len(content) > 1000 else ""),
                "content_length": len(content),
                "metadata": dict(r.chunk.metadata or {}),
            }
        )
    return out
