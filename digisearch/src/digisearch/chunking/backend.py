"""Swappable text-chunking backend protocol."""

from __future__ import annotations

from typing import Protocol

from digisearch.core.models import Chunk


class ChunkerBackend(Protocol):
    """Thin interface over an underlying text chunker (e.g. Chonkie).

    Operates on raw text so backends stay independent of digisearch Document
    lifecycle. Callers that need ``doc_id`` / stable chunk ids wrap this via
    :class:`~digisearch.chunking.document_adapter.BackendDocumentChunker`.
    """

    def chunk(self, text: str) -> list[Chunk]:
        """Split *text* into digisearch :class:`~digisearch.core.models.Chunk` values."""
        ...
