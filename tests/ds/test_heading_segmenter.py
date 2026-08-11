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
