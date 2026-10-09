"""Canonical filesystem ingest path: parse → sidecar → chunk → embed → index.

HTTP (``POST /ingest``), the Typer CLI, and tests all call :func:`ingest_source`
(or :func:`ingest_paths` for batches). Do not re-implement this sequence in
``server.py`` / ``cli.py``.

research flat payloads stay on :mod:`digisearch.research_ingest` (no segment
wrapper, stable research chunk ids) but share :func:`index_chunks` for the
final backend write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from digibase.art9 import screen_request
from pydantic import BaseModel, ConfigDict, Field

from digisearch.core.models import Chunk, Document
from digisearch.embedding.base import EmbeddingProvider
from digisearch.ingest_paths import resolve_ingest_source

logger = logging.getLogger(__name__)


class IngestResult(BaseModel):
    """Outcome of one successful filesystem ingest."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    chunks_created: int = Field(ge=0)
    index_name: str
    status: str = "ok"
    backend: str | None = None
    source: str | None = None


class IngestError(Exception):
    """Ingest failure with a stable code for HTTP / CLI mapping."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ingest_failed",
        http_status: int = 503,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


def _sidecar_path_for(file_path: Path) -> Path:
    yaml_path = file_path.parent / f"{file_path.stem}.yaml"
    if yaml_path.is_file():
        return yaml_path
    return file_path.parent / f"{file_path.stem}.yml"


def _resolve_path(source: str | Path, *, enforce_ingest_root: bool) -> Path:
    if enforce_ingest_root:
        try:
            return resolve_ingest_source(str(source))
        except ValueError as exc:
            raise IngestError(str(exc), code="ingest_source_rejected", http_status=400) from exc
    path = Path(source).expanduser()
    return path.resolve() if path.exists() else path


def apply_embeddings(
    chunks: list[Chunk],
    embedding_provider: EmbeddingProvider,
) -> None:
    """Embed chunks that lack vectors. Partial batches are refused."""

    if not chunks:
        return
    missing = [c for c in chunks if c.embedding is None]
    if not missing:
        return
    if len(missing) != len(chunks):
        raise IngestError(
            "partial embedding batch refused: supply embeddings for every chunk or for none",
            code="ingest_embed_partial",
            http_status=503,
        )
    vectors = embedding_provider.embed([c.content for c in chunks])
    if len(vectors) != len(chunks):
        raise IngestError(
            f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks",
            code="ingest_embed_mismatch",
            http_status=503,
        )
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = [float(v) for v in vector]


ART9_REFUSED_CODE = "art9_special_category"
ART9_REFUSED_STATUS = 422


def _screen_art9(index_name: str, chunks: list[Chunk]) -> None:
    """Refuse a batch whose chunks carry Art. 9 special-category data.

    Screening happens here, at the entry of :func:`index_chunks`, because that
    is the one seam every ingress path shares: filesystem ingest via
    :func:`ingest_source`, research, both trackers feeds and the SDK client all
    call :func:`index_chunks` for the backend write. Screening a request body
    instead would miss file ingest entirely, because ``IngestRequest.source`` is
    a *path*, and the bytes are only read from disk afterwards.

    The whole batch is screened in one call so a refusal costs one pass, not one
    pass per chunk. ``metadata`` is included as a mapping rather than as a string
    so that *field names* are screened as well as values: §5.5 coverage is by
    field name, and a chunk carrying a ``diagnosis`` key is refused even when its
    text is clean.

    ``id`` (a hash of doc id and chunk index) and ``embedding`` (a list of
    floats) are excluded: neither can carry a special category, and screening a
    float vector on every ingest would be pure cost.

    Fails closed. Only ``allow`` proceeds, so a decision added later than this
    leaf can only ever refuse more, never less. No exception reference is
    accepted here: this seam has no bypass, and a screening path with an off
    switch will be used as one.
    """

    if not chunks:
        return

    result = screen_request(
        [{"content": c.content, "doc_id": c.doc_id, "metadata": c.metadata} for c in chunks]
    )
    if result.decision == "allow":
        return

    # `reason` is an art9:<category>:<signal> label and never the matched value.
    raise IngestError(
        f"index {index_name!r} refused: chunks carry Art. 9 special-category data ({result.reason})",
        code=ART9_REFUSED_CODE,
        http_status=ART9_REFUSED_STATUS,
    )


def index_chunks(
    index_name: str,
    chunks: list[Chunk],
    *,
    embedding_provider: EmbeddingProvider | None = None,
    auto_embed: bool = True,
) -> str | None:
    """Refuse Art. 9 chunks, then optionally embed, then write via the router.

    The Art. 9 screen runs first, before a provider is resolved and before
    anything is embedded, so a refused chunk is never turned into a vector and
    never reaches a backend. Placement matters: with ``auto_embed=False`` there is
    no :func:`apply_embeddings` call at all and the backend embeds the chunk
    itself (``indexes/backends/vectorize.py``), so a screen placed at that call
    site would sit downstream of the embed it is meant to precede.

    When *embedding_provider* is omitted and *auto_embed* is True, resolves the
    configured EmbeddingCache → BatchEmbedder → EmbeddingProvider stack via
    :func:`digisearch.embedding.factory.resolve_embedding_pipeline`. Explicit
    embed config that cannot load raises :class:`IngestError` (no silent no-op).

    Propagates ``RuntimeError`` from :func:`route_add_chunks` unchanged so
    callers (research / client) keep their prior exception contract. Filesystem
    ingest wraps that error in :class:`IngestError` inside :func:`ingest_source`.
    An Art. 9 refusal is already an :class:`IngestError`, so
    :func:`ingest_source` re-raises it unchanged instead of reporting a backend
    outage.
    """

    _screen_art9(index_name, chunks)

    provider = embedding_provider
    if provider is None and auto_embed:
        from digisearch.embedding.factory import EmbeddingConfigError, resolve_embedding_pipeline

        try:
            provider = resolve_embedding_pipeline()
        except EmbeddingConfigError as exc:
            raise IngestError(
                str(exc),
                code="ingest_embed_config",
                http_status=503,
            ) from exc
    if provider is not None:
        apply_embeddings(chunks, provider)
    from digisearch.search._stub import route_add_chunks

    return route_add_chunks(index_name, chunks)


def ingest_source(
    source: str | Path,
    *,
    index_name: str = "default",
    metadata: Mapping[str, Any] | None = None,
    chunker_name: str | None = None,
    enforce_ingest_root: bool = False,
    embedding_provider: EmbeddingProvider | None = None,
) -> IngestResult:
    """Parse one file, chunk it, optionally embed, and index.

    Parameters
    ----------
    source:
        Filesystem path (relative or absolute). When *enforce_ingest_root* is
        True (HTTP), the path must stay under ``DIGISEARCH_INGEST_ROOT``.
    index_name:
        Target index / collection name.
    metadata:
        Extra document metadata merged after sidecar YAML (request body wins).
    chunker_name:
        Optional chunker key; otherwise per-index config / ``DIGISEARCH_CHUNKER``.
    enforce_ingest_root:
        Path containment for ``POST /ingest``. CLI leaves this False.
    embedding_provider:
        Optional embed hook before backend write. When omitted, the configured
        embed pipeline is resolved automatically (see
        :func:`digisearch.embedding.factory.resolve_embedding_pipeline`). Pass
        an explicit provider to override, or set ``DIGISEARCH_EMBED=0`` to skip
        pipeline-level embedding (backends may still embed).
    """
    try:
        from digisearch.chunking.factory import get_ingest_chunker
        from digisearch.core.config import DigiSearchConfig
        from digisearch.core.evidence_metadata import (
            load_sidecar_yaml,
            merge_document_metadata_into_chunks,
            metadata_from_sidecar_dict,
        )
        from digisearch.ingestion.registry import ParserRegistry

        path = _resolve_path(source, enforce_ingest_root=enforce_ingest_root)
        if not path.exists() or not path.is_file():
            raise IngestError(
                f"Source file not found: {source}",
                code="ingest_source_not_found",
                http_status=404,
            )

        registry = ParserRegistry()
        doc: Document = registry.parse(path)
        side_meta = metadata_from_sidecar_dict(load_sidecar_yaml(_sidecar_path_for(path)))
        merged: dict[str, Any] = {**(doc.metadata or {}), **side_meta}
        if metadata:
            merged = {**merged, **dict(metadata)}
        doc.metadata = merged

        index_cfg = DigiSearchConfig.from_env().get_index_config(index_name)
        chunker = get_ingest_chunker(chunker_name, index_config=index_cfg)
        chunks = chunker.chunk(doc)
        merge_document_metadata_into_chunks(doc, chunks)
        doc.chunks = chunks

        try:
            backend = index_chunks(
                index_name,
                chunks,
                embedding_provider=embedding_provider,
            )
        except RuntimeError as exc:
            raise IngestError(
                str(exc),
                code="ingest_backend_unavailable",
                http_status=503,
            ) from exc
    except IngestError:
        raise
    except ImportError as exc:
        logger.error("Ingestion dependencies not installed: %s", exc)
        raise IngestError(
            f"Ingestion backend unavailable (missing dependency: {exc}). "
            "Install digisearch[ingestion].",
            code="ingest_dependency_missing",
            http_status=503,
        ) from exc
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        logger.error("Ingestion failed for source '%s': %s", source, exc)
        raise IngestError(
            f"Ingestion failed: {exc}",
            code="ingest_failed",
            http_status=503,
        ) from exc

    return IngestResult(
        doc_id=doc.id,
        chunks_created=len(chunks),
        index_name=index_name,
        backend=backend,
        source=str(path),
    )


def ingest_paths(
    paths: list[Path],
    *,
    index_name: str = "default",
    chunker_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    skip_errors: bool = True,
) -> tuple[int, list[IngestResult]]:
    """Ingest every supported file under *paths*.

    When *skip_errors* is True (CLI default), failures are logged and skipped.
    Returns ``(total_chunks, successful_results)``.
    """
    from digisearch.ingestion.registry import ParserRegistry

    registry = ParserRegistry()
    results: list[IngestResult] = []
    total = 0
    for path in paths:
        if not path.is_file() or not registry.get_parser(str(path)):
            continue
        try:
            result = ingest_source(
                path,
                index_name=index_name,
                metadata=metadata,
                chunker_name=chunker_name,
                enforce_ingest_root=False,
                embedding_provider=embedding_provider,
            )
        except IngestError as exc:
            if not skip_errors:
                raise
            logger.warning("Skip %s: %s", path, exc.message)
            continue
        results.append(result)
        total += result.chunks_created
    return total, results


__all__ = [
    "IngestError",
    "IngestResult",
    "apply_embeddings",
    "index_chunks",
    "ingest_paths",
    "ingest_source",
]
