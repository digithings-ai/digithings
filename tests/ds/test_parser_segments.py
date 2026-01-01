"""Tests for parser-level segmentation: MarkdownParser populates Document.segments."""

from __future__ import annotations

import pytest
from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
from digisearch.ingestion.parsers.markdown import MarkdownParser


@pytest.mark.unit
def test_markdown_parser_populates_segments_for_headed_doc() -> None:
    content = "# Title\n\nintro text\n\n## Section One\n\nbody one\n\n## Section Two\n\nbody two\n"
    doc = MarkdownParser().parse(content)
    assert [s.label for s in doc.segments] == [
        "heading:Title",
        "heading:Title > Section One",
        "heading:Title > Section Two",
    ]
    assert [s.index for s in doc.segments] == [0, 1, 2]


@pytest.mark.unit
def test_markdown_parser_no_headings_yields_empty_segments() -> None:
    content = "just a plain paragraph with no headings at all.\n"
    doc = MarkdownParser().parse(content)
    assert doc.segments == []


@pytest.mark.unit
def test_markdown_parser_no_headings_chunks_unchanged() -> None:
    """No headings -> segments == [] -> chunks exactly as RecursiveChunker fallback."""
    content = "just a plain paragraph with no headings at all.\n"
    doc = MarkdownParser().parse(content)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == content.strip()


@pytest.mark.unit
def test_headed_markdown_document_chunks_carry_segment_label() -> None:
    content = "# Title\n\nintro text\n\n## Section One\n\nbody one\n\n## Section Two\n\nbody two\n"
    doc = MarkdownParser().parse(content)
    chunks = SegmentAwareChunker().chunk(doc)
    assert len(chunks) == len(doc.segments) == 3
    assert {c.metadata["segment_label"] for c in chunks} == {
        "heading:Title",
        "heading:Title > Section One",
        "heading:Title > Section Two",
    }


@pytest.mark.unit
def test_markdown_parser_from_path(tmp_path: object) -> None:
    """Segmentation also applies when parsing from a file path, not just a string."""
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Heading\n\nbody text\n", encoding="utf-8")
    doc = MarkdownParser().parse(md_file)
    assert [s.label for s in doc.segments] == ["heading:Heading"]
