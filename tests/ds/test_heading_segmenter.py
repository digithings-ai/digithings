"""Tests for the generic markdown heading segmenter."""

from __future__ import annotations

import re

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


@pytest.mark.unit
def test_stub_heading_text_is_carried_into_next_segment() -> None:
    # Confirmed repro: a skipped stub heading's own line must not vanish from the
    # corpus — it must surface at the start of the next emitted segment's text.
    segs = heading_segments("## Stub\n## Real\n\nbody\n")
    assert [s.label for s in segs] == ["heading:Real"]
    assert segs[0].index == 0
    assert segs[0].text.startswith("## Stub")
    assert "## Real" in segs[0].text
    assert "body" in segs[0].text
    stub_pos = segs[0].text.index("## Stub")
    real_pos = segs[0].text.index("## Real")
    assert stub_pos < real_pos


@pytest.mark.unit
def test_several_consecutive_stub_headings_are_all_carried_in_order() -> None:
    doc = "## Stub One\n## Stub Two\n## Real\n\nbody\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Real"]
    text = segs[0].text
    assert "## Stub One" in text
    assert "## Stub Two" in text
    assert "## Real" in text
    assert text.index("## Stub One") < text.index("## Stub Two") < text.index("## Real")


@pytest.mark.unit
def test_trailing_stub_heading_is_appended_to_previous_segment() -> None:
    doc = "# Intro\n\nintro text\n\n## Stub\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Intro"]
    assert "intro text" in segs[0].text
    assert "## Stub" in segs[0].text
    assert segs[0].text.index("intro text") < segs[0].text.index("## Stub")


@pytest.mark.unit
def test_lone_trailing_stub_heading_with_no_prior_segment_becomes_its_own_segment() -> None:
    segs = heading_segments("## Stub\n")
    assert len(segs) == 1
    assert segs[0].label == "heading:Stub"
    assert segs[0].text == "## Stub"
    assert segs[0].index == 0


@pytest.mark.unit
def test_stub_with_descendant_heading_preserves_text_without_duplication() -> None:
    doc = "## Stub\n### Child\n\nchild body\n"
    segs = heading_segments(doc)
    assert [s.label for s in segs] == ["heading:Stub > Child"]
    text = segs[0].text
    assert text.startswith("## Stub")
    assert text.count("## Stub") == 1
    assert "### Child" in text
    assert "child body" in text


@pytest.mark.unit
def test_no_content_dropped_with_stub_and_fenced_code_block() -> None:
    doc = (
        "## Stub\n"
        "## Real\n"
        "\n"
        "```python\n"
        "# fake heading\n"
        "```\n"
        "\n"
        "body text\n"
    )
    segs = heading_segments(doc)
    concatenated = "".join(s.text for s in segs)
    source_chars = len(re.sub(r"\s", "", doc))
    concatenated_chars = len(re.sub(r"\s", "", concatenated))
    assert source_chars == concatenated_chars
