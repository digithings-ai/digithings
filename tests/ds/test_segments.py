"""Tests for the Segment data contract and Document.segments overlay."""

from __future__ import annotations

import pytest
from digisearch.core.models import Document, Segment


@pytest.mark.unit
def test_segment_fields() -> None:
    seg = Segment(index=0, label="page:1", text="hello")
    assert seg.index == 0
    assert seg.label == "page:1"
    assert seg.text == "hello"
    assert seg.metadata == {}


@pytest.mark.unit
def test_document_segments_defaults_empty() -> None:
    doc = Document(id="d1", content="x", source="s", doc_type="txt")
    assert doc.segments == []


@pytest.mark.unit
def test_document_accepts_segments() -> None:
    segs = [Segment(index=0, label="page:1", text="a"), Segment(index=1, label="page:2", text="b")]
    doc = Document(id="d1", content="ab", source="s", doc_type="pdf", segments=segs)
    assert len(doc.segments) == 2
    assert doc.segments[1].label == "page:2"


@pytest.mark.unit
def test_segment_exported_from_core_package() -> None:
    from digisearch.core import Segment as CoreSegment

    assert CoreSegment is Segment
