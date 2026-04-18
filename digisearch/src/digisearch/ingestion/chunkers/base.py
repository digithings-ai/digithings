"""Abstract Chunker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from digisearch.core.models import Chunk, Document


class Chunker(ABC):
    """Abstract chunker. Splits Document into Chunks."""

    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]:
        """Chunk document into list of Chunk."""
        ...
