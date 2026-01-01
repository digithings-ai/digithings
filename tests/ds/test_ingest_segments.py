"""End-to-end check that segmented documents chunk along their boundaries."""

from __future__ import annotations

import pytest
from digisearch.core.models import Document, Segment
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker


@pytest.mark.unit
def test_segment_metadata_reaches_chunks() -> None:
    doc = Document(
        id="doc-1",
        content="ignored",
        source="https://example.com/guide.pdf",
        doc_type="pdf",
        segments=[
            Segment(index=0, label="page:1", text="intro text", metadata={"page": 1}),
            Segment(index=1, label="page:2", text="body text", metadata={"page": 2}),
        ],
    )
    chunks = SegmentAwareChunker().chunk(doc)
    assert {c.metadata["segment_label"] for c in chunks} == {"page:1", "page:2"}


@pytest.mark.unit
def test_unsegmented_document_is_unchanged_by_wiring() -> None:
    doc = Document(id="doc-2", content="plain text body", source="s", doc_type="txt")
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == "plain text body"
