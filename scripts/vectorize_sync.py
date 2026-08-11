#!/usr/bin/env python3
"""Sync onboard notes from Supabase ``architecture_notes`` into Cloudflare Vectorize.

Runs on an operator machine or in CI — never inside the Cloudflare Container, which
only ever queries. Chunking goes through the same SegmentAwareChunker path production
retrieval assumes, so the index matches the pipeline that was validated.

``--dry-run`` still reads notes from Supabase and chunks them — that's the only way
to get an accurate count — but skips both the embedder and the Vectorize upsert, so
it costs no ONNX inference, no model download, and no network write. The reported
count is the number of vectors that *would* be upserted.

Apply::

    CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \\
    VECTORIZE_ACCOUNT_ID=… VECTORIZE_API_TOKEN=… \\
      python3 scripts/vectorize_sync.py --prefix clients/digithings --index digithings-docs
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from typing import Any, Protocol  # score:allow untyped any — Supabase rows are open dicts

from digisearch.core.models import Chunk, Document, Segment


class ModelMismatchError(RuntimeError):
    """Raised when an index already holds vectors from a different embedding model."""


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorSink(Protocol):
    def add(self, chunks: list[Chunk]) -> None: ...


class ChunkerProtocol(Protocol):
    def chunk(self, doc: Document) -> list[Chunk]: ...


def _vector_id(vault_path: str, chunk_index: int) -> str:
    """Deterministic id so a re-sync overwrites rather than duplicating."""
    digest = hashlib.sha1(vault_path.encode("utf-8")).hexdigest()[:24]
    return f"{digest}-{chunk_index:05d}"


def _segments_for(body: str) -> list[Segment]:
    from digisearch.ingestion.segmenters.heading import heading_segments

    return heading_segments(body)


def sync_corpus(
    notes: list[dict[str, Any]],
    chunker: ChunkerProtocol,
    embedder: Embedder | None,
    sink: VectorSink,
    *,
    model_id: str,
    embed: bool = True,
) -> int:
    """Chunk, optionally embed, and upsert every note. Returns the number of vectors sent.

    ``embed=False`` (what ``--dry-run`` uses) skips the embedder entirely — chunks are
    sent with ``embedding=None`` so a count-only preview costs no ONNX inference and
    no model download. ``embedder`` may be ``None`` only when ``embed=False``.
    """
    if embed and embedder is None:
        raise ValueError("embedder is required when embed=True")
    total = 0
    for note in notes:
        vault_path = str(note.get("vault_path") or "").strip()
        body = str(note.get("body_markdown") or "")
        if not vault_path or not body.strip():
            continue
        doc = Document(
            id=vault_path,
            content=body,
            source=f"vault://{vault_path}",
            doc_type="markdown",
            metadata={},
            segments=_segments_for(body),
        )
        chunks = chunker.chunk(doc)
        if not chunks:
            continue
        if embed:
            embeddings = embedder.embed([c.content for c in chunks])  # type: ignore[union-attr]
            pairs = zip(chunks, embeddings, strict=True)
        else:
            pairs = ((chunk, None) for chunk in chunks)
        prepared: list[Chunk] = []
        for index, (chunk, embedding) in enumerate(pairs):
            prepared.append(
                Chunk(
                    id=_vector_id(vault_path, index),
                    content=chunk.content,
                    doc_id=vault_path,
                    embedding=list(embedding) if embedding is not None else None,
                    metadata={
                        **dict(chunk.metadata),
                        "vault_path": vault_path,
                        "title": str(note.get("title") or ""),
                        "embedding_model": model_id,
                    },
                )
            )
        sink.add(prepared)
        total += len(prepared)
    return total


def assert_index_model(backend: Any, *, model_id: str, dimensions: int) -> None:
    """Refuse to upsert into an index whose existing vectors used a different model.

    A silent model mismatch does not error — it degrades retrieval, because the
    query vector and the stored vectors no longer share a space. Probing one
    existing vector is cheap insurance.
    """
    from digisearch.core.models import Query as DsQuery

    try:
        hits = backend.query(DsQuery(text="", top_k=1, embedding=[0.0] * dimensions))
    except Exception:  # broad on purpose: an unreachable or empty index must not block a first sync
        return
    for hit in hits:
        existing = str(getattr(hit.chunk, "metadata", {}).get("embedding_model") or "").strip()
        if existing and existing != model_id:
            raise ModelMismatchError(
                f"index already holds vectors from {existing!r}; refusing to upsert "
                f"{model_id!r}. Delete and recreate the index, or sync with the "
                "original model."
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix", required=True, help="vault_path prefix, e.g. clients/digithings"
    )
    parser.add_argument("--index", required=True, help="Vectorize index name, e.g. digithings-docs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read notes from Supabase, chunk, and report the vector count — skip "
            "embedding and the Vectorize upsert entirely."
        ),
    )
    args = parser.parse_args(argv)

    import os

    from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder
    from digisearch.indexes.backends.vectorize import VectorizeBackend
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
    from digivault.supabase_store import SupabaseStore

    notes = SupabaseStore.from_env().list_notes(path_prefix=args.prefix)
    print(f"{len(notes)} notes under {args.prefix!r}", file=sys.stderr)

    class _CountingSink:
        def __init__(self) -> None:
            self.count = 0

        def add(self, chunks: list[Chunk]) -> None:
            self.count += len(chunks)

    sink: VectorSink
    if args.dry_run:
        sink = _CountingSink()
    else:
        account_id = os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("VECTORIZE_API_TOKEN", "").strip()
        if not account_id or not api_token:
            raise SystemExit("VECTORIZE_ACCOUNT_ID and VECTORIZE_API_TOKEN are required")
        sink = VectorizeBackend(args.index, account_id=account_id, api_token=api_token)

    if not args.dry_run:
        assert_index_model(sink, model_id=MINILM_MODEL_ID, dimensions=384)

    total = sync_corpus(
        notes,
        SegmentAwareChunker(),
        None if args.dry_run else MiniLMEmbedder(),
        sink,
        model_id=MINILM_MODEL_ID,
        embed=not args.dry_run,
    )
    print(f"{'would upsert' if args.dry_run else 'upserted'} {total} vectors → {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
