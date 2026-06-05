"""Unit tests for Atlas research-document ingest into DigiSearch.

Validates the contract surfaced by ``digisearch.atlas_ingest`` and the
``search_strategies`` MCP tool: chunks land in the configured index with
filterable metadata, repeats are idempotent, and the MCP tool returns typed
hits filtered by Atlas-specific structured clauses.

Tests stay backend-free — they rely on the in-memory stub gated by
``DIGISEARCH_ALLOW_STUB=1`` (set by ``tests/conftest.py``).
"""

from __future__ import annotations

from datetime import date

import pytest

from digisearch.atlas_ingest import (
    ATLAS_INDEX_NAME,
    IndexedDocument,
    fetch_atlas_row,
    ingest_atlas_document,
    ingest_atlas_payload,
)
from digisearch.core.models import Query
from digisearch.atlas_search import search_strategies
from digisearch.search import query_index
from digisearch.search._stub import _stub_index


@pytest.fixture(autouse=True)
def _isolate_atlas_index() -> None:
    """Use a per-test stub index so concurrent tests cannot interfere.

    ``ATLAS_INDEX_NAME`` is module-evaluated from the env once per process;
    we clear and restore the matching slot in ``_stub_index`` around each
    test.
    """
    _stub_index.pop(ATLAS_INDEX_NAME, None)
    yield
    _stub_index.pop(ATLAS_INDEX_NAME, None)


def _make_atlas_row(
    *,
    document_key: str = "technology",
    iso_date: str = "2026-04-21",
    doc_type: str = "Daily Digest",
    segment: str = "technology",
    sector: str | None = None,
    run_type: str = "baseline",
    payload: dict | None = None,
    content: str | None = None,
) -> dict:
    """Shape a fake Supabase ``documents`` row matching ``publish_document``'s output."""
    return {
        "date": iso_date,
        "document_key": document_key,
        "doc_type": doc_type,
        "segment": segment,
        "sector": sector,
        "run_type": run_type,
        "category": "research",
        "title": f"{document_key} {iso_date}",
        "payload": payload
        or {"thesis": "Mean reversion in tech megacaps", "asset_class": "equities"},
        "content": content,
    }


@pytest.mark.unit
def test_ingest_atlas_document_creates_chunks() -> None:
    """ingest_atlas_payload chunks the row and stamps Atlas metadata on each chunk."""
    row = _make_atlas_row(
        content=(
            "Tech sector momentum remains positive heading into Q2 earnings. "
            "Mean-reversion signals are weak; trend followers dominate. " * 4
        )
    )

    result = ingest_atlas_payload(row)

    assert isinstance(result, IndexedDocument)
    assert result.chunks_created >= 1
    assert result.document_key == "technology"
    assert result.date == "2026-04-21"
    assert result.index_name == ATLAS_INDEX_NAME

    chunks = _stub_index[ATLAS_INDEX_NAME]
    assert len(chunks) == result.chunks_created
    first = chunks[0]
    assert first.metadata["doc_type"] == "Daily Digest"
    assert first.metadata["segment"] == "technology"
    assert first.metadata["run_type"] == "baseline"
    assert first.metadata["date"] == "2026-04-21"
    assert first.metadata["date_ordinal"] == 20260421
    # asset_class lives inside payload but is hoisted into chunk metadata
    assert first.metadata["asset_class"] == "equities"


@pytest.mark.unit
def test_ingest_falls_back_to_payload_json_when_content_missing() -> None:
    """When the row has no markdown content, payload JSON becomes the chunk text."""
    row = _make_atlas_row(content=None, payload={"bias": "long", "asset_class": "equities"})
    result = ingest_atlas_payload(row)
    chunks = _stub_index[ATLAS_INDEX_NAME]
    assert chunks
    # JSON dump is sorted-key for stable cache hits — both keys must appear.
    assert "asset_class" in chunks[0].content
    assert "bias" in chunks[0].content
    assert result.chunks_created == len(chunks)


@pytest.mark.unit
def test_metadata_filter_by_date_range() -> None:
    """Range filter on date_ordinal returns only docs in the window."""
    ingest_atlas_payload(
        _make_atlas_row(document_key="tech-old", iso_date="2026-04-15", content="old tech research")
    )
    ingest_atlas_payload(
        _make_atlas_row(document_key="tech-new", iso_date="2026-04-25", content="new tech research")
    )
    ingest_atlas_payload(
        _make_atlas_row(
            document_key="tech-newest", iso_date="2026-04-26", content="newest tech research"
        )
    )

    q = Query(
        text="tech",
        top_k=10,
        filters={"structured": [{"field": "date_ordinal", "op": "ge", "value": 20260420}]},
    )
    resp = query_index(q, index_name=ATLAS_INDEX_NAME)
    keys = {r.chunk.metadata["document_key"] for r in resp.results}
    assert "tech-new" in keys
    assert "tech-newest" in keys
    assert "tech-old" not in keys


@pytest.mark.unit
def test_metadata_filter_by_doc_type() -> None:
    """Equality filter on doc_type returns only the matching doc_type."""
    ingest_atlas_payload(
        _make_atlas_row(document_key="digest-row", doc_type="Daily Digest", content="digest body")
    )
    ingest_atlas_payload(
        _make_atlas_row(document_key="delta-row", doc_type="Daily Delta", content="delta body")
    )

    q = Query(
        text="body",
        top_k=10,
        filters={"structured": [{"field": "doc_type", "op": "eq", "value": "Daily Digest"}]},
    )
    resp = query_index(q, index_name=ATLAS_INDEX_NAME)
    assert resp.results
    for hit in resp.results:
        assert hit.chunk.metadata["doc_type"] == "Daily Digest"


@pytest.mark.unit
def test_metadata_filter_by_sector() -> None:
    """Equality filter on sector returns only the matching ticker analyst doc."""
    ingest_atlas_payload(
        _make_atlas_row(
            document_key="analyst/AAPL",
            segment="analyst",
            sector="AAPL",
            content="aapl analyst note",
        )
    )
    ingest_atlas_payload(
        _make_atlas_row(
            document_key="analyst/MSFT",
            segment="analyst",
            sector="MSFT",
            content="msft analyst note",
        )
    )

    q = Query(
        text="analyst",
        top_k=10,
        filters={"structured": [{"field": "sector", "op": "eq", "value": "AAPL"}]},
    )
    resp = query_index(q, index_name=ATLAS_INDEX_NAME)
    assert resp.results
    for hit in resp.results:
        assert hit.chunk.metadata["sector"] == "AAPL"


@pytest.mark.unit
def test_search_strategies_mcp_tool_returns_typed_results() -> None:
    """The MCP tool returns the documented dict shape for downstream agents."""
    ingest_atlas_payload(_make_atlas_row(content="Crude oil bullish bias on supply tightness."))
    hits = search_strategies(query="bullish bias", top_k=5)
    assert isinstance(hits, list)
    assert hits, "expected at least one hit for the seeded chunk"
    for hit in hits:
        assert set(hit.keys()) == {
            "chunk_id",
            "doc_id",
            "score",
            "content",
            "content_length",
            "metadata",
        }
        assert isinstance(hit["chunk_id"], str)
        assert isinstance(hit["doc_id"], str)
        assert isinstance(hit["score"], float)
        assert isinstance(hit["content_length"], int)
        assert hit["metadata"]["source"] == "atlas"


@pytest.mark.unit
def test_search_strategies_filters_by_run_type_and_date_range() -> None:
    """The MCP tool wires its keyword args into structured filters."""
    ingest_atlas_payload(
        _make_atlas_row(
            document_key="energy-baseline",
            iso_date="2026-04-22",
            run_type="baseline",
            segment="energy",
            content="Energy baseline thesis",
        )
    )
    ingest_atlas_payload(
        _make_atlas_row(
            document_key="energy-delta",
            iso_date="2026-04-22",
            run_type="delta",
            segment="energy",
            content="Energy delta update",
        )
    )

    hits = search_strategies(
        query="energy",
        top_k=10,
        run_type="baseline",
        date_from_ymd=20260420,
        date_to_ymd=20260423,
    )
    document_keys = {h["metadata"]["document_key"] for h in hits}
    assert "energy-baseline" in document_keys
    assert "energy-delta" not in document_keys


@pytest.mark.unit
def test_idempotent_reingest_replaces_chunks() -> None:
    """Re-ingesting the same (date, document_key) row replaces — does not append."""
    row = _make_atlas_row(content="First version of the technology digest body.")
    first = ingest_atlas_payload(row)
    chunk_count_after_first = len(_stub_index[ATLAS_INDEX_NAME])

    # Same row replayed → same chunk ids → upsert by replacement.
    second = ingest_atlas_payload(row)
    assert second.doc_id == first.doc_id
    assert len(_stub_index[ATLAS_INDEX_NAME]) == chunk_count_after_first

    # Same row but different content → still same doc_id, still no duplicates.
    updated_row = _make_atlas_row(content="Second version with more detail. " * 8)
    third = ingest_atlas_payload(updated_row)
    assert third.doc_id == first.doc_id
    chunks = _stub_index[ATLAS_INDEX_NAME]
    # All chunks should belong to the single doc_id.
    assert {c.doc_id for c in chunks} == {first.doc_id}


@pytest.mark.unit
def test_ingest_atlas_payload_requires_natural_key() -> None:
    """Missing (date, document_key) raises before any side-effect."""
    with pytest.raises(ValueError):
        ingest_atlas_payload({"date": "", "document_key": ""})
    with pytest.raises(ValueError):
        ingest_atlas_payload({"document_key": "x"})


# --- Supabase-aware path: in-memory fake client ---------------------------------


class _FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._date: str | None = None
        self._key: str | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def eq(self, field: str, value: str) -> "_FakeQuery":
        if field == "date":
            self._date = value
        elif field == "document_key":
            self._key = value
        return self

    def limit(self, _n: int) -> "_FakeQuery":
        return self

    def execute(self) -> object:
        rows = [
            r
            for r in self._rows
            if (self._date is None or r.get("date") == self._date)
            and (self._key is None or r.get("document_key") == self._key)
        ]
        return type("Resp", (), {"data": rows})()


class _FakeSupabase:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def table(self, name: str) -> _FakeQuery:
        assert name == "documents"
        return _FakeQuery(self._rows)


@pytest.mark.unit
def test_fetch_atlas_row_filters_by_natural_key() -> None:
    """fetch_atlas_row narrows by (date, document_key); returns None when absent."""
    rows = [
        _make_atlas_row(document_key="technology", iso_date="2026-04-21"),
        _make_atlas_row(document_key="energy", iso_date="2026-04-21"),
    ]
    client = _FakeSupabase(rows)
    found = fetch_atlas_row(client, "2026-04-21", "energy")
    assert found is not None
    assert found["document_key"] == "energy"
    assert fetch_atlas_row(client, date(2026, 4, 21), "missing-key") is None


@pytest.mark.unit
def test_ingest_atlas_document_via_client_then_search() -> None:
    """End-to-end: fetch via fake Supabase → ingest → MCP search returns the doc."""
    rows = [
        _make_atlas_row(
            document_key="macro",
            iso_date="2026-04-21",
            doc_type=None,
            segment="macro",
            content="Global macro: rates are pricing two cuts by year-end.",
        )
    ]
    client = _FakeSupabase(rows)

    result = ingest_atlas_document(client, "2026-04-21", "macro")
    assert result is not None
    assert result.document_key == "macro"
    assert result.chunks_created >= 1

    hits = search_strategies(
        query="macro",
        top_k=5,
        segment="macro",
        date_from_ymd=20260420,
    )
    assert hits
    assert any(h["metadata"]["document_key"] == "macro" for h in hits)


@pytest.mark.unit
def test_ingest_atlas_document_returns_none_when_row_missing() -> None:
    """Late triggers / publish failures → the indexer skips, doesn't raise."""
    client = _FakeSupabase(rows=[])
    assert ingest_atlas_document(client, "2026-04-21", "missing-doc") is None
    # Index stays empty.
    assert not _stub_index.get(ATLAS_INDEX_NAME)
