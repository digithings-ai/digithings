"""Unit tests for Chonkie chunking backends and DIGISEARCH_CHUNKER selection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from digisearch.chunking.chonkie_semantic import ChonkieSemanticChunker
from digisearch.chunking.chonkie_token import ChonkieTokenChunker
from digisearch.chunking.document_adapter import BackendDocumentChunker
from digisearch.chunking.factory import (
    DEFAULT_CHUNKER_NAME,
    get_chunker_backend,
    get_document_chunker,
    get_ingest_chunker,
    resolve_chunker_name,
)
from digisearch.core.models import Document
from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
from digisearch.ingestion.chunkers.recursive import RecursiveChunker
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker


class _FakeChonkieChunk:
    def __init__(self, text: str, start: int, end: int, token_count: int) -> None:
        self.text = text
        self.start_index = start
        self.end_index = end
        self.token_count = token_count


class _FakeInner:
    def __init__(self, pieces: list[str] | None = None) -> None:
        self.pieces = pieces

    def chunk(self, text: str) -> list[_FakeChonkieChunk]:
        if self.pieces is not None:
            out: list[_FakeChonkieChunk] = []
            pos = 0
            for p in self.pieces:
                out.append(_FakeChonkieChunk(p, pos, pos + len(p), max(1, len(p) // 4)))
                pos += len(p)
            return out
        mid = max(1, len(text) // 2)
        return [
            _FakeChonkieChunk(text[:mid], 0, mid, mid),
            _FakeChonkieChunk(text[mid:], mid, len(text), len(text) - mid),
        ]


@pytest.mark.unit
def test_default_chunker_name_is_semantic() -> None:
    assert DEFAULT_CHUNKER_NAME == "semantic"
    assert resolve_chunker_name() == "semantic"


@pytest.mark.unit
def test_resolve_chunker_name_env_and_index_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "token")
    assert resolve_chunker_name() == "token"
    # Explicit name wins over env.
    assert resolve_chunker_name("semantic") == "semantic"
    # Index config wins over env when name is omitted.
    assert resolve_chunker_name(index_config={"chunker": "recursive"}) == "recursive"


@pytest.mark.unit
def test_get_chunker_backend_semantic_and_token() -> None:
    sem = get_chunker_backend("semantic")
    tok = get_chunker_backend("token")
    assert isinstance(sem, ChonkieSemanticChunker)
    assert isinstance(tok, ChonkieTokenChunker)


@pytest.mark.unit
def test_get_chunker_backend_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown DIGISEARCH_CHUNKER"):
        get_chunker_backend("not-a-chunker")


@pytest.mark.unit
def test_chonkie_semantic_chunker_with_injected_inner() -> None:
    backend = ChonkieSemanticChunker(_inner=_FakeInner(["alpha. ", "beta."]))
    chunks = backend.chunk("alpha. beta.")
    assert len(chunks) == 2
    assert chunks[0].content == "alpha. "
    assert chunks[1].content == "beta."
    assert chunks[0].metadata["chunker"] == "chonkie"
    assert chunks[0].doc_id == ""


@pytest.mark.unit
def test_chonkie_token_chunker_real_character_tokenizer() -> None:
    """Token path uses base chonkie (no embedding model download)."""
    backend = ChonkieTokenChunker(tokenizer="character", chunk_size=40, chunk_overlap=5)
    text = "News flash: oil inventories rose unexpectedly this week. " * 4
    chunks = backend.chunk(text)
    assert len(chunks) >= 2
    assert all(c.content for c in chunks)
    assert all(c.metadata.get("token_count", 0) > 0 for c in chunks)


@pytest.mark.unit
def test_backend_document_chunker_stamps_doc_ids() -> None:
    backend = ChonkieSemanticChunker(_inner=_FakeInner())
    doc = Document(id="d9", content="abcdefghij", source="x", doc_type="txt")
    chunks = BackendDocumentChunker(backend).chunk(doc)
    assert [c.id for c in chunks] == ["d9_0", "d9_1"]
    assert all(c.doc_id == "d9" for c in chunks)


@pytest.mark.unit
def test_get_ingest_chunker_default_wraps_semantic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_CHUNKER", raising=False)

    def _fake_semantic() -> ChonkieSemanticChunker:
        return ChonkieSemanticChunker(_inner=_FakeInner(["one block"]))

    monkeypatch.setattr(
        "digisearch.chunking.factory.ChonkieSemanticChunker",
        lambda **_kwargs: _fake_semantic(),
    )
    chunker = get_ingest_chunker()
    assert isinstance(chunker, SegmentAwareChunker)
    assert isinstance(chunker.inner, BackendDocumentChunker)
    assert isinstance(chunker.inner.backend, ChonkieSemanticChunker)
    doc = Document(id="x", content="one block", source="s", doc_type="txt")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == "one block"


@pytest.mark.unit
def test_get_document_chunker_legacy_recursive_and_fixed() -> None:
    assert isinstance(get_document_chunker("recursive"), RecursiveChunker)
    assert isinstance(get_document_chunker("fixed"), FixedSizeChunker)


@pytest.mark.unit
def test_chunker_backend_protocol_structural() -> None:
    """Chonkie wrappers satisfy ChunkerBackend (chunk(text) -> list[Chunk])."""
    backend = ChonkieTokenChunker(
        _inner=SimpleNamespace(
            chunk=lambda text: [_FakeChonkieChunk(text, 0, len(text), 1)],
        )
    )
    assert hasattr(backend, "chunk")
    out = backend.chunk("hi")
    assert len(out) == 1
    assert out[0].content == "hi"
