"""EmbeddingCache - SQLite or Redis backed. Prevents re-embedding unchanged chunks."""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from pathlib import Path

from digisearch.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Cache embeddings by content hash. SQLite backend."""

    def __init__(self, provider: EmbeddingProvider, db_path: str | Path | None = None) -> None:
        self.provider = provider
        self._path = db_path or os.environ.get("DIGISEARCH_CACHE_PATH", ".digisearch_embed_cache.db")
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (hash TEXT PRIMARY KEY, embedding BLOB)"
            )
        return self._conn

    def _model_namespace(self) -> str:
        """Prefix cache keys with provider identity so model swaps invalidate hits (REM-103)."""
        model_id = getattr(self.provider, "model_id", None) or getattr(
            self.provider, "model", None
        )
        if model_id:
            return f"{model_id}:{self.provider.dimensions}"
        return f"{type(self.provider).__name__}:{self.provider.dimensions}"

    def _hash(self, text: str) -> str:
        payload = f"{self._model_namespace()}\0{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, texts: list[str]) -> tuple[list[list[float] | None], list[int]]:
        """Get cached embeddings. Returns (list of embedding or None, indices to compute).

        Uses a single batched SELECT WHERE hash IN (...) query instead of N per-row queries.
        """
        import json

        if not texts:
            return [], []
        conn = self._get_conn()
        hashes = [self._hash(t) for t in texts]
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT hash, embedding FROM embeddings WHERE hash IN ({placeholders})",
            hashes,
        ).fetchall()
        hash_to_emb: dict[str, list[float]] = {row[0]: json.loads(row[1]) for row in rows}
        result: list[list[float] | None] = [None] * len(texts)
        to_compute: list[int] = []
        for i, h in enumerate(hashes):
            if h in hash_to_emb:
                result[i] = hash_to_emb[h]
            else:
                to_compute.append(i)
        return result, to_compute

    def set(self, texts: list[str], embeddings: list[list[float]]) -> None:
        """Cache embeddings."""
        import json

        conn = self._get_conn()
        for t, emb in zip(texts, embeddings):
            h = self._hash(t)
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (hash, embedding) VALUES (?, ?)",
                (h, json.dumps(emb)),
            )
        conn.commit()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed with cache. Computes only missing embeddings and fills them in-place.

        Returns a list of the same length as `texts`, preserving positional alignment.
        Raises ValueError if any embedding could not be computed.
        """
        if not texts:
            return []
        result, to_compute = self.get(texts)
        hits = len(texts) - len(to_compute)
        logger.info(
            "EmbeddingCache hit rate: %d/%d (%.0f%%)",
            hits,
            len(texts),
            100.0 * hits / len(texts) if texts else 0.0,
        )
        if to_compute:
            to_embed = [texts[i] for i in to_compute]
            computed = self.provider.embed(to_embed)
            if len(computed) != len(to_compute):
                raise ValueError(
                    f"Embedding provider returned {len(computed)} embeddings for {len(to_compute)} texts"
                )
            self.set(to_embed, computed)
            for j, i in enumerate(to_compute):
                result[i] = computed[j]
        # Verify all slots were filled (guards against provider returning partial results)
        missing = [i for i, r in enumerate(result) if r is None]
        if missing:
            raise ValueError(f"Embeddings missing for {len(missing)} text(s) at indices: {missing[:10]}")
        return result  # type: ignore[return-value]  # all None slots are filled above
