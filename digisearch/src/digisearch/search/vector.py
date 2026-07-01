"""VectorSearcher - ANN search over embeddings via DigiIndex."""

from __future__ import annotations

import logging
import time

from digisearch.core.models import Query, Result
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)


class VectorSearcher:
    """ANN search over embeddings. Uses DigiIndex + EmbeddingProvider."""

    def __init__(self, index: DigiIndex, embed_text: "object | None" = None) -> None:
        self.index = index
        self._embed = embed_text  # callable(text: str) -> list[float] or EmbeddingProvider

    def search(self, query: Query) -> list[Result]:
        """Run vector search. Embeds query if provider set."""
        start = time.perf_counter()
        try:
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
            results = self.index.query(query)
        except Exception:
            logger.exception(
                "vector search failed",
                extra={
                    "operation": "vector_search",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "top_k": query.top_k,
                },
            )
            raise
        logger.info(
            "vector search done",
            extra={
                "operation": "vector_search",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "top_k": query.top_k,
                "result_count": len(results),
                "vector_dim": len(query.embedding) if query.embedding else 0,
            },
        )
        return results
