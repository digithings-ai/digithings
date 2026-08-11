"""Tests for the Supabase -> Vectorize sync."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — recording doubles hold open dicts

import pytest

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


def _note(path: str, body: str) -> dict[str, Any]:
    return {"vault_path": path, "title": path, "frontmatter": {}, "body_markdown": body}


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
    import digivault.supabase_store as supabase_store_module

    import scripts.vectorize_sync as vectorize_sync_module

    class _FakeSupabaseStore:
        @classmethod
        def from_env(cls) -> "_FakeSupabaseStore":
            return cls()

        def list_notes(self, *, path_prefix: str) -> list[dict[str, Any]]:
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

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _FakeSupabaseStore)
    monkeypatch.setattr(vectorize_module, "VectorizeBackend", _FakeVectorizeBackend)
    # Simulate a model upgrade: the guard and the stamp must track this together.
    monkeypatch.setattr(minilm_module, "MINILM_MODEL_ID", "temporarily-different-id")
    monkeypatch.setattr(vectorize_sync_module, "assert_index_model", _fake_assert_index_model)
    monkeypatch.setattr(vectorize_sync_module, "sync_corpus", _fake_sync_corpus)
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "token")

    vectorize_sync_module.main(["--prefix", "clients/acme", "--index", "acme-docs"])

    assert seen["guard"] == seen["sync"] == "temporarily-different-id"


def test_dry_run_makes_zero_embed_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--dry-run must not construct or call the embedder — chunk-and-count only."""
    import digisearch.embedding.providers.minilm as minilm_module
    import digivault.supabase_store as supabase_store_module

    from scripts.vectorize_sync import main

    embed_calls: list[list[str]] = []

    class _SpyEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            embed_calls.append(list(texts))
            return [[0.0] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    class _FakeSupabaseStore:
        @classmethod
        def from_env(cls) -> "_FakeSupabaseStore":
            return cls()

        def list_notes(self, *, path_prefix: str) -> list[dict[str, Any]]:
            return [_note("clients/acme/a", "# A\n\nSome real body text worth chunking.\n")]

    monkeypatch.setattr(minilm_module, "MiniLMEmbedder", _SpyEmbedder)
    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _FakeSupabaseStore)

    exit_code = main(["--prefix", "clients/acme", "--index", "acme-docs", "--dry-run"])

    assert exit_code == 0
    assert embed_calls == []
    out = capsys.readouterr().out
    assert "would upsert" in out
    assert "would upsert 0 vectors" not in out
