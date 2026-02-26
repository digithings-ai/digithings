"""EmbeddingCache - SQLite or Redis backed. Prevents re-embedding unchanged chunks."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from digisearch.embedding.base import EmbeddingProvider


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

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, texts: list[str]) -> tuple[list[list[float] | None], list[int]]:
        """Get cached embeddings. Returns (list of embedding or None, indices to compute)."""
        conn = self._get_conn()
        result: list[list[float] | None] = [None] * len(texts)
        to_compute: list[int] = []
        for i, t in enumerate(texts):
            h = self._hash(t)
            row = conn.execute("SELECT embedding FROM embeddings WHERE hash=?", (h,)).fetchone()
            if row:
                import json
                result[i] = json.loads(row[0])
            else:
                to_compute.append(i)
        return result, to_compute

    def set(self, texts: list[str], embeddings: list[list[float]]) -> None:
        """Cache embeddings."""
        conn = self._get_conn()
        for t, emb in zip(texts, embeddings):
            h = self._hash(t)
            import json
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (hash, embedding) VALUES (?, ?)",
                (h, json.dumps(emb)),
            )
        conn.commit()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed with cache. Computes only missing."""
        if not texts:
            return []
        result, to_compute = self.get(texts)
        if to_compute:
            to_embed = [texts[i] for i in to_compute]
            computed = self.provider.embed(to_embed)
            self.set(to_embed, computed)
            for j, i in enumerate(to_compute):
                result[i] = computed[j]
        return [r for r in result if r is not None]
