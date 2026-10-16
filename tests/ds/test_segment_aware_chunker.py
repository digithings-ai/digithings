"""Tests for segment-aware chunking."""

from __future__ import annotations

import pytest
from digisearch.core.models import Document, Segment
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker


@pytest.mark.unit
def test_falls_back_to_inner_when_no_segments() -> None:
    doc = Document(id="d1", content="word " * 800, source="s", doc_type="txt")
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) >= 2
    assert all(c.doc_id == "d1" for c in chunks)
    assert all("segment_label" not in c.metadata for c in chunks)


@pytest.mark.unit
def test_short_segment_becomes_exactly_one_chunk() -> None:
    segs = [
        Segment(index=0, label="page:1", text="short page one"),
        Segment(index=1, label="page:2", text="short page two"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 2
    assert chunks[0].content == "short page one"
    assert chunks[0].metadata["segment_label"] == "page:1"
    assert chunks[1].metadata["segment_index"] == 1


@pytest.mark.unit
def test_oversized_segment_is_subsplit_without_crossing_boundaries() -> None:
    segs = [
        Segment(index=0, label="page:1", text="alpha " * 900),
        Segment(index=1, label="page:2", text="beta"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    page_one = [c for c in chunks if c.metadata["segment_label"] == "page:1"]
    page_two = [c for c in chunks if c.metadata["segment_label"] == "page:2"]
    assert len(page_one) > 1
    assert len(page_two) == 1
    assert all("beta" not in c.content for c in page_one)
    assert page_two[0].content == "beta"


@pytest.mark.unit
def test_chunk_ids_and_indices_are_sequential_across_segments() -> None:
    segs = [
        Segment(index=0, label="page:1", text="gamma " * 900),
        Segment(index=1, label="page:2", text="delta"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert [c.id for c in chunks] == [f"d1_{i}" for i in range(len(chunks))]
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


@pytest.mark.unit
def test_blank_segments_are_skipped() -> None:
    segs = [
        Segment(index=0, label="page:1", text="   "),
        Segment(index=1, label="page:2", text="real content"),
    ]
    doc = Document(id="d1", content="ignored", source="s", doc_type="pdf", segments=segs)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].metadata["segment_label"] == "page:2"
