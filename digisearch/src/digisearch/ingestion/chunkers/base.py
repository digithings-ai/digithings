"""Abstract Chunker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from digisearch.core.models import DigiChunk, DigiDocument


class Chunker(ABC):
    """Abstract chunker. Splits DigiDocument into DigiChunks."""

    @abstractmethod
    def chunk(self, doc: DigiDocument) -> list[DigiChunk]:
        """Chunk document into list of DigiChunk."""
        ...
