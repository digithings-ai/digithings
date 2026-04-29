"""Atlas research-document ingest helper for DigiSearch.

Bridges the Atlas pipeline's ``documents`` table (PR #441) into DigiSearch's
vector store so finalized research notes are queryable from the
``search_strategies`` MCP tool. Two layers of API:

- :func:`ingest_atlas_payload` — pure: takes a pre-fetched ``documents`` row
  dict, parses + chunks it, stamps Atlas metadata, and upserts into the
  configured DigiSearch index. Tests use this directly.
- :func:`ingest_atlas_document` — Supabase-aware: pulls one row by
  ``(date, document_key)`` and forwards to the pure helper.

The helpers are deliberately **pull-based**: the caller decides when to
re-index. Real-time eventing (Atlas publish → DigiSearch reindex) waits on
DigiStore (#57) — see PR body for the punt rationale.

Idempotency: chunk IDs are deterministic in
``(document_key, date_str, chunk_index)``. Re-ingesting the same row replaces
the prior chunks rather than appending duplicates. This is the contract every
test asserts.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import date as DateType
from typing import Any, Mapping, Protocol

from digisearch.core.evidence_metadata import (
    merge_document_metadata_into_chunks,
    normalize_metadata_for_chroma,
)
from digisearch.core.models import Document
from digisearch.ingestion.chunkers.recursive import RecursiveChunker
from digisearch.search._stub import _stub_index, add_chunks

logger = logging.getLogger(__name__)


#: Default index name for Atlas research documents. Override with
#: ``DIGISEARCH_ATLAS_INDEX``.
ATLAS_INDEX_NAME: str = os.environ.get("DIGISEARCH_ATLAS_INDEX", "atlas")

#: Atlas chunk metadata fields that are filterable from the MCP tool.
ATLAS_FILTERABLE_FIELDS: frozenset[str] = frozenset(
    {
        "date",  # ISO YYYY-MM-DD string (eq match)
        "date_ordinal",  # int YYYYMMDD (range match — gt/ge/lt/le)
        "doc_type",
        "segment",
        "sector",
        "run_type",
        "category",
        "asset_class",
        "document_key",
    }
)


class _AtlasRowSource(Protocol):
    """Minimal Supabase surface used by :func:`ingest_atlas_document`.

    Mirrors :class:`apps.digiquant.atlas.supabase_io.SupabaseClient` without
    importing it — DigiSearch must not depend on the Atlas package. Production
    callers pass the same live client they pass to ``publish_document``.
    """

    def table(self, name: str) -> Any: ...  # noqa: D401, E704


@dataclass(frozen=True)
class IndexedDocument:
    """Result of ingesting one Atlas document into DigiSearch."""

    document_key: str
    date: str
    doc_id: str
    chunks_created: int
    index_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _ordinal_from_iso_date(value: str | DateType | None) -> int | None:
    """Convert ``YYYY-MM-DD`` (str or date) to ``YYYYMMDD`` int for range filters.

    Returns ``None`` for non-ISO inputs so downstream filters silently skip the
    field rather than raising — matches the existing
    :func:`digisearch.core.filter_apply.chunk_metadata_matches` philosophy of
    treating unparseable values as non-matches.
    """
    if value is None:
        return None
    if isinstance(value, DateType):
        return value.year * 10000 + value.month * 100 + value.day
    s = str(value).strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        return int(s[:4]) * 10000 + int(s[5:7]) * 100 + int(s[8:10])
    except ValueError:
        return None


def _content_from_row(row: Mapping[str, Any]) -> str:
    """Extract searchable text from an Atlas ``documents`` row.

    Prefers the ``content`` (markdown) column when populated; falls back to a
    canonicalized JSON dump of ``payload`` so chunk content stays stable across
    runs (sorted keys → identical text → embedding-cache hits on re-ingest).
    """
    content = row.get("content")
    if isinstance(content, str) and content.strip():
        return content
    payload = row.get("payload")
    if payload is None:
        return ""
    try:
        return json.dumps(payload, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(payload)


def _extract_atlas_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build the chunk-metadata dict from an Atlas row.

    Captures every field listed in :data:`ATLAS_FILTERABLE_FIELDS` plus a few
    useful lineage keys (``title``, ``source``). Drops ``None`` values so the
    Chroma serializer doesn't store empty cells.
    """
    date_value = row.get("date")
    date_iso = str(date_value)[:10] if date_value is not None else ""
    payload = row.get("payload")
    asset_class = payload.get("asset_class") if isinstance(payload, Mapping) else None

    raw: dict[str, Any] = {
        "source": "atlas",
        "date": date_iso or None,
        "date_ordinal": _ordinal_from_iso_date(date_value),
        "doc_type": row.get("doc_type"),
        "segment": row.get("segment"),
        "sector": row.get("sector"),
        "run_type": row.get("run_type"),
        "category": row.get("category"),
        "document_key": row.get("document_key"),
        "title": row.get("title"),
        "asset_class": asset_class,
    }
    return {k: v for k, v in raw.items() if v is not None and v != ""}


def _stable_doc_id(row: Mapping[str, Any]) -> str:
    """Deterministic ``Document.id`` from ``(date, document_key)``.

    Same row replayed → same id → :func:`ingest_atlas_payload` rewrites the
    same chunk slot rather than duplicating. UUID5 with the ``URL`` namespace
    keeps ids opaque while remaining deterministic.
    """
    date_iso = str(row.get("date") or "")[:10]
    document_key = str(row.get("document_key") or "")
    seed = f"atlas::{date_iso}::{document_key}"
    return f"atlas-{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


def _drop_existing_chunks(index_name: str, doc_id: str) -> int:
    """Remove any prior chunks for ``doc_id`` from the in-memory stub index.

    Returns the count removed. Real backends (Chroma, Azure) handle upsert via
    matching ids, but the stub append-only list needs a manual sweep. Lives
    here rather than in ``_stub.py`` because re-indexing semantics are an
    Atlas-ingest concern, not a generic search concern.
    """
    chunks = _stub_index.get(index_name)
    if not chunks:
        return 0
    keep = [c for c in chunks if c.doc_id != doc_id]
    removed = len(chunks) - len(keep)
    if removed:
        _stub_index[index_name] = keep
    return removed


def ingest_atlas_payload(
    row: Mapping[str, Any],
    *,
    index_name: str | None = None,
    chunker: RecursiveChunker | None = None,
) -> IndexedDocument:
    """Index one Atlas ``documents`` row into DigiSearch (pure function).

    Parameters
    ----------
    row:
        A pre-fetched ``documents`` row mapping with at minimum ``date`` and
        ``document_key``. ``content``, ``payload``, ``doc_type``, ``segment``,
        ``sector``, ``run_type``, ``category``, and ``title`` are honored when
        present.
    index_name:
        DigiSearch index to write into. Defaults to
        :data:`ATLAS_INDEX_NAME` (``"atlas"`` unless the
        ``DIGISEARCH_ATLAS_INDEX`` env override is set).
    chunker:
        Optional chunker override for tests. Defaults to the same
        ``RecursiveChunker(512, 64)`` used by ``POST /ingest``.

    Returns
    -------
    IndexedDocument
        Counts and identifiers — useful for audit logging and the e2e tests.

    Raises
    ------
    ValueError
        When ``date`` or ``document_key`` is missing from ``row`` (the natural
        key for the upsert).
    """
    start = time.perf_counter()
    date_value = row.get("date")
    document_key = row.get("document_key")
    if not date_value or not document_key:
        raise ValueError("Atlas row requires non-empty 'date' and 'document_key'")

    date_iso = str(date_value)[:10]
    target_index = (index_name or ATLAS_INDEX_NAME).strip() or ATLAS_INDEX_NAME
    used_chunker = chunker or RecursiveChunker(chunk_size=512, chunk_overlap=64)

    doc_id = _stable_doc_id(row)
    metadata = _extract_atlas_metadata(row)
    content = _content_from_row(row)

    doc = Document(
        id=doc_id,
        content=content,
        source=f"supabase://documents/{date_value}/{document_key}",
        doc_type=str(row.get("doc_type") or "atlas_research"),
        metadata=dict(metadata),
        chunks=[],
    )

    chunks = used_chunker.chunk(doc)
    # Stable chunk IDs: same input → same ids → upsert by replacement.
    for idx, chunk in enumerate(chunks):
        chunk.id = f"atlas::{document_key}::{date_iso}::{idx}"
        chunk.doc_id = doc_id
    merge_document_metadata_into_chunks(doc, chunks)
    # ``merge_document_metadata_into_chunks`` already passes through
    # ``normalize_metadata_for_chroma``, but we run it again as a belt-and-
    # braces pass in case a custom chunker bypassed the merge call.
    for chunk in chunks:
        chunk.metadata = normalize_metadata_for_chroma(chunk.metadata)

    removed = _drop_existing_chunks(target_index, doc_id)
    add_chunks(target_index, chunks)

    logger.info(
        "atlas_ingest done",
        extra={
            "operation": "ingest_atlas_payload",
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "outcome": "ok",
            "doc_id": doc_id,
            "document_key": document_key,
            "date": date_iso,
            "chunk_count": len(chunks),
            "chunks_replaced": removed,
            "index_name": target_index,
        },
    )

    return IndexedDocument(
        document_key=str(document_key),
        date=date_iso,
        doc_id=doc_id,
        chunks_created=len(chunks),
        index_name=target_index,
        metadata=dict(metadata),
    )


def fetch_atlas_row(
    client: _AtlasRowSource, date: str | DateType, document_key: str
) -> Mapping[str, Any] | None:
    """Pull one ``documents`` row by ``(date, document_key)``.

    Mirrors the Supabase access pattern in
    ``digiquant.atlas.supabase_io.load_prior_context`` — single ``.eq().eq()``
    filter, single-row select. Returns ``None`` when the row is absent so the
    caller can no-op rather than raise (publish failures + late triggers
    should not crash the indexer).
    """
    date_str = date.isoformat() if isinstance(date, DateType) else str(date)[:10]
    resp = (
        client.table("documents")
        .select(
            "date, document_key, doc_type, segment, sector, run_type, category, title, payload, content"
        )
        .eq("date", date_str)
        .eq("document_key", document_key)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    return rows[0]


def ingest_atlas_document(
    client: _AtlasRowSource,
    date: str | DateType,
    document_key: str,
    *,
    index_name: str | None = None,
) -> IndexedDocument | None:
    """Fetch + index one Atlas document by ``(date, document_key)``.

    Returns ``None`` if the row is missing (no chunks indexed). The natural
    way to call this is from a polling worker or directly from Atlas's
    ``publish_phase`` once #57 lands a queue.
    """
    row = fetch_atlas_row(client, date, document_key)
    if row is None:
        logger.warning(
            "atlas_ingest skipped — row not found",
            extra={
                "operation": "ingest_atlas_document",
                "outcome": "skipped",
                "document_key": document_key,
                "date": str(date)[:10],
            },
        )
        return None
    return ingest_atlas_payload(row, index_name=index_name)


__all__ = [
    "ATLAS_INDEX_NAME",
    "ATLAS_FILTERABLE_FIELDS",
    "IndexedDocument",
    "fetch_atlas_row",
    "ingest_atlas_document",
    "ingest_atlas_payload",
]
