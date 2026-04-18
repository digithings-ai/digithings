"""DigiSearch evidence metadata helpers (unit)."""

from __future__ import annotations

import pytest

from digisearch.core.chroma_where import structured_filters_to_chroma_where
from digisearch.core.evidence_metadata import merge_document_metadata_into_chunks, normalize_metadata_for_chroma
from digisearch.core.filter_apply import chunk_metadata_matches
from digisearch.core.models import Chunk, Document


@pytest.mark.unit
def test_normalize_list_to_comma_string() -> None:
    m = normalize_metadata_for_chroma({"asset_class_tags": ["a", "b"], "peer_reviewed": True})
    assert m["asset_class_tags"] == "a,b"
    assert m["peer_reviewed"] is True


@pytest.mark.unit
def test_filter_in_comma_tags() -> None:
    s = [{"field": "asset_class_tags", "op": "in", "value": ["gold"]}]
    assert chunk_metadata_matches(s, {"asset_class_tags": "gold,fx"})
    assert not chunk_metadata_matches(s, {"asset_class_tags": "equities"})


@pytest.mark.unit
def test_chroma_where_skips_tag_fields() -> None:
    s = [{"field": "asset_class_tags", "op": "eq", "value": "gold"}]
    assert structured_filters_to_chroma_where(s) is None


@pytest.mark.unit
def test_merge_document_metadata_into_chunks() -> None:
    doc = Document(
        id="d1",
        content="x",
        source="/x",
        doc_type="md",
        metadata={"evidence_tier": "peer_reviewed", "title": "T"},
    )
    chunks = [Chunk(id="d1_0", content="a", doc_id="d1", metadata={"chunk_index": 0})]
    merge_document_metadata_into_chunks(doc, chunks)
    assert chunks[0].metadata.get("evidence_tier") == "peer_reviewed"
