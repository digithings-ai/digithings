"""DigiIndex abstract interface. All backends implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod

from digisearch.core.models import DigiChunk, DigiQuery, DigiResult


class DigiIndex(ABC):
    """Abstract index interface. Chroma, Azure, etc. implement this."""

    name: str
    embedding_provider: object | None = None  # EmbeddingProvider when set

    @abstractmethod
    def add(self, chunks: list[DigiChunk]) -> None:
        """Add chunks to index."""
        ...

    @abstractmethod
    def query(self, query: DigiQuery) -> list[DigiResult]:
        """Search index. Returns ranked results."""
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete chunks by id."""
        ...

    @abstractmethod
    def update(self, chunks: list[DigiChunk]) -> None:
        """Update chunks (upsert)."""
        ...

    @abstractmethod
    def list_collections(self) -> list[str]:
        """List collection/index names."""
        ...

    @abstractmethod
    def snapshot(self, path: str) -> None:
        """Export snapshot to path."""
        ...

