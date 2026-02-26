"""Tests for document parsers."""

from __future__ import annotations

import pytest

from digisearch.ingestion.parsers.plaintext import PlainTextParser
from digisearch.ingestion.registry import ParserRegistry


@pytest.mark.unit
def test_plaintext_parser() -> None:
    p = PlainTextParser()
    doc = p.parse("hello world")
    assert doc.content == "hello world"
    assert doc.doc_type == "plaintext"


@pytest.mark.unit
def test_registry_plaintext() -> None:
    r = ParserRegistry()
    doc = r.parse("simple text")
    assert "simple text" in doc.content
