"""DigiSearch query logic. Stub, Azure, Chroma backends."""

from __future__ import annotations

from digisearch.core.models import DigiChunk, DigiQuery, DigiResult

from digisearch.search._stub import add_chunks, get_stub_index, query_index

__all__ = [
    "query_index",
    "add_chunks",
    "get_stub_index",
    "VectorSearcher",
]

# Lazy import to avoid circular deps
def __getattr__(name: str):
    if name == "VectorSearcher":
        from digisearch.search.vector import VectorSearcher
        return VectorSearcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
