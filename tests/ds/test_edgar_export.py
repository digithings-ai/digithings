"""Unit tests for EDGAR sample export (no Hugging Face download)."""

from __future__ import annotations

import pytest
import yaml
from digisearch.dev.edgar_sample_export import (
    row_to_markdown,
    row_to_sidecar_metadata,
    row_to_stem,
    sidecar_yaml_dict,
    write_export_pair,
)

pytestmark = pytest.mark.unit


def test_row_to_stem_sanitizes_cik() -> None:
    assert row_to_stem({"cik": "12345", "year": 2020}, 3) == "edgar_12345_2020_00003"


def test_row_to_markdown_includes_sections() -> None:
    row = {
        "filename": "test.txt",
        "cik": 1,
        "year": 2020,
        "section_7": "Revenue increased.",
        "section_1A": "We face market risk.",
    }
    md = row_to_markdown(row)
    assert "# SEC filing" in md or "SEC filing excerpt" in md
    assert "Revenue increased." in md
    assert "market risk" in md
    assert "## Item 7" in md or "MD&A" in md


def test_row_to_sidecar_metadata_evidence_tier() -> None:
    row = {"filename": "x.html", "cik": 7654321, "year": 2019}
    meta = row_to_sidecar_metadata(row, "edgar_test")
    assert meta["evidence_tier"] == "industry"
    assert meta["peer_reviewed"] is False
    assert meta["venue"] == "SEC EDGAR"
    assert meta["publication_year"] == 2019
    assert "source_url" in meta and "7654321" in meta["source_url"]


def test_write_export_pair_roundtrip(tmp_path) -> None:
    stem = "edgar_test_2020_00001"
    md = "# T\n\nHello.\n"
    meta = row_to_sidecar_metadata({"filename": "f.txt", "cik": 1, "year": 2020}, stem)
    md_path, yaml_path = write_export_pair(tmp_path, stem, md, meta)
    assert md_path.read_text() == md
    data = yaml.safe_load(yaml_path.read_text())
    assert data == sidecar_yaml_dict(meta)
