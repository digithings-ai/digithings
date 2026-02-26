"""DigiSearch MCP server. Exposes document search as MCP tools for DigiGraph/DigiFlow."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from digisearch.core.models import DigiQuery
from digisearch.search._stub import query_index

mcp = FastMCP(
    "DigiSearch",
    json_response=True,
)

DIGISEARCH_INDEX = os.environ.get("DIGISEARCH_INDEX", "default")


def create_mcp_with_indexes(client: object) -> FastMCP:
    """Create MCP server. Returns default mcp (index_name param supports multi-index)."""
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
    q = DigiQuery(text=text, top_k=top_k, mode=mode)
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
