"""digisearch query logic. Stub, Azure, Chroma backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from digisearch.core.models import Chunk, Query, Result
from digisearch.search._stub import add_chunks, get_stub_index, query_index

if TYPE_CHECKING:
    # Static visibility for the PEP 562 lazy export below; never runs,
    # so the circular-import reason for laziness is unchanged.
    from digisearch.search.vector import VectorSearcher

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
