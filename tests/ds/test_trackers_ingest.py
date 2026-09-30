"""Unit tests for luxalgo market-trackers-data congress-trades ingest (#4826).

Covers the spike: fetch (mocked transport — no live HTTP) → normalize →
``index_chunks`` into a dedicated ``trackers`` stub index with deterministic
ids, so re-ingest is a no-op. Golden rows are copied from the live
``congress/trades/latest.json`` schema (verified 2026-09-30): one stock row
with a ticker, one null-ticker bond row (must be ingested, never dropped
silently).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from digisearch.search._stub import _stub_index
from digisearch.trackers_ingest import (
    TRACKERS_INDEX_NAME,
    StaleDatasetError,
    fetch_congress_trades_latest,
    ingest_congress_trades,
    normalize_congress_trade,
)

# --- Golden rows (live schema, congress/trades/latest.json, 2026-09-30) --------

_TICKER_ROW: dict[str, Any] = {
    "id": "senate:f8d003c0-ca1e-4c39-9d66-632d220180e1:1",
    "chamber": "senate",
    "docId": "f8d003c0-ca1e-4c39-9d66-632d220180e1",
    "rowIndex": 1,
    "member": {
        "name": "Sheldon Whitehouse",
        "bioguideId": "W000802",
        "party": "Democrat",
        "state": "RI",
    },
    "filedAt": "2026-09-02",
    "transactedAt": "2026-08-13",
    "ticker": "NVDA",
    "assetDescription": "NVIDIA Corporation - Common Stock",
    "assetType": "stock",
    "side": "sell",
    "amountRange": {"min": 15001, "max": 50000, "text": "$15,001 - $50,000"},
    "owner": "self",
    "provenance": {
        "source": "senate-efd",
        "sourceUrl": "https://efdsearch.senate.gov/search/view/ptr/"
        "f8d003c0-ca1e-4c39-9d66-632d220180e1/",
        "retrievedAt": "2026-09-08T02:38:37.383Z",
        "parser": "efd-ptr-html@1",
        "confidence": 0.9,
        "needsReview": False,
    },
}

_NULL_TICKER_BOND_ROW: dict[str, Any] = {
    "id": "senate:257795ae-e1b2-411d-b562-8fe4c2a4f2a1:15",
    "chamber": "senate",
    "docId": "257795ae-e1b2-411d-b562-8fe4c2a4f2a1",
    "rowIndex": 15,
    "member": {
        "name": "David H McCormick",
        "bioguideId": "M001243",
        "party": "Republican",
        "state": "PA",
    },
    "filedAt": "2026-08-27",
    "transactedAt": "2026-07-31",
    "ticker": None,
    "assetDescription": "PENNSYLVANIA ST TPK COMMN OIL REV Rate/Coupon: 5% Matures: 2026-12-01",
    "assetType": "bond",
    "side": "sell",
    "amountRange": {"min": 100001, "max": 250000, "text": "$100,001 - $250,000"},
    "owner": "spouse",
    "provenance": {
        "source": "senate-efd",
        "sourceUrl": "https://efdsearch.senate.gov/search/view/ptr/"
        "257795ae-e1b2-411d-b562-8fe4c2a4f2a1/",
        "retrievedAt": "2026-09-08T02:38:36.448Z",
        "parser": "efd-ptr-html@1",
        "confidence": 0.9,
        "needsReview": False,
    },
}

_MANIFEST_OK: dict[str, Any] = {
    "generatedAt": "2026-09-07T15:13:09.121Z",
    "schemaVersion": 2,
    "datasets": {
        "congress-trades": {
            "title": "Congressional trades",
            "exportDir": "congress/trades",
            "rows": 175,
            "stale": False,
        },
        "insider-transactions": {
            "title": "Insider transactions",
            "exportDir": "insider/transactions",
            "rows": 17499,
            "stale": False,
        },
    },
}


class _FakeFetchResult:
    """Minimal digifetch ``FetchResult`` surface (``.text`` only)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeFetcher:
    """Offline fetcher: serves canned JSON per URL, records calls."""

    def __init__(self, rows: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> None:
        self._rows = rows
        self._manifest = manifest if manifest is not None else _MANIFEST_OK
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FakeFetchResult:
        self.calls.append(url)
        if url.endswith("manifest.json"):
            return _FakeFetchResult(json.dumps(self._manifest))
        return _FakeFetchResult(json.dumps(self._rows))


@pytest.fixture(autouse=True)
def _isolate_trackers_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test stub index + legacy recursive chunker (no model download).

    ``DIGISEARCH_CHUNKER=recursive`` (not ``token``): ``chonkie`` is not
    installed in this env, so the Chonkie backends raise ImportError here —
    the same reason ``test_research_ingest.py`` fails in this env. The
    legacy recursive chunker needs no extra dependency.
    """
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    _stub_index.pop(TRACKERS_INDEX_NAME, None)
    yield
    _stub_index.pop(TRACKERS_INDEX_NAME, None)


@pytest.mark.unit
def test_normalize_congress_trade_maps_live_schema() -> None:
    """Live-schema row → {doc_id, text, metadata} with natural-key id."""
    norm = normalize_congress_trade(_TICKER_ROW)
    assert norm["doc_id"] == "senate:f8d003c0-ca1e-4c39-9d66-632d220180e1:1"
    meta = norm["metadata"]
    assert meta["ticker"] == "NVDA"
    assert meta["side"] == "sell"
    assert meta["amount_text"] == "$15,001 - $50,000"
    assert meta["transacted_at"] == "2026-08-13"
    assert meta["needs_review"] is False
    assert meta["origin"] == "luxalgo-trackers/congress-trades"
    assert meta["source_url"] == (
        "https://efdsearch.senate.gov/search/view/ptr/f8d003c0-ca1e-4c39-9d66-632d220180e1/"
    )
    assert "NVDA" in norm["text"]
    assert "Whitehouse" in norm["text"]


@pytest.mark.unit
def test_normalize_null_ticker_row_keeps_row() -> None:
    """Null-ticker bond row normalizes (ticker None) — never dropped silently."""
    norm = normalize_congress_trade(_NULL_TICKER_BOND_ROW)
    assert norm["doc_id"] == "senate:257795ae-e1b2-411d-b562-8fe4c2a4f2a1:15"
    assert norm["metadata"]["ticker"] is None
    assert "PENNSYLVANIA" in norm["text"]


@pytest.mark.unit
def test_normalize_requires_natural_key() -> None:
    """Rows missing chamber/docId/rowIndex raise before any side-effect."""
    with pytest.raises(ValueError):
        normalize_congress_trade({"chamber": "senate", "docId": "x"})
    with pytest.raises(ValueError):
        normalize_congress_trade({})


@pytest.mark.unit
def test_fetch_congress_trades_latest_uses_mocked_transport() -> None:
    """Fetch returns raw row dicts through the injected fetcher (no socket)."""
    rows = fetch_congress_trades_latest(_FakeFetcher([_TICKER_ROW]))
    assert rows == [_TICKER_ROW]


@pytest.mark.unit
def test_ingest_two_rows_then_reingest_is_idempotent() -> None:
    """First ingest writes 2 rows; replay writes nothing and duplicates nothing."""
    fetcher = _FakeFetcher([_TICKER_ROW, _NULL_TICKER_BOND_ROW])

    first = ingest_congress_trades(fetcher)
    assert first.ingested == 2
    assert first.skipped == 0
    assert first.source == "luxalgo-trackers/congress-trades"
    count_after_first = len(_stub_index[TRACKERS_INDEX_NAME])
    assert count_after_first >= 2

    # Null-ticker bond row landed with searchable content.
    bond_chunks = [
        c
        for c in _stub_index[TRACKERS_INDEX_NAME]
        if c.metadata.get("natural_key") == "senate:257795ae-e1b2-411d-b562-8fe4c2a4f2a1:15"
    ]
    assert bond_chunks, "null-ticker row must be ingested, not dropped"
    assert "ticker" not in bond_chunks[0].metadata

    # Every stored chunk carries the exact upstream source_url.
    for chunk in _stub_index[TRACKERS_INDEX_NAME]:
        assert chunk.metadata.get("source_url", "").startswith("https://efdsearch.senate.gov/")

    second = ingest_congress_trades(fetcher)
    assert second.ingested == 0
    assert second.skipped == 2
    assert len(_stub_index[TRACKERS_INDEX_NAME]) == count_after_first


@pytest.mark.unit
def test_ingest_refuses_stale_manifest() -> None:
    """A dataset flagged stale:true refuses before any chunk is written."""
    stale_manifest = {
        "datasets": {"congress-trades": {"stale": True, "rows": 175}},
    }
    fetcher = _FakeFetcher([_TICKER_ROW], manifest=stale_manifest)
    with pytest.raises(StaleDatasetError, match="[Ss]tale"):
        ingest_congress_trades(fetcher)
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
def test_ingest_skips_keyless_row_with_count() -> None:
    """A row without a natural key is counted as skipped, loudly — not silent."""
    fetcher = _FakeFetcher([_TICKER_ROW, {"ticker": "ORPHAN"}])
    result = ingest_congress_trades(fetcher)
    assert result.ingested == 1
    assert result.skipped == 1
