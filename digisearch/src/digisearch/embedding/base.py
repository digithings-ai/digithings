"""EmbeddingProvider abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract embedding provider. OpenAI, HuggingFace, etc. implement this."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts. Returns list of vectors."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimension."""
        ...
