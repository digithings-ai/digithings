"""SQLite exact-scan backend for digisearch. No external service or package.

This is the free/default vector backend: embeddings are stored as float32 blobs
in a local SQLite database and queries run an exact cosine scan. It implements
the same ``DigiIndex`` contract as :class:`~digisearch.indexes.backends.chroma.ChromaBackend`
and reuses the shared structured/workspace post-filters, so switching backends
does not change hit semantics for the supported query features.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
import time
from array import array
from pathlib import Path
from typing import Any

from digisearch.core.evidence_metadata import normalize_metadata_for_chroma
from digisearch.core.filter_apply import chunk_metadata_matches
from digisearch.core.models import Chunk, Query, Result
from digisearch.core.workspace_filter import chunk_matches_workspace
from digisearch.embedding.providers.minilm import get_default_minilm_embedder
from digisearch.indexes.backends.backend_errors import SearchBackendError
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)

DEFAULT_SQLITE_PATH = ".digisearch/index.sqlite3"
MAX_TOP_K = 100

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    collection TEXT NOT NULL,
    id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (collection, id)
);
CREATE INDEX IF NOT EXISTS idx_chunks_collection ON chunks(collection);
CREATE TABLE IF NOT EXISTS collection_dimensions (
    collection TEXT PRIMARY KEY,
    dimension INTEGER NOT NULL
);
"""


def _db_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    configured = os.environ.get("DIGISEARCH_SQLITE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    workspace = os.environ.get("DIGI_WORKSPACE", "").strip()
    if workspace:
        return Path(workspace).expanduser() / ".digisearch" / "index.sqlite3"
    return Path(DEFAULT_SQLITE_PATH)


def _encode(embedding: list[float]) -> bytes:
    return array("f", (float(v) for v in embedding)).tobytes()


def _decode(blob: bytes) -> list[float]:
    values = array("f")
    values.frombytes(blob)
    return list(values)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError(f"embedding dimension mismatch: {len(left)} != {len(right)}")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


class SQLiteExactBackend(DigiIndex):
    """Exact cosine vector index backed by a single local SQLite file."""

    def __init__(
        self,
        name: str,
        db_path: str | Path | None = None,
        embedding_provider: object | None = None,
    ) -> None:
        self.name = name
        self.embedding_provider = embedding_provider
        self._db_path = _db_path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _resolved_provider(self) -> object:
        return self.embedding_provider or get_default_minilm_embedder()

    def _embed(self, chunks: list[Chunk]) -> list[list[float]]:
        have = [chunk.embedding is not None for chunk in chunks]
        if any(have) and not all(have):
            missing = [c.id for c, ok in zip(chunks, have, strict=True) if not ok]
            raise ValueError(
                "partial embedding batch refused: chunks missing precomputed embeddings "
                f"{missing!r}; supply embeddings for every chunk or for none"
            )
        if all(have):
            return [[float(v) for v in chunk.embedding or []] for chunk in chunks]
        provider = self._resolved_provider()
        try:
            raw = provider.embed([chunk.content for chunk in chunks])  # type: ignore[attr-defined]
        except Exception as exc:
            raise SearchBackendError(f"embedding provider failed for {self.name!r}: {exc}") from exc
        if len(raw) != len(chunks):
            raise SearchBackendError(
                f"embedding provider returned {len(raw)} vectors for {len(chunks)} chunks "
                f"in {self.name!r}"
            )
        return [[float(v) for v in vec] for vec in raw]

    def _stored_dimension(self) -> int | None:
        """Return the collection's embedding width, including legacy databases.

        New databases record the width in ``collection_dimensions``. A database
        written before that table existed is inferred from the stored float32
        blobs; mixed widths there are refused rather than silently scored.
        """
        row = self._conn.execute(
            "SELECT dimension FROM collection_dimensions WHERE collection = ?",
            (self.name,),
        ).fetchone()
        if row:
            return int(row[0])
        row = self._conn.execute(
            "SELECT MIN(length(embedding)), MAX(length(embedding)) "
            "FROM chunks WHERE collection = ?",
            (self.name,),
        ).fetchone()
        if not row or row[0] is None:
            return None
        low, high = int(row[0]), int(row[1])
        if low != high or low % 4:
            raise SearchBackendError(
                f"collection {self.name!r} contains mixed or malformed embeddings; "
                "re-index it with one embedding model"
            )
        return low // 4

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        start = time.perf_counter()
        embeddings = self._embed(chunks)
        dimension = len(embeddings[0])
        if dimension == 0 or any(len(vec) != dimension for vec in embeddings):
            raise SearchBackendError(
                f"sqlite index refused batch for {self.name!r}: every embedding "
                "must have the same non-zero dimension"
            )
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = embedding
        rows = [
            (
                self.name,
                chunk.id,
                chunk.doc_id,
                chunk.content,
                json.dumps(
                    {**normalize_metadata_for_chroma(chunk.metadata), "doc_id": chunk.doc_id},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                _encode(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        try:
            with self._lock, self._conn:
                stored = self._stored_dimension()
                if stored is not None and stored != dimension:
                    raise SearchBackendError(
                        f"sqlite index dimension mismatch for {self.name!r}: "
                        f"collection uses {stored}, batch uses {dimension}"
                    )
                if stored is not None:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO collection_dimensions(collection, dimension) "
                        "VALUES (?, ?)",
                        (self.name, stored),
                    )
                else:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO collection_dimensions(collection, dimension) "
                        "VALUES (?, ?)",
                        (self.name, dimension),
                    )
                    stored = self._stored_dimension()
                    if stored != dimension:
                        raise SearchBackendError(
                            f"sqlite index dimension mismatch for {self.name!r}: "
                            f"collection uses {stored}, batch uses {dimension}"
                        )
                self._conn.executemany(
                    """
                    INSERT INTO chunks(collection, id, doc_id, content, metadata, embedding)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(collection, id) DO UPDATE SET
                        doc_id = excluded.doc_id,
                        content = excluded.content,
                        metadata = excluded.metadata,
                        embedding = excluded.embedding
                    """,
                    rows,
                )
        except SearchBackendError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            logger.exception("sqlite index failed")
            raise SearchBackendError(f"sqlite index failed for {self.name!r}: {exc}") from exc
        logger.info(
            "sqlite index done",
            extra={
                "operation": "sqlite_index",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "collection": self.name,
                "chunk_count": len(chunks),
            },
        )

    def _query(self, query: Query) -> tuple[list[Result], int]:
        n = min(max(int(query.top_k or 0), 0), MAX_TOP_K)
        offset = max(int(query.skip or 0), 0)
        filters = query.filters or {}
        structured = (
            filters.get("structured") if isinstance(filters.get("structured"), list) else None
        )
        provider = self._resolved_provider()
        embedding = query.embedding
        if embedding is None:
            try:
                embedding = provider.embed([query.text])[0]  # type: ignore[attr-defined]
            except Exception as exc:
                raise SearchBackendError(
                    f"embedding provider failed for {self.name!r}: {exc}"
                ) from exc
        vector = [float(v) for v in embedding]

        try:
            with self._lock:
                stored = self._stored_dimension()
                if stored is not None and stored != len(vector):
                    raise SearchBackendError(
                        f"sqlite query dimension mismatch for {self.name!r}: "
                        f"index uses {stored}, query uses {len(vector)}"
                    )
                rows = self._conn.execute(
                    "SELECT id, doc_id, content, metadata, embedding "
                    "FROM chunks WHERE collection = ?",
                    (self.name,),
                ).fetchall()

            matches: list[tuple[float, str, str, str, dict[str, Any]]] = []
            for chunk_id, doc_id, content, raw_meta, blob in rows:
                meta = json.loads(raw_meta)
                if structured and not chunk_metadata_matches(structured, meta):
                    continue
                if not chunk_matches_workspace(meta, query.workspace_id):
                    continue
                score = (1.0 + _cosine(vector, _decode(blob))) / 2.0
                matches.append((score, chunk_id, doc_id, content, meta))

            matches.sort(key=lambda item: (-item[0], item[1]))
            total = len(matches)
            page = matches[offset : offset + n] if n else []
            out: list[Result] = []
            for rank, (score, chunk_id, doc_id, content, meta) in enumerate(page, start=1):
                chunk = Chunk(
                    id=chunk_id,
                    content=content,
                    doc_id=doc_id,
                    embedding=None,
                    metadata=meta,
                )
                out.append(Result(chunk=chunk, score=score, rank=rank))
            return out, total
        except SearchBackendError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise SearchBackendError(f"sqlite query failed for {self.name!r}: {exc}") from exc

    def query(self, query: Query) -> list[Result]:
        return self._query(query)[0]

    def query_with_total(self, query: Query) -> tuple[list[Result], int | None]:
        """Return the requested page and, when asked, the full match count."""
        results, total = self._query(query)
        return results, (total if query.include_total_count else None)

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            with self._lock, self._conn:
                for start in range(0, len(ids), 500):
                    batch = ids[start : start + 500]
                    placeholders = ",".join("?" for _ in batch)
                    self._conn.execute(
                        f"DELETE FROM chunks WHERE collection = ? AND id IN ({placeholders})",
                        (self.name, *batch),
                    )
                remaining = self._conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE collection = ?", (self.name,)
                ).fetchone()
                if remaining and int(remaining[0]) == 0:
                    self._conn.execute(
                        "DELETE FROM collection_dimensions WHERE collection = ?", (self.name,)
                    )
        except sqlite3.Error as exc:
            raise SearchBackendError(f"sqlite delete failed for {self.name!r}: {exc}") from exc

    def update(self, chunks: list[Chunk]) -> None:
        self.add(chunks)

    def list_collections(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT collection FROM chunks ORDER BY collection"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def snapshot(self, path: str) -> None:
        target = Path(path).expanduser()
        try:
            with self._lock:
                if target.suffix in (".db", ".sqlite", ".sqlite3"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    destination = target
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    destination = target / self._db_path.name
                # sqlite3.Connection.backup() takes a consistent snapshot while
                # other HTTP/MCP readers and writers share the live database.
                dest = sqlite3.connect(str(destination))
                try:
                    self._conn.backup(dest)
                finally:
                    dest.close()
        except (OSError, sqlite3.Error) as exc:
            raise SearchBackendError(f"sqlite snapshot failed for {self.name!r}: {exc}") from exc

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection = ?", (self.name,)
            ).fetchone()
        return int(row[0]) if row else 0

    def health(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()
