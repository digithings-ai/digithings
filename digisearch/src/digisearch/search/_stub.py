"""Stub and Azure query logic. Used when no DigiIndex is configured."""

from __future__ import annotations

from digisearch.core.models import DigiChunk, DigiQuery, DigiResult, SearchResponse

_stub_index: dict[str, list[DigiChunk]] = {"default": []}


def _query_azure(query: DigiQuery, index_name: str) -> SearchResponse:
    """Delegate to Azure when configured."""
    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, query_azure

        if is_azure_configured():
            return query_azure(query, index_name)
    except ImportError:
        pass
    return SearchResponse(results=[], facets=None)


def query_index(query: DigiQuery, index_name: str = "default") -> SearchResponse:
    """Search index. Uses Azure when configured; else Chroma when available; else stub."""
    azure_response = _query_azure(query, index_name)
    if azure_response.results:
        return azure_response

    # TODO: Chroma via DigiSearch client registry
    chunks = _stub_index.get(index_name, [])
    if not chunks:
        return SearchResponse(results=[], facets=None)
    text_lower = query.text.lower()
    out: list[DigiResult] = []
    for i, c in enumerate(chunks):
        if text_lower in c.content.lower():
            out.append(DigiResult(chunk=c, score=0.9, rank=i + 1))
    return SearchResponse(results=out[: query.top_k], facets=None)


def add_chunks(index_name: str, chunks: list[DigiChunk]) -> None:
    """Add chunks to stub index."""
    _stub_index.setdefault(index_name, []).extend(chunks)


def get_stub_index() -> dict[str, list[DigiChunk]]:
    """Expose for tests."""
    return _stub_index
