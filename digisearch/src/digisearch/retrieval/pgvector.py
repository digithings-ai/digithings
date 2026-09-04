"""pgvector-backed :class:`~digisearch.retrieval.backend.RetrievalBackend`.

Default retrieval backend (#402). Uses the existing Postgres instance when
``DIGISEARCH_DATABASE_URL`` (or ``DIGISEARCH_PGVECTOR_URL``) is set and the
``vector`` extension is available. Unit tests inject an in-memory store so no
database is required.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from digisearch.core.models import Document
from digisearch.retrieval.backend import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "digisearch_retrieval"
DEFAULT_DIMENSIONS = 384
DSN_ENV_VARS = ("DIGISEARCH_PGVECTOR_URL", "DIGISEARCH_DATABASE_URL")


def resolve_pgvector_dsn(explicit: str | None = None) -> str | None:
    """Return the Postgres DSN from *explicit* or the first set env var."""
    if explicit and explicit.strip():
        return explicit.strip()
    for key in DSN_ENV_VARS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _StoredRow:
    document_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    doc_type: str = ""


class VectorStore(Protocol):
    """Persistence seam for :class:`PgvectorBackend` (real Postgres or memory)."""

    async def ensure_schema(self, dimensions: int) -> None: ...

    async def upsert(self, rows: list[_StoredRow]) -> None: ...

    async def search(
        self, embedding: list[float], top_k: int
    ) -> list[tuple[_StoredRow, float]]: ...

    async def delete(self, document_ids: list[str]) -> None: ...

    async def ping(self) -> bool: ...


class InMemoryVectorStore:
    """Process-local store used by unit tests and DSN-less smoke paths."""

    def __init__(self) -> None:
        self._rows: dict[str, _StoredRow] = {}
        self._ready = False

    async def ensure_schema(self, dimensions: int) -> None:
        del dimensions  # in-memory has no fixed schema
        self._ready = True

    async def upsert(self, rows: list[_StoredRow]) -> None:
        for row in rows:
            self._rows[row.document_id] = row

    async def search(self, embedding: list[float], top_k: int) -> list[tuple[_StoredRow, float]]:
        scored = [
            (row, _cosine_similarity(embedding, row.embedding)) for row in self._rows.values()
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(0, top_k)]

    async def delete(self, document_ids: list[str]) -> None:
        for doc_id in document_ids:
            self._rows.pop(doc_id, None)

    async def ping(self) -> bool:
        return self._ready


class PsycopgVectorStore:
    """Postgres + pgvector store via optional ``psycopg`` (async)."""

    def __init__(self, dsn: str, *, table: str = DEFAULT_TABLE) -> None:
        self._dsn = dsn
        self._table = table
        self._dimensions: int | None = None

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise ImportError(
                "Install digisearch[pgvector] (psycopg) for Postgres retrieval"
            ) from exc
        return psycopg.AsyncConnection.connect(self._dsn)

    async def ensure_schema(self, dimensions: int) -> None:
        self._dimensions = dimensions
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        document_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({dimensions}) NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        source TEXT NOT NULL DEFAULT '',
                        doc_type TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
            await conn.commit()

    async def upsert(self, rows: list[_StoredRow]) -> None:
        if not rows:
            return
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                for row in rows:
                    await cur.execute(
                        f"""
                        INSERT INTO {self._table}
                            (document_id, content, embedding, metadata, source, doc_type)
                        VALUES (%s, %s, %s::vector, %s::jsonb, %s, %s)
                        ON CONFLICT (document_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            source = EXCLUDED.source,
                            doc_type = EXCLUDED.doc_type
                        """,
                        (
                            row.document_id,
                            row.content,
                            _vector_literal(row.embedding),
                            json.dumps(row.metadata),
                            row.source,
                            row.doc_type,
                        ),
                    )
            await conn.commit()

    async def search(self, embedding: list[float], top_k: int) -> list[tuple[_StoredRow, float]]:
        lit = _vector_literal(embedding)
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT document_id, content, embedding::text, metadata, source, doc_type,
                           1 - (embedding <=> %s::vector) AS score
                    FROM {self._table}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (lit, lit, top_k),
                )
                fetched = await cur.fetchall()
        out: list[tuple[_StoredRow, float]] = []
        for doc_id, content, emb_text, metadata, source, doc_type, score in fetched:
            meta = metadata if isinstance(metadata, dict) else json.loads(metadata or "{}")
            out.append(
                (
                    _StoredRow(
                        document_id=str(doc_id),
                        content=str(content),
                        embedding=_parse_vector_text(str(emb_text)),
                        metadata=meta,
                        source=str(source or ""),
                        doc_type=str(doc_type or ""),
                    ),
                    float(score),
                )
            )
        return out

    async def delete(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"DELETE FROM {self._table} WHERE document_id = ANY(%s)",
                    (list(document_ids),),
                )
            await conn.commit()

    async def ping(self) -> bool:
        try:
            async with await self._connect() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()
            return True
        except Exception:
            logger.exception("pgvector health check failed")
            return False


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def _parse_vector_text(text: str) -> list[float]:
    cleaned = text.strip().lstrip("[").rstrip("]")
    if not cleaned:
        return []
    return [float(part) for part in cleaned.split(",")]


def _embed_texts(embedder: Any, texts: list[str]) -> list[list[float]]:
    vectors = embedder.embed(texts)
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"embedding provider returned {len(vectors)} vectors for {len(texts)} texts"
        )
    return [[float(x) for x in vec] for vec in vectors]


class PgvectorBackend:
    """Default :class:`~digisearch.retrieval.backend.RetrievalBackend`.

    Parameters
    ----------
    dsn:
        Postgres URL. When omitted, reads ``DIGISEARCH_PGVECTOR_URL`` /
        ``DIGISEARCH_DATABASE_URL``. When still unset, uses an in-memory store
        (tests / local smoke only — not for production).
    store:
        Optional pre-built :class:`VectorStore` (tests inject fakes).
    embedder:
        Object with ``embed(texts) -> list[list[float]]`` and ``dimensions``.
        Defaults to :class:`~digisearch.embedding.providers.minilm.MiniLMEmbedder`.
    table:
        Postgres table name (real store only).
    """

    name = "pgvector"

    def __init__(
        self,
        dsn: str | None = None,
        *,
        store: VectorStore | None = None,
        embedder: Any | None = None,
        table: str = DEFAULT_TABLE,
        allow_memory: bool = True,
    ) -> None:
        resolved = resolve_pgvector_dsn(dsn)
        if store is not None:
            self._store: VectorStore = store
        elif resolved:
            self._store = PsycopgVectorStore(resolved, table=table)
        elif allow_memory:
            logger.warning(
                "PgvectorBackend using in-memory store — set DIGISEARCH_DATABASE_URL "
                "for Postgres + pgvector"
            )
            self._store = InMemoryVectorStore()
        else:
            raise ValueError(
                "PgvectorBackend requires DIGISEARCH_DATABASE_URL / "
                "DIGISEARCH_PGVECTOR_URL when allow_memory=False"
            )
        if embedder is None:
            from digisearch.embedding.providers.minilm import get_default_minilm_embedder

            embedder = get_default_minilm_embedder()
        self._embedder = embedder
        self._schema_ready = False

    @property
    def dimensions(self) -> int:
        dims = getattr(self._embedder, "dimensions", None)
        if isinstance(dims, int) and dims > 0:
            return dims
        return DEFAULT_DIMENSIONS

    async def _ensure_ready(self) -> None:
        if self._schema_ready:
            return
        await self._store.ensure_schema(self.dimensions)
        self._schema_ready = True

    async def index(self, documents: list[Document]) -> None:
        await self._ensure_ready()
        if not documents:
            return
        texts = [doc.content for doc in documents]
        vectors = _embed_texts(self._embedder, texts)
        rows = [
            _StoredRow(
                document_id=doc.id,
                content=doc.content,
                embedding=vec,
                metadata=dict(doc.metadata),
                source=doc.source,
                doc_type=doc.doc_type,
            )
            for doc, vec in zip(documents, vectors, strict=True)
        ]
        await self._store.upsert(rows)

    async def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        await self._ensure_ready()
        if top_k <= 0:
            return []
        query_vec = _embed_texts(self._embedder, [query])[0]
        hits = await self._store.search(query_vec, top_k)
        return [
            RetrievalResult(
                document_id=row.document_id,
                content=row.content,
                score=score,
                metadata=dict(row.metadata),
                source=row.source,
            )
            for row, score in hits
        ]

    async def delete(self, document_ids: list[str]) -> None:
        await self._ensure_ready()
        await self._store.delete(document_ids)

    async def health(self) -> bool:
        try:
            await self._ensure_ready()
        except Exception:
            logger.exception("PgvectorBackend schema ensure failed")
            return False
        return await self._store.ping()


def postgres_env_from_dsn(dsn: str) -> dict[str, str]:
    """Map a SQLAlchemy/psycopg URL onto LightRAG ``POSTGRES_*`` env vars."""
    parsed = urlparse(dsn)
    return {
        "POSTGRES_HOST": parsed.hostname or "127.0.0.1",
        "POSTGRES_PORT": str(parsed.port or 5432),
        "POSTGRES_USER": parsed.username or "postgres",
        "POSTGRES_PASSWORD": parsed.password or "",
        "POSTGRES_DATABASE": (parsed.path or "/postgres").lstrip("/") or "postgres",
    }
