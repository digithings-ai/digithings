"""DigiSearch HTTP API for DigiGraph and DigiFlow. Phase 1: health, query, ingest stubs."""

from __future__ import annotations

import uuid
from typing import Any

from digisearch.core.models import DigiChunk, DigiQuery
from digisearch.search._stub import add_chunks, query_index

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="DigiSearch",
    description="RAG, document search for Digi ecosystem. MCP tools for DigiGraph/DigiFlow.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    text: str = Field(..., description="Search query text")
    index_name: str = Field(default="default", description="Index/collection name")
    top_k: int = Field(default=10, ge=1, le=100)
    mode: str = Field(default="hybrid", description="keyword | vector | hybrid")
    format: str = Field(default="default", description="default | table — table returns formatted markdown in response.formatted")
    filter: str | None = Field(default=None, description="Raw OData filter (when index allow_raw_filter)")
    filters: list[dict[str, Any]] | None = Field(default=None, description="Structured filters [{field, op, value}]")
    columns: list[str] | None = Field(default=None, description="Metadata columns to return")
    response_mode: str = Field(default="full", description="full | summary — return full rows or data summary")
    summarize_if_over: int | None = Field(default=None, ge=1, description="If result count > this, return summary instead of full")
    facets: list[str] | None = Field(default=None, description="Azure: facet expressions e.g. ['sourceType', 'itemType,count:20']")
    highlight_fields: list[str] | None = Field(default=None, description="Azure: fields to highlight matches in (searchable fields)")
    highlight_pre_tag: str | None = Field(default=None, description="Azure: tag before highlighted term e.g. '<em>'")
    highlight_post_tag: str | None = Field(default=None, description="Azure: tag after highlighted term e.g. '</em>'")
    order_by: list[str] | None = Field(default=None, description="Azure: sort clauses e.g. ['sentDateTime desc', 'search.score() desc']")
    skip: int = Field(default=0, ge=0, description="Pagination offset (page size = top_k)")
    include_total_count: bool = Field(default=False, description="When true, total is full match count for pagination")


class QueryResponse(BaseModel):
    """Response for POST /query."""

    results: list[dict]
    query: str
    index_name: str
    total: int
    formatted: str | None = Field(default=None, description="When format=table, markdown table string for display")
    summary: dict[str, Any] | None = Field(default=None, description="Data summary when response_mode=summary or over threshold")
    facets: dict[str, list[dict[str, Any]]] | None = Field(default=None, description="Facet counts by field when facets requested (Azure)")


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    source: str = Field(..., description="File path or URL")
    index_name: str = Field(default="default")
    doc_type: str | None = Field(default=None, description="pdf, html, docx, etc.")


class IngestResponse(BaseModel):
    """Response for POST /ingest."""

    doc_id: str
    chunks_created: int
    index_name: str
    status: str = "ok"


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for Docker and DigiGraph."""
    return {"status": "ok", "service": "digisearch"}


@app.get("/azure_status")
def azure_status() -> dict[str, bool | str]:
    """Check if Azure AI Search is configured and reachable."""
    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, _get_client

        if not is_azure_configured():
            return {"configured": False, "message": "Set AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME"}
        client = _get_client()
        if client is None:
            return {"configured": True, "reachable": False, "message": "Client init failed"}
        # Quick count to verify connection
        _ = client.get_document_count()
        return {"configured": True, "reachable": True, "message": "ok"}
    except ImportError:
        return {"configured": False, "message": "Install digisearch[azure] for Azure backend"}
    except Exception as e:
        return {"configured": True, "reachable": False, "message": str(e)[:200]}


def _build_query_filters(req: QueryRequest) -> dict[str, Any]:
    """Build DigiQuery.filters from request: either raw odata or structured list."""
    filters: dict[str, Any] = {}
    if req.filter and req.filter.strip():
        filters["odata"] = req.filter.strip()
    if req.filters:
        filters["structured"] = req.filters
    return filters


@app.post("/query", response_model=QueryResponse)
def api_query(req: QueryRequest) -> QueryResponse:
    """Search documents. Use format=table to get response.formatted as markdown table."""
    q = DigiQuery(
        text=req.text,
        top_k=req.top_k,
        mode=req.mode,
        filters=_build_query_filters(req),
        columns=req.columns,
        facets=req.facets,
        highlight_fields=req.highlight_fields,
        highlight_pre_tag=req.highlight_pre_tag,
        highlight_post_tag=req.highlight_post_tag,
        order_by=req.order_by,
        skip=req.skip,
        include_total_count=req.include_total_count,
    )
    response = query_index(q, index_name=req.index_name)
    results = response.results
    # Build each result: content, score, doc_id, rank, and metadata (exclude @search.score; already at top level)
    out_results: list[dict] = []
    for r in results:
        meta = dict(r.chunk.metadata)
        meta.pop("@search.score", None)
        out_results.append({
            "content": r.chunk.content[:500],
            "score": r.score,
            "doc_id": r.chunk.doc_id,
            "rank": r.rank,
            "metadata": meta,
        })
    summary: dict[str, Any] | None = None
    use_summary = (req.response_mode or "").strip().lower() == "summary" or (
        req.summarize_if_over is not None and len(out_results) > req.summarize_if_over
    )
    if use_summary and out_results:
        from digisearch.core.summarize import summarize_results

        summary_obj = summarize_results(out_results, sample_size=5, include_text_summary=True)
        summary = summary_obj
        # Return first 5 results as sample so response shape stays consistent (content, score, doc_id, rank, metadata)
        out_results = out_results[:5]
    formatted: str | None = None
    if (getattr(req, "format", None) or "").strip().lower() == "table":
        from digisearch.http_client import format_results_table

        formatted = format_results_table(out_results, req.text, top_k=req.top_k)
    total = response.total_count if response.total_count is not None else len(results)
    return QueryResponse(
        results=out_results,
        query=req.text,
        index_name=req.index_name,
        total=total,
        formatted=formatted,
        summary=summary,
        facets=response.facets,
    )


@app.post("/ingest", response_model=IngestResponse)
def api_ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document. Uses parsers + chunkers when available."""
    try:
        from pathlib import Path

        from digisearch.ingestion.chunkers.recursive import RecursiveChunker
        from digisearch.ingestion.registry import ParserRegistry

        path = Path(req.source)
        if path.exists():
            registry = ParserRegistry()
            doc = registry.parse(path)
            chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
            chunks = chunker.chunk(doc)
            doc.chunks = chunks
            add_chunks(req.index_name, chunks)
            return IngestResponse(
                doc_id=doc.id,
                chunks_created=len(chunks),
                index_name=req.index_name,
            )
    except ImportError:
        pass
    except Exception:
        pass
    doc_id = str(uuid.uuid4())
    chunk = DigiChunk(
        id=f"{doc_id}_0",
        content=f"[Stub] Ingested: {req.source}",
        doc_id=doc_id,
        embedding=None,
        metadata={"source": req.source},
    )
    add_chunks(req.index_name, [chunk])
    return IngestResponse(
        doc_id=doc_id,
        chunks_created=1,
        index_name=req.index_name,
    )


@app.get("/indexes")
def list_indexes() -> dict[str, list[str]]:
    """List available indexes."""
    from digisearch.search._stub import get_stub_index

    return {"indexes": list(get_stub_index().keys())}


@app.get("/indexes/{name}")
def get_index(name: str) -> dict:
    """Get index metadata."""
    from digisearch.search._stub import get_stub_index

    idx = get_stub_index()
    if name not in idx:
        raise HTTPException(status_code=404, detail=f"Index {name} not found")
    return {"name": name, "chunks": len(idx[name])}


@app.delete("/indexes/{name}/documents/{doc_id}")
def delete_document(name: str, doc_id: str) -> dict:
    """Delete document from index. Stub: no-op for in-memory."""
    return {"status": "ok", "message": "Delete not yet implemented for stub index"}
