"""BatchEmbedder - rate limiting, retry, concurrency."""

from __future__ import annotations

import time

from digisearch.embedding.base import EmbeddingProvider


class BatchEmbedder:
    """Wraps EmbeddingProvider with batching, rate limit, retry."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        batch_size: int = 100,
        max_retries: int = 3,
        delay: float = 1.0,
    ) -> None:
        self.provider = provider
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.delay = delay

    @property
    def dimensions(self) -> int:
        return self.provider.dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed in batches with retry."""
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            for attempt in range(self.max_retries):
                try:
                    emb = self.provider.embed(batch)
                    out.extend(emb)
                    break
                except Exception:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.delay * (attempt + 1))
                    else:
                        raise
        return out
