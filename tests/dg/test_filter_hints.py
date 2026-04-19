"""Unit tests for NL → FilterHints extraction (digigraph.filter_hints)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from digigraph.filter_hints import FilterHints, extract_filter_hints


def _canned(content: str):
    """Return a patch context that makes chat_completion return ``content``."""
    return patch("digigraph.filter_hints.chat_completion", return_value=content)


@pytest.mark.unit
def test_extracts_year_and_region() -> None:
    payload = json.dumps({"year": 2024, "region": "Europe", "topic": "AI funding"})
    with _canned(payload):
        hints = extract_filter_hints("AI funding in Europe 2024")
    assert hints.year == 2024
    assert hints.region == "Europe"
    assert hints.topic and "ai funding" in hints.topic.lower()
    assert not hints.is_empty()


@pytest.mark.unit
def test_no_year_or_region_for_vague_time_reference() -> None:
    payload = json.dumps({"year": None, "region": None, "topic": "best stocks"})
    with _canned(payload):
        hints = extract_filter_hints("best stocks this week")
    assert hints.year is None
    assert hints.region is None
    # topic may still be populated; that's fine


@pytest.mark.unit
def test_extracts_region_and_topic_without_year() -> None:
    payload = json.dumps({"region": "Asia", "topic": "climate policy changes"})
    with _canned(payload):
        hints = extract_filter_hints("climate policy changes in Asia")
    assert hints.year is None
    assert hints.region == "Asia"
    assert hints.topic and "climate" in hints.topic.lower()


@pytest.mark.unit
def test_fail_open_on_llm_exception() -> None:
    with patch("digigraph.filter_hints.chat_completion", side_effect=RuntimeError("boom")):
        hints = extract_filter_hints("any query here")
    assert hints == FilterHints()
    assert hints.is_empty()


@pytest.mark.unit
def test_fail_open_on_garbage_output() -> None:
    with _canned("this is not json at all"):
        hints = extract_filter_hints("AI funding in Europe 2024")
    assert hints.is_empty()


@pytest.mark.unit
def test_handles_fenced_json() -> None:
    fenced = "```json\n" + json.dumps({"year": 2023, "region": "US"}) + "\n```"
    with _canned(fenced):
        hints = extract_filter_hints("US market 2023")
    assert hints.year == 2023
    assert hints.region == "US"


@pytest.mark.unit
def test_context_block_formatting() -> None:
    h = FilterHints(year=2024, region="Europe", topic="ai funding")
    block = h.as_context_block()
    assert block.startswith("[Detected filter hints:")
    assert "year=2024" in block
    assert "region=Europe" in block
    assert "topic=ai funding" in block


@pytest.mark.unit
def test_empty_hints_produce_empty_block() -> None:
    assert FilterHints().as_context_block() == ""


@pytest.mark.unit
def test_empty_query_short_circuits() -> None:
    with patch("digigraph.filter_hints.chat_completion") as m:
        hints = extract_filter_hints("   ")
    assert hints.is_empty()
    m.assert_not_called()


@pytest.mark.unit
def test_env_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_FILTER_HINTS", "0")
    with patch("digigraph.filter_hints.chat_completion") as m:
        hints = extract_filter_hints("AI funding in Europe 2024")
    assert hints.is_empty()
    m.assert_not_called()


@pytest.mark.unit
def test_invalid_year_rejected_fail_open() -> None:
    # year=42 fails the 1900..2100 validator → fail-open to empty hints.
    with _canned(json.dumps({"year": 42, "region": "Europe"})):
        hints = extract_filter_hints("something weird")
    assert hints.is_empty()


@pytest.mark.unit
def test_blank_strings_become_none() -> None:
    with _canned(json.dumps({"year": None, "region": "  ", "topic": ""})):
        hints = extract_filter_hints("whatever")
    assert hints.region is None
    assert hints.topic is None
