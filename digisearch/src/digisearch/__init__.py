"""DigiSearch – RAG, vectorization, document search for Digi ecosystem.

Exposes: DigiSearch client, DigiIndex interface, Document, Chunk, Query, Result,
HTTP client (query + format_results_table), and MCP server tooling.
"""

from digisearch.client import DigiSearch
from digisearch.core.models import Chunk, Document, Query, Result

__all__ = [
    "DigiSearch",
    "Chunk",
    "Document",
    "Query",
    "Result",
]
