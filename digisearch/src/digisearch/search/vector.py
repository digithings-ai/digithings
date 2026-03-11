"""VectorSearcher - ANN search over embeddings via DigiIndex."""

from __future__ import annotations

from digisearch.core.models import Query, Result
from digisearch.indexes.base import DigiIndex


class VectorSearcher:
    """ANN search over embeddings. Uses DigiIndex + EmbeddingProvider."""

    def __init__(self, index: DigiIndex, embed_text: "object | None" = None) -> None:
        self.index = index
        self._embed = embed_text  # callable(text: str) -> list[float] or EmbeddingProvider

    def search(self, query: Query) -> list[Result]:
        """Run vector search. Embeds query if provider set."""
        if self._embed and not query.embedding:
            if hasattr(self._embed, "embed"):
                emb = self._embed.embed([query.text])[0]
            else:
                emb = self._embed(query.text)  # type: ignore
            query = Query(
                text=query.text,
                embedding=emb,
                top_k=query.top_k,
                filters=query.filters,
                mode=query.mode,
            )
        return self.index.query(query)
