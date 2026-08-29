"""Tests for the D1 -> Vectorize sync."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — recording doubles hold open dicts

import pytest
from digivault.models import NoteRow

from scripts.vectorize_sync import sync_corpus

pytestmark = pytest.mark.unit


class _StubEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * 384 for _ in texts]

    @property
    def dimensions(self) -> int:
        return 384


class _RecordingBackend:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, chunks: list[Any]) -> None:
        self.added.extend(chunks)


def _note(path: str, body: str, *, title: str | None = None, frontmatter: Any = None) -> NoteRow:
    return NoteRow(
        vault_path=path,
        title=path if title is None else title,
        frontmatter={} if frontmatter is None else frontmatter,
        body_markdown=body,
    )


def test_sync_embeds_and_upserts_every_chunk() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    notes = [_note("clients/acme/a", "# A\n\nbody a\n"), _note("clients/acme/b", "# B\n\nbody b\n")]
    backend = _RecordingBackend()
    count = sync_corpus(
        notes, SegmentAwareChunker(), _StubEmbedder(), backend, model_id="minilm-384"
    )
    assert count == len(backend.added)
    assert count >= 2
    assert all(c.embedding is not None and len(c.embedding) == 384 for c in backend.added)


def test_sync_stamps_model_id_and_source_on_every_chunk() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    backend = _RecordingBackend()
    sync_corpus(
        [_note("clients/acme/a", "# A\n\nbody\n")],
        SegmentAwareChunker(),
        _StubEmbedder(),
        backend,
        model_id="minilm-384",
    )
    assert all(c.metadata["embedding_model"] == "minilm-384" for c in backend.added)
    assert all(c.metadata["vault_path"] == "clients/acme/a" for c in backend.added)


def test_sync_skips_notes_with_empty_bodies() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    backend = _RecordingBackend()
    count = sync_corpus(
        [_note("clients/acme/blank", "   ")],
        SegmentAwareChunker(),
        _StubEmbedder(),
        backend,
        model_id="m",
    )
    assert count == 0
    assert backend.added == []


def test_sync_batches_across_notes_into_one_upsert_call() -> None:
    """C2 repro: N notes whose total chunk count is below batch_size must produce
    exactly ONE sink.add() call, not one per note (the bug that turned a sync of
    ~1,279 notes into ~1,279 HTTP POSTs and hit Cloudflare's rate limit)."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    class _CallCountingBackend(_RecordingBackend):
        def __init__(self) -> None:
            super().__init__()
            self.call_count = 0

        def add(self, chunks: list[Any]) -> None:
            self.call_count += 1
            super().add(chunks)

    notes = [_note(f"clients/acme/{i}", f"# Note {i}\n\nbody {i}\n") for i in range(5)]
    backend = _CallCountingBackend()
    total = sync_corpus(
        notes, SegmentAwareChunker(), _StubEmbedder(), backend, model_id="minilm-384"
    )
    assert backend.call_count == 1
    assert total == len(backend.added)
    assert total > 0


def test_sync_flushes_at_batch_boundary_and_for_the_remainder() -> None:
    """A total chunk count that crosses the batch boundary must flush in full
    batches plus one final partial flush -- not one call per note either."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    class _CallCountingBackend(_RecordingBackend):
        def __init__(self) -> None:
            super().__init__()
            self.call_sizes: list[int] = []

        def add(self, chunks: list[Any]) -> None:
            self.call_sizes.append(len(chunks))
            super().add(chunks)

    # Each note yields exactly 1 chunk (short body, no headings to split on).
    notes = [_note(f"clients/acme/{i}", f"body {i}\n") for i in range(7)]
    backend = _CallCountingBackend()
    total = sync_corpus(
        notes,
        SegmentAwareChunker(),
        _StubEmbedder(),
        backend,
        model_id="minilm-384",
        batch_size=3,
    )
    assert total == 7
    assert backend.call_sizes == [3, 3, 1]


def test_sync_rejects_non_positive_batch_size() -> None:
    """A batch_size < 1 must raise, not infinite-loop: ``while len(buffer) >= 0``
    with a zero-size slice never shrinks the buffer. Unreachable from the CLI
    today (default 1000), but a prior task in this plan shipped a near-identical
    unbounded loop that made ~993,000 calls -- guard it explicitly."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    notes = [_note("clients/acme/a", "# A\n\nbody a\n")]
    with pytest.raises(ValueError, match="batch_size"):
        sync_corpus(
            notes,
            SegmentAwareChunker(),
            _StubEmbedder(),
            _RecordingBackend(),
            model_id="m",
            batch_size=0,
        )


def test_sync_ids_are_deterministic() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    notes = [_note("clients/acme/a", "# A\n\nbody a\n")]
    first, second = _RecordingBackend(), _RecordingBackend()
    sync_corpus(notes, SegmentAwareChunker(), _StubEmbedder(), first, model_id="m")
    sync_corpus(notes, SegmentAwareChunker(), _StubEmbedder(), second, model_id="m")
    assert [c.id for c in first.added] == [c.id for c in second.added]


def test_sync_refuses_to_mix_embedding_models() -> None:
    from scripts.vectorize_sync import ModelMismatchError, assert_index_model

    class _ProbeBackend(_RecordingBackend):
        def query(self, _q: Any) -> list[Any]:
            class _R:
                metadata = {"embedding_model": "some-other-model-768"}

            class _Hit:
                chunk = _R()

            return [_Hit()]

    with pytest.raises(ModelMismatchError, match="some-other-model-768"):
        assert_index_model(_ProbeBackend(), model_id="all-MiniLM-L6-v2-384", dimensions=384)


def test_sync_allows_matching_or_empty_index() -> None:
    from scripts.vectorize_sync import assert_index_model

    class _EmptyBackend:
        def query(self, _q: Any) -> list[Any]:
            return []

    assert_index_model(_EmptyBackend(), model_id="m", dimensions=384)


def test_assert_index_model_probes_with_a_non_zero_unit_vector() -> None:
    """I1 repro: probing with an all-zero vector is undefined for a cosine index
    and may be rejected outright, which would make the guard never fire."""
    from digisearch.core.models import Query as DsQuery

    from scripts.vectorize_sync import assert_index_model

    seen: dict[str, Any] = {}

    class _RecordingProbeBackend:
        def query(self, q: DsQuery) -> list[Any]:
            seen["embedding"] = list(q.embedding or [])
            return []

    assert_index_model(_RecordingProbeBackend(), model_id="m", dimensions=8)
    assert seen["embedding"] != [0.0] * 8
    assert any(v != 0.0 for v in seen["embedding"])


def test_assert_index_model_does_not_block_on_index_not_found() -> None:
    """I1 repro: a brand-new index (first sync) has nothing to probe and must not
    block the sync -- a 404 from the probe is expected, not a real problem."""
    from scripts.vectorize_sync import assert_index_model

    class _NotFoundBackend:
        def query(self, _q: Any) -> list[Any]:
            raise RuntimeError('vectorize query failed (404): [{"message": "index not found"}]')

    assert_index_model(_NotFoundBackend(), model_id="m", dimensions=384)  # must not raise


def test_assert_index_model_warns_but_does_not_block_on_other_probe_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """I1 repro: the old bare `except Exception: return` silently swallowed every
    probe failure, including real ones (auth, transport) -- the guard must
    surface those as a warning instead of proceeding as if nothing happened."""
    from scripts.vectorize_sync import assert_index_model

    class _BrokenBackend:
        def query(self, _q: Any) -> list[Any]:
            raise RuntimeError("vectorize query failed (500): boom")

    with caplog.at_level("WARNING"):
        assert_index_model(_BrokenBackend(), model_id="m", dimensions=384)  # must not raise
    assert any("proceeding without the guard" in record.getMessage() for record in caplog.records)


def test_main_guards_and_syncs_with_the_same_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A future MINILM_MODEL_ID change must reach the guard and the stamp identically.

    Regression for the stale-constant finding: the guard used to be called with a
    hand-maintained literal while ``sync_corpus`` was stamped with the imported
    ``MINILM_MODEL_ID`` — nothing enforced they stayed equal.
    """
    import digisearch.embedding.providers.minilm as minilm_module
    import digisearch.indexes.backends.vectorize as vectorize_module
    import digivault.d1_store as d1_store_module

    import scripts.vectorize_sync as vectorize_sync_module

    class _FakeD1Store:
        def __init__(self, database_id: str, **kwargs: Any) -> None:
            pass

        def list_notes(self, *, path_prefix: str) -> list[NoteRow]:
            return []

    class _FakeVectorizeBackend:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    seen: dict[str, str] = {}

    def _fake_assert_index_model(backend: Any, *, model_id: str, dimensions: int) -> None:
        seen["guard"] = model_id

    def _fake_sync_corpus(
        notes: Any, chunker: Any, embedder: Any, sink: Any, *, model_id: str, **kwargs: Any
    ) -> int:
        seen["sync"] = model_id
        return 0

    monkeypatch.setattr(d1_store_module, "D1Store", _FakeD1Store)
    monkeypatch.setattr(vectorize_module, "VectorizeBackend", _FakeVectorizeBackend)
    # Simulate a model upgrade: the guard and the stamp must track this together.
    monkeypatch.setattr(minilm_module, "MINILM_MODEL_ID", "temporarily-different-id")
    monkeypatch.setattr(vectorize_sync_module, "assert_index_model", _fake_assert_index_model)
    monkeypatch.setattr(vectorize_sync_module, "sync_corpus", _fake_sync_corpus)
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "token")

    vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )

    assert seen["guard"] == seen["sync"] == "temporarily-different-id"


# ── canonical CLOUDFLARE_*/legacy VECTORIZE_*/D1_* credential fallback (#2239
# credential rename) ─────────────────────────────────────────────────────────
def _credential_capturing_main(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, str]]:
    """Wires ``main()`` so a real (non-dry-run) call reaches both credential reads --
    the D1 notes read and the Vectorize sink construction -- capturing what each
    resolved to instead of hitting the network. Returns the ``captured`` dict, keyed
    ``"d1"``/``"vectorize"``.
    """
    import digisearch.embedding.providers.minilm as minilm_module
    import digisearch.indexes.backends.vectorize as vectorize_module
    import digivault.d1_store as d1_store_module

    import scripts.vectorize_sync as vectorize_sync_module

    captured: dict[str, dict[str, str]] = {}

    class _FakeD1Store:
        def __init__(self, database_id: str, *, account_id: str, api_token: str) -> None:
            captured["d1"] = {"account_id": account_id, "api_token": api_token}

        def list_notes(self, *, path_prefix: str) -> list[NoteRow]:
            return []

    class _FakeVectorizeBackend:
        def __init__(self, index_name: str, *, account_id: str, api_token: str) -> None:
            captured["vectorize"] = {"account_id": account_id, "api_token": api_token}

    monkeypatch.setattr(d1_store_module, "D1Store", _FakeD1Store)
    monkeypatch.setattr(vectorize_module, "VectorizeBackend", _FakeVectorizeBackend)
    monkeypatch.setattr(
        vectorize_sync_module, "assert_index_model", lambda backend, *, model_id, dimensions: None
    )
    monkeypatch.setattr(
        vectorize_sync_module,
        "sync_corpus",
        lambda notes, chunker, embedder, sink, *, model_id, **kwargs: 0,
    )
    # `lambda: object()` is just a wrapper around `object` itself -- calling `object`
    # with no args already returns a bare instance, so patch to the class directly.
    monkeypatch.setattr(minilm_module, "MiniLMEmbedder", object)
    return captured


def test_main_accepts_canonical_cloudflare_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN alone must drive both the D1 read
    and the Vectorize write -- no legacy VECTORIZE_*/D1_* name needs to be set."""
    import scripts.vectorize_sync as vectorize_sync_module

    captured = _credential_capturing_main(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    exit_code = vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )

    assert exit_code == 0
    assert captured["d1"] == {"account_id": "acct", "api_token": "tok"}
    assert captured["vectorize"] == {"account_id": "acct", "api_token": "tok"}


def test_main_accepts_legacy_d1_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-downtime property: the legacy D1_ACCOUNT_ID/D1_API_TOKEN names (same
    account + token as Vectorize, per #2239) must keep driving both reads with no
    CLOUDFLARE_*/VECTORIZE_* name set at all."""
    import scripts.vectorize_sync as vectorize_sync_module

    captured = _credential_capturing_main(monkeypatch)
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    exit_code = vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )

    assert exit_code == 0
    assert captured["d1"] == {"account_id": "acct", "api_token": "tok"}
    assert captured["vectorize"] == {"account_id": "acct", "api_token": "tok"}


def test_main_canonical_wins_over_legacy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """When multiple names in the fallback chain are set to *different* values, the
    canonical CLOUDFLARE_* pair must win over both legacy VECTORIZE_* and D1_* for
    both the D1 read and the Vectorize write."""
    import scripts.vectorize_sync as vectorize_sync_module

    captured = _credential_capturing_main(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "canonical-acct")
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "legacy-vectorize-acct")
    monkeypatch.setenv("D1_ACCOUNT_ID", "legacy-d1-acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "canonical-tok")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "legacy-vectorize-tok")
    monkeypatch.setenv("D1_API_TOKEN", "legacy-d1-tok")

    exit_code = vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )

    assert exit_code == 0
    assert captured["d1"] == {"account_id": "canonical-acct", "api_token": "canonical-tok"}
    assert captured["vectorize"] == {"account_id": "canonical-acct", "api_token": "canonical-tok"}


def test_main_requires_cloudflare_credentials_for_a_real_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no name in the fallback chain set, a real (non-dry-run) run must exit
    cleanly rather than reach the network -- mirrors d1_sync.py's own guard.

    `_FakeD1Store` raises if ever instantiated -- a stronger guard than merely
    asserting `main()` exits, so a regression that moves the credential check back
    to *after* constructing `D1Store` (reaching the network before failing) fails
    loudly here instead of passing by coincidence (#2239 review)."""
    import digivault.d1_store as d1_store_module

    import scripts.vectorize_sync as vectorize_sync_module

    class _FakeD1Store:
        def __init__(self, database_id: str, *, account_id: str, api_token: str) -> None:
            raise AssertionError("D1Store must not be constructed without credentials")

    monkeypatch.setattr(d1_store_module, "D1Store", _FakeD1Store)

    rc = vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )
    assert rc == 1


def test_dry_run_makes_zero_embed_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--dry-run must not construct or call the embedder — chunk-and-count only.

    Still needs credentials: `--dry-run` skips the embedder and the Vectorize
    upsert, but the D1 read that supplies the notes to chunk happens either way
    (#2239 review), so the credential presence check `main()` now runs before that
    read must see a non-empty pair here too.
    """
    import digisearch.embedding.providers.minilm as minilm_module
    import digivault.d1_store as d1_store_module

    from scripts.vectorize_sync import main

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    embed_calls: list[list[str]] = []

    class _SpyEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            embed_calls.append(list(texts))
            return [[0.0] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    class _FakeD1Store:
        def __init__(self, database_id: str, **kwargs: Any) -> None:
            pass

        def list_notes(self, *, path_prefix: str) -> list[NoteRow]:
            return [_note("clients/acme/a", "# A\n\nSome real body text worth chunking.\n")]

    monkeypatch.setattr(minilm_module, "MiniLMEmbedder", _SpyEmbedder)
    monkeypatch.setattr(d1_store_module, "D1Store", _FakeD1Store)

    exit_code = main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1", "--dry-run"]
    )

    assert exit_code == 0
    assert embed_calls == []
    out = capsys.readouterr().out
    assert "would upsert" in out
    assert "would upsert 0 vectors" not in out


# --- #2239: vectorize_sync reads notes from D1, not Supabase ---------------------


@pytest.mark.unit
def test_reads_notes_from_d1_not_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI must read notes from D1 via `--database`, never touch Supabase.

    `SupabaseStore.from_env` is monkeypatched to raise if called at all -- a
    stronger guard than merely not asserting it was called, so a future
    reintroduction of the Supabase import fails loudly rather than silently.
    """
    import scripts.vectorize_sync as vectorize_sync

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    seen: dict[str, Any] = {}

    class _FakeD1:
        def __init__(self, database_id: str, **kw: Any) -> None:
            seen["database_id"] = database_id

        def list_notes(self, *, path_prefix: str) -> list[NoteRow]:
            seen["prefix"] = path_prefix
            return []

    monkeypatch.setattr("digivault.d1_store.D1Store", _FakeD1)
    monkeypatch.setattr(
        "digivault.supabase_store.SupabaseStore.from_env",
        lambda: (_ for _ in ()).throw(AssertionError("Supabase must not be read")),
    )
    rc = vectorize_sync.main(
        ["--prefix", "clients/x", "--index", "x_docs", "--database", "db-9", "--dry-run"]
    )
    assert rc == 0
    assert seen == {"database_id": "db-9", "prefix": "clients/x"}


@pytest.mark.unit
def test_prefix_that_normalizes_to_empty_fails_closed_instead_of_syncing_everything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--prefix /` (or any prefix `resolve_path_prefix` normalizes to '') must not
    silently become an unscoped sync of every note in the database -- the real
    `D1Store.list_notes` raises `ValueError` for exactly this case (its own
    `resolve_path_prefix` guard, called before any HTTP request is built), and
    `main` must surface that as a clean CLI error (exit 1) rather than an
    unhandled traceback or, worse, swallowing it and proceeding as if no prefix
    were given at all. Pinned to that specific failure (not just exit code 1) by
    asserting the prefix-guard message reaches stderr -- a regression that made
    `main` exit 1 for an unrelated reason would otherwise pass this test too."""
    import scripts.vectorize_sync as vectorize_sync

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    def _post_must_not_be_called(*args: Any, **kwargs: Any) -> tuple[int, str]:
        raise AssertionError("resolve_path_prefix must raise before any HTTP call")

    # The real D1Store (not a fake) so the real resolve_path_prefix guard runs --
    # this is a property of that function, not something a stub would exercise.
    # http_post would raise if ever reached, proving the ValueError fires first.
    monkeypatch.setattr("digivault.d1_store._default_http_post", _post_must_not_be_called)

    rc = vectorize_sync.main(
        ["--prefix", "/", "--index", "x_docs", "--database", "db-9", "--dry-run"]
    )
    assert rc == 1
    assert "normalizes to an empty prefix" in capsys.readouterr().err


# --- #2226: carry frontmatter segment metadata (page identity) onto chunks ---


def test_sync_carries_frontmatter_segment_fields_onto_chunks() -> None:
    """OCC child-note repro: a note that is already one PDF page has no headings for
    heading_segments() to split on, so its page identity must come from frontmatter
    instead -- this is the metadata Vectorize was coming back with as None."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    note = _note(
        "clients/occ/help-online-compliance-center__p001",
        "Body text of a single already-split PDF page. No headings here at all.\n",
        frontmatter={
            "segment_label": "page:1",
            "segment_index": 0,
            "parent_doc": "help-online-compliance-center-com-images-occ",
            "source_url": "https://example.com/occ/manual.pdf",
            "page_class": "body",
            # Retrieval-irrelevant fields that must NOT be carried over.
            "ingested_at": "2026-08-10T00:00:00Z",
            "status": "published",
            "tags": ["occ", "manual"],
            "content_type": "application/pdf",
        },
    )
    backend = _RecordingBackend()
    sync_corpus([note], SegmentAwareChunker(), _StubEmbedder(), backend, model_id="m")

    assert len(backend.added) == 1
    meta = backend.added[0].metadata
    assert meta["segment_label"] == "page:1"
    assert meta["segment_index"] == 0
    assert meta["parent_doc"] == "help-online-compliance-center-com-images-occ"
    assert meta["source_url"] == "https://example.com/occ/manual.pdf"
    assert meta["page_class"] == "body"
    assert meta["vault_path"] == "clients/occ/help-online-compliance-center__p001"
    # No-value-for-retrieval fields must not ride along.
    assert "ingested_at" not in meta
    assert "status" not in meta
    assert "tags" not in meta
    assert "content_type" not in meta


def test_frontmatter_cannot_override_canonical_stamps() -> None:
    """A previous review round found caller metadata silently overriding
    backend-controlled doc_id/content (see VectorizeBackend.add). Guard the same
    hazard here: a note's frontmatter must never be able to overwrite the
    sync-controlled vault_path/title/embedding_model stamps, even if it carries
    keys with those exact names."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    note = _note(
        "clients/occ/doc__p001",
        "body with no headings\n",
        title="Real Title",
        frontmatter={
            "vault_path": "attacker-controlled-path",
            "title": "attacker title",
            "embedding_model": "attacker-model",
            "segment_label": "page:1",
        },
    )
    backend = _RecordingBackend()
    sync_corpus([note], SegmentAwareChunker(), _StubEmbedder(), backend, model_id="real-model-384")

    meta = backend.added[0].metadata
    assert meta["vault_path"] == "clients/occ/doc__p001"
    assert meta["title"] == "Real Title"
    assert meta["embedding_model"] == "real-model-384"
    # The frontmatter field that ISN'T a canonical stamp still comes through.
    assert meta["segment_label"] == "page:1"


def test_sync_handles_frontmatter_that_is_none() -> None:
    """NoteRow's own validator already coerces a null frontmatter column to {} --
    but sync_corpus must not assume every caller goes through that validator."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    note = NoteRow.model_construct(
        vault_path="clients/acme/a", title="A", frontmatter=None, body_markdown="body a\n"
    )
    backend = _RecordingBackend()
    count = sync_corpus([note], SegmentAwareChunker(), _StubEmbedder(), backend, model_id="m")

    assert count == 1
    assert backend.added[0].metadata["vault_path"] == "clients/acme/a"


def test_sync_handles_frontmatter_that_is_not_a_dict() -> None:
    """Defensive: a non-dict frontmatter (e.g. a malformed jsonb column) must not
    raise -- it is treated the same as no frontmatter at all."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    note = NoteRow.model_construct(
        vault_path="clients/acme/a",
        title="A",
        frontmatter=["not", "a", "dict"],
        body_markdown="body a\n",
    )
    backend = _RecordingBackend()
    count = sync_corpus([note], SegmentAwareChunker(), _StubEmbedder(), backend, model_id="m")

    assert count == 1
    assert backend.added[0].metadata["vault_path"] == "clients/acme/a"


def test_per_chunk_segment_label_wins_over_note_level_frontmatter_label() -> None:
    """A note whose body genuinely has headings (e.g. the digithings repo docs)
    still produces heading segments -- SegmentAwareChunker's own, more specific
    per-chunk segment_label must win over the note-level frontmatter value, not
    be clobbered by it."""
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    note = _note(
        "clients/digithings/docs/foo",
        "# Real Heading\n\nSome content under a real heading.\n",
        frontmatter={"segment_label": "page:1", "segment_index": 0},
    )
    backend = _RecordingBackend()
    sync_corpus([note], SegmentAwareChunker(), _StubEmbedder(), backend, model_id="m")

    assert backend.added[0].metadata["segment_label"] == "heading:Real Heading"


@pytest.mark.unit
def test_d1_store_error_is_a_clean_cli_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A wrong (non-empty) D1 token must exit 1 with a readable message, not raise.

    The credential presence check in `main()` only catches an entirely absent
    account id/token (#2239 review) -- it cannot catch a *typo'd* one, which still
    reaches Cloudflare, comes back 401, and is wrapped as D1StoreError -- a
    RuntimeError subclass that an `except ValueError` arm does not catch. Without
    this the operator got an unhandled traceback after a wasted round-trip.
    """
    from digivault.d1_errors import D1StoreError

    import scripts.vectorize_sync as vectorize_sync

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "typo-d-token")

    class _FailingD1:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def list_notes(self, *, path_prefix: str | None = None) -> list:
            raise D1StoreError("d1 list_notes failed (401): authentication error")

    monkeypatch.setattr("digivault.d1_store.D1Store", _FailingD1)
    rc = vectorize_sync.main(
        ["--prefix", "clients/x", "--index", "x_docs", "--database", "db-1", "--dry-run"]
    )
    assert rc == 1
    assert "authentication error" in capsys.readouterr().err


@pytest.mark.unit
def test_apply_prints_sync_completion_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Apply pass prints operator-facing sync metadata for runbook step 3a (#2236)."""
    import digisearch.indexes.backends.vectorize as vectorize_module
    import digivault.d1_store as d1_store_module

    import scripts.vectorize_sync as vectorize_sync_module

    class _FakeD1Store:
        def __init__(self, database_id: str, **kwargs: object) -> None:
            pass

        def list_notes(self, *, path_prefix: str) -> list[NoteRow]:
            return []

    class _FakeVectorizeBackend:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    monkeypatch.setattr(d1_store_module, "D1Store", _FakeD1Store)
    monkeypatch.setattr(vectorize_module, "VectorizeBackend", _FakeVectorizeBackend)
    monkeypatch.setattr(
        vectorize_sync_module, "assert_index_model", lambda backend, *, model_id, dimensions: None
    )
    monkeypatch.setattr(
        vectorize_sync_module,
        "sync_corpus",
        lambda notes, chunker, embedder, sink, *, model_id, **kwargs: 3,
    )
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    rc = vectorize_sync_module.main(
        ["--prefix", "clients/acme", "--index", "acme-docs", "--database", "db-1"]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert out.out.strip() == "upserted 3 vectors → acme-docs"
    assert "sync_completed_at=" in out.err


@pytest.mark.unit
def test_mutation_capturing_post_collects_upsert_mutation_ids() -> None:
    import scripts.vectorize_sync as vectorize_sync_module

    captured: list[str] = []

    def _inner(
        url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        return 200, '{"success": true, "result": {"mutationId": "mut-42"}}'

    post = vectorize_sync_module._mutation_capturing_post(_inner, captured)
    status, text = post(
        "https://api.cloudflare.com/client/v4/accounts/a/vectorize/v2/indexes/i/upsert",
        {},
        b"",
        "application/x-ndjson",
    )
    assert status == 200
    assert text
    assert captured == ["mut-42"]
