"""Tests for PDF page segmentation."""

from __future__ import annotations

import pytest
from digisearch.ingestion.parsers import pdf as pdf_module
from digisearch.ingestion.parsers.pdf import PDFParser


@pytest.mark.unit
def test_pdf_parser_emits_one_segment_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(
        pdf_module,
        "_extract_pages",
        lambda raw: ["page one text", "page two text", "page three text"],
    )
    doc = PDFParser().parse(b"%PDF-fake")
    assert [s.label for s in doc.segments] == ["page:1", "page:2", "page:3"]
    assert [s.index for s in doc.segments] == [0, 1, 2]
    assert doc.segments[1].text == "page two text"
    assert doc.segments[1].metadata == {"page": 2}


@pytest.mark.unit
def test_pdf_parser_content_still_flattened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(pdf_module, "_extract_pages", lambda raw: ["alpha", "beta"])
    doc = PDFParser().parse(b"%PDF-fake")
    assert doc.content == "alpha\nbeta"
    assert doc.doc_type == "pdf"


@pytest.mark.unit
def test_pdf_parser_skips_blank_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_module, "_PDF_AVAILABLE", True)
    monkeypatch.setattr(pdf_module, "_extract_pages", lambda raw: ["real", "   ", "also real"])
    doc = PDFParser().parse(b"%PDF-fake")
    assert [s.label for s in doc.segments] == ["page:1", "page:3"]
