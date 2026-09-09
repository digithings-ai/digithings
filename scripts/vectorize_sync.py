#!/usr/bin/env python3
"""Sync notes from Cloudflare D1 into Cloudflare Vectorize.

Runs on an operator machine or in CI — never inside the Cloudflare Container, which
only ever queries. Chunking goes through the same SegmentAwareChunker path production
retrieval assumes, so the index matches the pipeline that was validated.

``--database`` MUST be the same D1 database ``scripts/d1_sync.py`` published
``--prefix`` into — digisearch's Vectorize hits carry a ``vault_path``, and
``digivault_get_note`` resolves that path against D1, not Vectorize. Point this at a
different database than digivault serves the same prefix from and every hit the
model tries to load 404s: the vectors and the notes have to describe the same corpus.

``--dry-run`` still reads notes from D1 and chunks them — that's the only way to get
an accurate count — but skips both the embedder and the Vectorize upsert, so it costs
no ONNX inference, no model download, and no network write. The reported count is
the number of vectors that *would* be upserted.

``--index`` is NOT a free choice: it must equal the ``DIGISEARCH_INDEX`` /
``DIGI_TENANT_CORPUS_MAP`` entry the digisearch server for that tenant is
configured with (see ``frontend/digithings-stack-cloudflare/wrangler.toml``),
because ``_vectorize_backend`` passes ``index_name`` straight into the Vectorize
URL with no translation -- a mismatched name means every chat query 404s against
an index that was never populated. Today those values are underscore-form
(``digithings_docs``, ``occ_help``), matching this script's examples below.

Cloudflare's docs give *advisory* naming guidance -- get-started/intro
(https://developers.cloudflare.com/vectorize/get-started/intro/) states in
prose that "a good index name is: a combination of lowercase and/or numeric
ASCII characters, shorter than 32 characters, starts with a letter, and uses
dashes (-) instead of spaces" -- but no enforced charset or regex is
published, and there is a real 64-byte length cap that both ``digithings_docs``
and ``occ_help`` clear. This is not a claim that underscores are documented as
supported, and it is not a claim the docs are silent on the matter -- both
would be false. Verified empirically against the live account on
2026-08-11: ``npx wrangler vectorize create digithings_docs --dimensions=384
--metric=cosine`` and the same call for ``occ_help`` both succeeded, and
``npx wrangler vectorize list`` shows both indexes at 384 dimensions, cosine
metric. Underscore index names are accepted, so no rename of
``DIGISEARCH_INDEX``, the corpus map, or the Chroma collection names in
``seed_chroma.sh`` is needed -- ``digithings_docs`` / ``occ_help`` are the
single canonical name on both sides of the pairing.

Apply::

    CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… \\
      python3 scripts/vectorize_sync.py --prefix clients/digithings --index digithings_docs \\
        --database <d1-database-id>

One Cloudflare account + token now covers both the D1 read and the Vectorize write
(#2239 credential rename) -- ``CLOUDFLARE_ACCOUNT_ID``/``CLOUDFLARE_API_TOKEN`` are
canonical; the legacy ``D1_ACCOUNT_ID``/``D1_API_TOKEN``/``VECTORIZE_ACCOUNT_ID``/
``VECTORIZE_API_TOKEN`` names still work as a fallback (see ``_first_env`` below).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any, Protocol  # score:allow untyped any — Vectorize backend duck-typed

from digisearch.core.models import Chunk, Document, Segment
from digivault.models import NoteRow

logger = logging.getLogger(__name__)

#: Matches VectorizeBackend.DEFAULT_BATCH_SIZE (see the import in ``main`` below);
#: used as ``sync_corpus``'s default so a direct call (e.g. from a test) still
#: batches sanely without importing the Vectorize backend module.
_DEFAULT_SYNC_BATCH_SIZE = 1000


class ModelMismatchError(RuntimeError):
    """Raised when an index already holds vectors from a different embedding model."""


def _mutation_capturing_post(
    inner_post: Any,
    mutation_ids: list[str],
) -> Any:
    """Wrap Vectorize HTTP posts to collect upsert mutation ids (#2236)."""

    def post(url: str, headers: dict[str, str], body: bytes, content_type: str) -> tuple[int, str]:
        status, text = inner_post(url, headers, body, content_type)
        if status == 200 and "/upsert" in url:
            try:
                payload = json.loads(text)
                mutation_id = (payload.get("result") or {}).get("mutationId")
                if mutation_id:
                    mutation_ids.append(str(mutation_id))
            except json.JSONDecodeError:
                pass
        return status, text

    return post


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


#: Frontmatter keys worth carrying onto every chunk's metadata. Deliberately not a
#: blind splat of the whole frontmatter dict, because Vectorize caps metadata at
#: 10 KiB per vector: everything here earns its place at retrieval
#: or citation time --
#:   segment_label / segment_index -- page/heading identity for a note that is
#:     itself already one PDF page or section (the OCC child-note shape this
#:     fixes). heading_segments() can't derive these from a headerless body, so
#:     without this the label silently comes back None even though page
#:     identity still survives in vault_path.
#:   parent_doc     -- links a page-level chunk back to its multi-page source.
#:   source_url     -- the original document URL, for citation-building.
#:   page_class     -- retrieval-time filtering by page type (e.g. TOC vs body).
#: Explicitly excluded: ingested_at, status, tags, content_type, client, and
#: frontmatter's own title -- none of them help a query or a citation, and the
#: canonical `title` stamp below already covers the title case.
_FRONTMATTER_METADATA_KEYS = (
    "segment_label",
    "segment_index",
    "parent_doc",
    "source_url",
    "page_class",
)


def _frontmatter_fields(frontmatter: Any) -> dict[str, Any]:
    """Select the retrieval-relevant frontmatter fields to carry onto every chunk.

    ``frontmatter`` may be ``None`` or a non-dict (a malformed jsonb column, or a
    caller that bypasses ``NoteRow``'s own null-coercion validator) -- treated the
    same as "no frontmatter" rather than raising. A key is only included when
    actually present, so a falsy-but-meaningful value (``segment_index: 0``) is
    still carried, and callers never see an inserted ``None``.
    """
    if not isinstance(frontmatter, dict):
        return {}
    return {key: frontmatter[key] for key in _FRONTMATTER_METADATA_KEYS if key in frontmatter}


def sync_corpus(
    notes: list[NoteRow],
    chunker: ChunkerProtocol,
    embedder: Embedder | None,
    sink: VectorSink,
    *,
    model_id: str,
    embed: bool = True,
    batch_size: int = _DEFAULT_SYNC_BATCH_SIZE,
) -> int:
    """Chunk, optionally embed, and upsert every note. Returns the number of vectors sent.

    Chunks are accumulated across notes into one buffer and only flushed to
    ``sink.add()`` once the buffer reaches ``batch_size`` (plus a final flush for
    whatever remains) — a note yields 1-10 chunks, so calling ``sink.add()`` once
    per note (as a naive per-note loop would) turns a run over ~1,279 notes into
    ~1,279 HTTP POSTs against Vectorize, which rate-limits at 1,200 requests / 5
    minutes per user. Batching keeps a full sync at roughly one request per
    ``batch_size`` vectors instead.

    ``embed=False`` (what ``--dry-run`` uses) skips the embedder entirely — chunks are
    sent with ``embedding=None`` so a count-only preview costs no ONNX inference and
    no model download. ``embedder`` may be ``None`` only when ``embed=False``.
    """
    if embed and embedder is None:
        raise ValueError("embedder is required when embed=True")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    total = 0
    buffer: list[Chunk] = []
    for note in notes:
        vault_path = note.vault_path.strip()
        body = note.body_markdown
        if not vault_path or not body.strip():
            continue
        frontmatter_fields = _frontmatter_fields(note.frontmatter)
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
        for index, (chunk, embedding) in enumerate(pairs):
            buffer.append(
                Chunk(
                    id=_vector_id(vault_path, index),
                    content=chunk.content,
                    doc_id=vault_path,
                    embedding=list(embedding) if embedding is not None else None,
                    metadata={
                        # Precedence, weakest to strongest:
                        # 1. note-level frontmatter fields (segment_label etc.) --
                        #    the only source of page/heading identity for a note
                        #    with no headings of its own.
                        # 2. the chunk's own metadata from the chunker. When the
                        #    body DOES have headings, SegmentAwareChunker's
                        #    segment_label ("heading:...") is strictly more
                        #    specific than the note-level one and must win --
                        #    RecursiveChunker's fallback path never sets
                        #    segment_label at all, so frontmatter's value survives
                        #    untouched in that case.
                        # 3. sync-controlled canonical stamps -- vault_path/title/
                        #    embedding_model are never overridable by a note's own
                        #    frontmatter, mirroring VectorizeBackend.add's doc_id/
                        #    content guard against caller-supplied metadata.
                        **frontmatter_fields,
                        **dict(chunk.metadata),
                        "vault_path": vault_path,
                        "title": note.title or "",
                        "embedding_model": model_id,
                    },
                )
            )
        total += len(chunks)
        while len(buffer) >= batch_size:
            sink.add(buffer[:batch_size])
            buffer = buffer[batch_size:]
    if buffer:
        sink.add(buffer)
    return total


def _unit_probe_vector(dimensions: int) -> list[float]:
    """A valid non-zero unit vector for probing a cosine index.

    Cosine similarity against an all-zero vector is undefined, and Cloudflare
    may reject a zero-vector query outright on a cosine index -- which would
    make this probe, and therefore the model-mismatch guard, never fire for
    anyone. ``e_0`` (a 1 in the first position, zeros elsewhere) has magnitude
    1 and is cheap to build for any dimension.
    """
    vector = [0.0] * dimensions
    if dimensions > 0:
        vector[0] = 1.0
    return vector


#: Matches a Vectorize failure message's leading `(<status>)`, e.g.
#: "vectorize query failed (404): ...". Used to tell "index not found" (a
#: brand-new index -- fine, proceed) apart from every other probe failure.
_STATUS_CODE_RE = re.compile(r"\((\d{3})\)")


def assert_index_model(backend: Any, *, model_id: str, dimensions: int) -> None:
    """Refuse to upsert into an index whose existing vectors used a different model.

    A silent model mismatch does not error — it degrades retrieval, because the
    query vector and the stored vectors no longer share a space. Probing one
    existing vector is cheap insurance.

    A probe failure because the index is empty or does not exist yet is expected
    on a first sync and must not block it. Any *other* probe failure (auth,
    network, a malformed response) is surfaced as a warning instead of being
    silently swallowed — a guard that never runs should be visible as such, not
    indistinguishable from a guard that ran and found no mismatch.
    """
    from digisearch.core.models import Query as DsQuery

    try:
        hits = backend.query(DsQuery(text="", top_k=1, embedding=_unit_probe_vector(dimensions)))
    except Exception as exc:  # classified below -- not a blind swallow
        message = str(exc)
        status_match = _STATUS_CODE_RE.search(message)
        status = int(status_match.group(1)) if status_match else None
        if status == 404 or "not found" in message.lower():
            # A brand-new index has no existing vectors to probe -- that must
            # not block a first sync.
            return
        logger.warning(
            "vectorize model-mismatch probe failed; proceeding without the guard: %s",
            message,
        )
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
    parser.add_argument(
        "--index",
        required=True,
        help=(
            "Vectorize index name -- MUST equal the target tenant's DIGISEARCH_INDEX / "
            "DIGI_TENANT_CORPUS_MAP value (see frontend/digithings-stack-cloudflare/"
            "wrangler.toml), e.g. digithings_docs or occ_help. A name that doesn't "
            "match means digisearch queries a different index than this synced."
        ),
    )
    parser.add_argument(
        "--database",
        required=True,
        help=(
            "D1 database id holding this corpus' notes — the same id d1_sync.py wrote "
            "to for --prefix. Vectors are derived from D1, so a mismatch silently "
            "embeds a different corpus than digivault serves."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read notes from D1, chunk, and report the vector count — skip "
            "embedding and the Vectorize upsert entirely."
        ),
    )
    args = parser.parse_args(argv)

    from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder
    from digisearch.indexes.backends.vectorize import DEFAULT_BATCH_SIZE, VectorizeBackend
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
    from digivault.d1_errors import D1StoreError
    from digivault.d1_store import D1Store
    from digivault.supabase_store import _first_env

    # Canonical-first, legacy-fallback (#2239 credential rename): D1 and Vectorize
    # now share one Cloudflare account + token, so this single resolution feeds both
    # the D1 read below and the Vectorize sink further down -- CLOUDFLARE_ACCOUNT_ID/
    # CLOUDFLARE_API_TOKEN first, then the legacy VECTORIZE_*/D1_* names, whichever
    # the operator still has set.
    account_id = _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    api_token = _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    if not account_id or not api_token:
        # Checked before the D1 read below, not only before the Vectorize write
        # further down: D1 is read on every invocation, `--dry-run` included, so
        # without this an entirely-unset credential pair still reached Cloudflare as
        # an unauthenticated request, came back 401, and -- 401 being retryable, see
        # `_is_retryable_status` -- burned the full retry budget's backoff delay
        # before `D1StoreError` finally surfaced below. This up-front check skips
        # that wasted, slow round-trip entirely (#2239 review).
        print(
            "error: CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required",
            file=sys.stderr,
        )
        return 1

    try:
        notes = D1Store(
            args.database,
            account_id=account_id,
            api_token=api_token,
        ).list_notes(path_prefix=args.prefix)
    except (ValueError, D1StoreError) as exc:
        # ValueError: resolve_path_prefix (digivault.d1_store) rejects a non-None
        # prefix that normalizes to empty (e.g. "--prefix /") -- fail closed rather
        # than silently syncing every note in the database.
        # D1StoreError: a wrong database id, a malformed-but-non-empty token, or a
        # transport blip -- the presence check above only catches an entirely absent
        # credential, never a wrong one. Both give the clean CLI error d1_sync.py gives.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{len(notes)} notes under {args.prefix!r}", file=sys.stderr)

    class _CountingSink:
        def __init__(self) -> None:
            self.count = 0

        def add(self, chunks: list[Chunk]) -> None:
            self.count += len(chunks)

    sink: VectorSink
    mutation_ids: list[str] = []
    if args.dry_run:
        sink = _CountingSink()
    else:
        from digisearch.indexes.backends.vectorize import _default_http_post

        sink = VectorizeBackend(
            args.index,
            account_id=account_id,
            api_token=api_token,
            http_post=_mutation_capturing_post(_default_http_post, mutation_ids),
        )

    if not args.dry_run:
        assert_index_model(sink, model_id=MINILM_MODEL_ID, dimensions=384)

    total = sync_corpus(
        notes,
        SegmentAwareChunker(),
        None if args.dry_run else MiniLMEmbedder(),
        sink,
        model_id=MINILM_MODEL_ID,
        embed=not args.dry_run,
        # Single source of truth for the flush threshold — VectorizeBackend's own
        # batch size — so this can never drift from what the backend actually sends
        # per HTTP request (see C2: a per-note sink.add() call defeated batching
        # entirely and would blow through Cloudflare's 1,200 req / 5 min rate limit).
        batch_size=DEFAULT_BATCH_SIZE,
    )
    print(f"{'would upsert' if args.dry_run else 'upserted'} {total} vectors → {args.index}")
    if not args.dry_run:
        completed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        print(f"sync_completed_at={completed_at}", file=sys.stderr)
        if mutation_ids:
            print(f"last_mutation_id={mutation_ids[-1]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
