"""DigiSearch MCP server. Exposes document search as MCP tools for DigiGraph/DigiFlow."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from digisearch.atlas_search import search_strategies as _search_strategies_impl
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
    if _digisearch_client is not None:
        try:
            results = _digisearch_client.query(text=text, index_name=idx, top_k=top_k, mode=mode)
            from digisearch.core.models import SearchResponse

            response = SearchResponse(results=results)
        except (RuntimeError, ValueError, ImportError, OSError, TypeError) as e:
            logger.error("DigiSearch client query failed: %s", e)
            return f"[DigiSearch query error: {e}]"
    else:
        allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not allow_stub:
            return "DigiSearch MCP is not wired to a backend client and stub fallback is disabled."
        response = query_index(q, index_name=idx)
    if not response.results:
        return f"No results for query: {text!r}"
    lines = [f"Query: {text}\n---"]
    for r in response.results[:top_k]:
        meta = r.chunk.metadata
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
    return _search_strategies_impl(
        query=query,
        top_k=top_k,
        date_from_ymd=date_from_ymd,
        date_to_ymd=date_to_ymd,
        doc_type=doc_type,
        segment=segment,
        sector=sector,
        run_type=run_type,
        index_name=index_name,
    )


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


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8765,
) -> None:
    """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8765."""
    bind = host or os.environ.get("DIGISEARCH_MCP_HOST", "127.0.0.1")
    mcp.run(transport=transport, host=bind, port=port)
