"""DigiSearch – RAG, vectorization, document search for Digi ecosystem.

Exposes: DigiSearch client, DigiIndex interface, DigiDocument, DigiChunk,
HTTP client (query + format_results_table), and MCP server tooling.
"""

from digisearch.client import DigiSearch
from digisearch.core.models import DigiChunk, DigiDocument, DigiQuery, DigiResult

__all__ = [
    "DigiSearch",
    "DigiChunk",
    "DigiDocument",
    "DigiQuery",
    "DigiResult",
]
