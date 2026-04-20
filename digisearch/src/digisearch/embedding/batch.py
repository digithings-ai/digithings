"""BatchEmbedder - rate limiting, retry, concurrency."""

from __future__ import annotations

import logging
import time

from digisearch.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)


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
        perf_start = time.perf_counter()
        out: list[list[float]] = []
        batches = 0
        try:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                batches += 1
                for attempt in range(self.max_retries):
                    try:
                        emb = self.provider.embed(batch)
                        out.extend(emb)
                        break
                    except Exception:
                        if attempt < self.max_retries - 1:
                            logger.warning(
                                "embed batch retry",
                                extra={
                                    "operation": "embed_batch",
                                    "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                                    "outcome": "error",
                                    "attempt": attempt + 1,
                                    "batch_size": len(batch),
                                },
                            )
                            time.sleep(self.delay * (attempt + 1))
                        else:
                            raise
        except Exception:
            logger.exception(
                "embed_batch failed",
                extra={
                    "operation": "embed_batch",
                    "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                    "outcome": "error",
                    "text_count": len(texts),
                },
            )
            raise
        logger.info(
            "embed_batch done",
            extra={
                "operation": "embed_batch",
                "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                "outcome": "ok",
                "text_count": len(texts),
                "batch_count": batches,
                "batch_size": self.batch_size,
                "vector_dim": self.provider.dimensions,
            },
        )
        return out
