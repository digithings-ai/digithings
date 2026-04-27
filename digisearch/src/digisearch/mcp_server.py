"""DigiSearch MCP server. Exposes document search as MCP tools for DigiGraph/DigiFlow."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from digisearch.atlas_ingest import ATLAS_FILTERABLE_FIELDS, ATLAS_INDEX_NAME
from digisearch.core.models import Query
from digisearch.logging import configure_logging
from digisearch.search._stub import query_index

configure_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "DigiSearch",
    json_response=True,
)

DIGISEARCH_INDEX = os.environ.get("DIGISEARCH_INDEX", "default")

# Module-level client reference, set by create_mcp_with_indexes when a real backend is available.
_digisearch_client: Any | None = None


def create_mcp_with_indexes(client: object) -> FastMCP:
    """Wire a DigiSearch client into the MCP server so tools use the real backend.

    Call this at startup when a configured client is available. Without it, tools
    fall back to the in-memory stub (development only).
    """
    global _digisearch_client
    _digisearch_client = client
    if client is not None:
        logger.info("DigiSearch MCP server wired to real client: %s", type(client).__name__)
    else:
        logger.warning("create_mcp_with_indexes called with None — MCP tools will use stub backend")
    return mcp


@mcp.tool()
def digisearch_query(
    text: str,
    index_name: str | None = None,
    top_k: int = 10,
    mode: str = "hybrid",
) -> str:
    """Search documents in DigiSearch. Returns relevant chunks for RAG or agent context.

    Use this when you need to find information in ingested documents (research papers,
    strategy docs, compliance docs, etc.). Supports keyword, vector, and hybrid search.
    """
    idx = index_name or DIGISEARCH_INDEX or "default"
    q = Query(text=text, top_k=top_k, mode=mode)
    # Use the wired client when available; fall back to stub otherwise.
    if _digisearch_client is not None:
        try:
            results = _digisearch_client.query(text=text, index_name=idx, top_k=top_k, mode=mode)
            from digisearch.core.models import SearchResponse

            response = SearchResponse(results=results)
        except Exception as e:
            logger.error("DigiSearch client query failed: %s — falling back to stub", e)
            response = query_index(q, index_name=idx)
    else:
        response = query_index(q, index_name=idx)
    if not response.results:
        return f"No results for query: {text!r}"
    lines = [f"Query: {text}\n---"]
    for r in response.results[:top_k]:
        meta = r.chunk.metadata
        # Build a short metadata line from common fields when present
        parts = []
        if meta.get("subject"):
            parts.append(f"subject={meta['subject'][:80]!r}")
        if meta.get("fromName") or meta.get("fromAddress"):
            parts.append(f"from={meta.get('fromName') or meta.get('fromAddress')}")
        if meta.get("sourceType"):
            parts.append(f"source={meta['sourceType']}")
        if meta.get("sentDateTime") or meta.get("createdDateTime"):
            parts.append(f"date={meta.get('sentDateTime') or meta.get('createdDateTime')}")
        meta_line = " | ".join(parts) if parts else None
        content_preview = (
            (r.chunk.content[:400] + "...") if len(r.chunk.content) > 400 else r.chunk.content
        )
        if meta_line:
            lines.append(f"[score={r.score:.2f}] {meta_line}\n{content_preview}")
        else:
            lines.append(f"[score={r.score:.2f}] {content_preview}")
    return "\n\n".join(lines)


def _atlas_filters(
    *,
    date_from_ymd: int | None,
    date_to_ymd: int | None,
    doc_type: str | None,
    segment: str | None,
    sector: str | None,
    run_type: str | None,
) -> list[dict[str, Any]]:
    """Build structured filters for ``search_strategies`` from MCP tool args.

    Empty lists pass through ``query_index`` as a no-op (no filters applied);
    the MCP tool only refuses fields that are not in
    :data:`ATLAS_FILTERABLE_FIELDS` to keep the surface tight.
    """
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


@mcp.tool()
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
    """Semantic search over the Atlas research library indexed by DigiSearch.

    Filters are AND-combined. Date range filters use ``date_ordinal`` (an
    integer ``YYYYMMDD`` stamped at ingest); pass e.g. ``date_from_ymd=20260420``
    for "on or after 2026-04-20". String filters (``doc_type``, ``segment``,
    ``sector``, ``run_type``) match exactly and case-sensitively against the
    metadata stamped by :func:`digisearch.atlas_ingest.ingest_atlas_payload`.

    Returns up to ``top_k`` typed result dicts:
    ``{chunk_id, doc_id, content, content_length, score, metadata}``. Empty
    list when nothing matches.
    """
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


try:
    import json as _json

    from digisearch.agent.pipeline import run_research_turn as _run_research_turn

    @mcp.tool()
    def digisearch_research_turn(
        user_message: str,
        index_name: str | None = None,
        top_k: int = 10,
        mode: str = "hybrid",
    ) -> str:
        """Composite research turn (plan → retrieve → aggregate) with citations for hub/trace parity."""
        payload = {
            "user_message": user_message,
            "index_name": index_name or DIGISEARCH_INDEX or "default",
            "top_k": top_k,
            "mode": mode,
        }
        return _json.dumps(_run_research_turn(payload), indent=2)

except ImportError:
    logger.info("digisearch_research_turn MCP tool omitted (install digisearch[agent])")


def run_mcp(transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server. Default: streamable HTTP on port 8765."""
    mcp.run(transport=transport, host=host, port=port)
