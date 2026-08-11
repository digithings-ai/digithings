"""Tests for the generic markdown heading segmenter."""

from __future__ import annotations

import pytest
from digisearch.ingestion.segmenters.heading import heading_segments

_DOC = """# API Guide

Intro paragraph.

## Authentication

How auth works.

### Rotating Keys

Rotate them often.

## Ingestion

How ingest works.
"""


@pytest.mark.unit
def test_no_headings_returns_empty() -> None:
    assert heading_segments("just a paragraph\n\nand another\n") == []


@pytest.mark.unit
def test_splits_on_headings() -> None:
    segs = heading_segments(_DOC)
    assert [s.label for s in segs] == [
        "heading:API Guide",
        "heading:API Guide > Authentication",
        "heading:API Guide > Authentication > Rotating Keys",
        "heading:API Guide > Ingestion",
    ]


@pytest.mark.unit
def test_segments_are_indexed_in_order() -> None:
    segs = heading_segments(_DOC)
    assert [s.index for s in segs] == [0, 1, 2, 3]


@pytest.mark.unit
def test_segment_text_includes_its_heading_and_body() -> None:
    segs = heading_segments(_DOC)
    auth = segs[1]
    assert auth.text.startswith("## Authentication")
    assert "How auth works." in auth.text
    assert "Rotate them often." not in auth.text


@pytest.mark.unit
def test_preamble_before_first_heading_becomes_intro_segment() -> None:
    segs = heading_segments("stray preamble\n\n## First\n\nbody\n")
    assert segs[0].label == "heading:(intro)"
    assert "stray preamble" in segs[0].text
    assert segs[1].label == "heading:First"


@pytest.mark.unit
def test_max_split_level_ignores_deeper_headings() -> None:
    segs = heading_segments(_DOC, max_split_level=2)
    assert [s.label for s in segs] == [
        "heading:API Guide",
        "heading:API Guide > Authentication",
        "heading:API Guide > Ingestion",
    ]
    assert "### Rotating Keys" in segs[1].text


@pytest.mark.unit
def test_hash_lines_inside_fenced_code_block_are_not_headings() -> None:
    doc = (
        "# Real Heading\n"
        "\n"
        "Some text.\n"
        "\n"
        "```python\n"
        "# This is a comment, not a heading\n"
        "def foo():\n"
        "    pass\n"
        "```\n"
        "\n"
        "## Next Section\n"
        "\n"
        "more text\n"
    )
    segs = heading_segments(doc)
    assert [s.label for s in segs] == [
        "heading:Real Heading",
        "heading:Real Heading > Next Section",
    ]
    # The fenced code block, including its fake "#" comment line, must survive verbatim
    # inside the first segment's body rather than being treated as a split point.
    first = segs[0].text
    assert "```python" in first
    assert "# This is a comment, not a heading" in first
    assert "def foo():" in first
    assert "    pass" in first
    assert first.count("```") == 2
    assert "more text" in segs[1].text


@pytest.mark.unit
def test_hash_lines_inside_tilde_fence_are_not_headings() -> None:
    doc = "# Heading\n\n~~~\n# not a heading\n~~~\n\n## Next\n\nbody\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Heading", "heading:Heading > Next"]
    assert "# not a heading" in segs[0].text


@pytest.mark.unit
def test_hash_lines_inside_long_fence_are_not_headings() -> None:
    doc = "# Heading\n\n````\n# not a heading\n```\nstill fenced\n````\n\n## Next\n\nbody\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Heading", "heading:Heading > Next"]
    assert "# not a heading" in segs[0].text
    assert "still fenced" in segs[0].text


@pytest.mark.unit
def test_stub_heading_with_no_body_content_is_skipped() -> None:
    segs = heading_segments("## A\n## B\n\ntext for B\n")
    assert [s.label for s in segs] == ["heading:B"]
    assert segs[0].index == 0


@pytest.mark.unit
def test_index_stays_sequential_when_stub_heading_is_skipped() -> None:
    doc = "# Intro\n\nintro text\n\n## Stub\n## Real\n\nreal body\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Intro", "heading:Intro > Real"]
    assert [s.index for s in segs] == [0, 1]
