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
