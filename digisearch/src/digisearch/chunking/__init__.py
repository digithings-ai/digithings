"""digisearch chunking backends (Chonkie + legacy adapters)."""

from digisearch.chunking.backend import ChunkerBackend
from digisearch.chunking.chonkie_semantic import ChonkieSemanticChunker
from digisearch.chunking.chonkie_token import ChonkieTokenChunker
from digisearch.chunking.document_adapter import BackendDocumentChunker
from digisearch.chunking.factory import (
    DEFAULT_CHUNKER_NAME,
    clear_chunker_cache,
    get_chunker_backend,
    get_document_chunker,
    get_ingest_chunker,
    resolve_chunker_name,
)

__all__ = [
    "BackendDocumentChunker",
    "ChunkerBackend",
    "ChonkieSemanticChunker",
    "ChonkieTokenChunker",
    "DEFAULT_CHUNKER_NAME",
    "clear_chunker_cache",
    "get_chunker_backend",
    "get_document_chunker",
    "get_ingest_chunker",
    "resolve_chunker_name",
]
