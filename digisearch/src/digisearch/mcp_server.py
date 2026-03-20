"""DigiSearch MCP server. Exposes document search as MCP tools for DigiGraph/DigiFlow."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from digisearch.core.models import Query
from digisearch.search._stub import query_index

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
        content_preview = (r.chunk.content[:400] + "...") if len(r.chunk.content) > 400 else r.chunk.content
        if meta_line:
            lines.append(f"[score={r.score:.2f}] {meta_line}\n{content_preview}")
        else:
            lines.append(f"[score={r.score:.2f}] {content_preview}")
    return "\n\n".join(lines)


def run_mcp(transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server. Default: streamable HTTP on port 8765."""
    mcp.run(transport=transport, host=host, port=port)
