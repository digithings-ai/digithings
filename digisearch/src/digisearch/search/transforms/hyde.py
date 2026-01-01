"""HyDE - Hypothetical Document Embeddings."""

from __future__ import annotations


class HyDE:
    """Generate hypothetical answer, embed it as query. Stub."""

    def __init__(self, embedder: object | None = None) -> None:
        self.embedder = embedder

    def embed_query(self, query: str) -> list[float]:
        """Stub: would generate hypothetical doc, embed it. Returns empty for now."""
        if self.embedder and hasattr(self.embedder, "embed"):
            return self.embedder.embed([query])[0]
        return []
