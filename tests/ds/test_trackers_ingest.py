"""Unit tests for the digisearch congress-trades refusal ([DIG-1307](/DIG/issues/DIG-1307)).

CTO disposition on [DIG-1291](/DIG/issues/DIG-1291) (i) is REFUSED: the
congressional trade-level feed is not distributable as an indexed record, so
digisearch must refuse the whole path. The refusal is **deny-only and
fail-closed** — the code constant refuses `congress-trades` unconditionally and
`DIGISEARCH_REFUSED_FEEDS` can only *widen* the refused set. No value of that
env var may ever permit the feed, and a missing/empty/unparseable value must
never lift the refusal.

These tests are the contract. They were committed by the EM before the leaf was
assigned and must not be edited by the implementer.

Still covered here: `normalize_congress_trade` stays a pure row→payload mapper
(no I/O, no fetch, no index write), so its behaviour is pinned unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from digisearch.search._stub import _stub_index
from digisearch.trackers_ingest import (
    TRACKERS_INDEX_NAME,
    RefusedDatasetError,
    check_manifest_not_stale,
    fetch_congress_trades_latest,
    ingest_congress_trade,
    ingest_congress_trades,
    normalize_congress_trade,
)

from digisearch import trackers_ingest as congress

#: Every shape a legal ``DIGISEARCH_REFUSED_FEEDS`` value can take, including
#: the ones an operator would try in order to *permit* the feed again. All of
#: them must leave the refusal standing.
LEGAL_REFUSAL_ENV_VALUES: tuple[str, ...] = (
    "",
    "   ",
    "congress-trades",
    "CONGRESS-TRADES",
    "congress_trades",
    "insider-transactions",
    "all",
    "*",
    "none",
    "0",
    "false",
    "allow",
    "permit",
    "\x1b[31m{}[],; garbage",
)

# --- Golden row (live schema, congress/trades/latest.json, 2026-09-30) --------

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

#: Manifest that would (before the refusal) have let the ingest through.
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

    def __init__(
        self,
        rows: list[dict[str, Any]],
        manifest: dict[str, Any] | None = None,
    ) -> None:
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
    installed in this env, so the Chonkie backends raise ImportError here.
    Also drops ``DIGISEARCH_REFUSED_FEEDS`` so each test starts from the
    code-constant-only refusal.
    """
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    monkeypatch.delenv("DIGISEARCH_REFUSED_FEEDS", raising=False)
    _stub_index.pop(TRACKERS_INDEX_NAME, None)
    yield
    _stub_index.pop(TRACKERS_INDEX_NAME, None)


# --- Refusal: the whole congress-trades path is closed ----------------------


@pytest.mark.unit
def test_fetch_congress_trades_latest_refuses_before_transport() -> None:
    """The fetch boundary refuses without ever touching the transport."""
    fetcher = _FakeFetcher([_TICKER_ROW])
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        fetch_congress_trades_latest(fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"


@pytest.mark.unit
def test_ingest_congress_trade_refuses_single_row() -> None:
    """The single-row entry point refuses and writes nothing."""
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trade(_TICKER_ROW)
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
def test_ingest_congress_trades_refuses_bulk_before_transport() -> None:
    """The bulk entry point refuses before fetching and writes nothing."""
    fetcher = _FakeFetcher([_TICKER_ROW, _NULL_TICKER_BOND_ROW])
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trades(fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
def test_check_manifest_not_stale_refuses_congress_trades_dataset() -> None:
    """No path reaches the ``congress-trades`` dataset, manifest read included.

    ``check_manifest_not_stale`` defaults to ``CONGRESS_TRADES_DATASET``, so it
    is a live path into the refused dataset and must refuse on its default.
    Wave-2 calls it with its own (non-refused) dataset and must keep working.
    """
    fetcher = _FakeFetcher([_TICKER_ROW])
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        check_manifest_not_stale(fetcher)
    assert fetcher.calls == []
    # A non-refused dataset is untouched by the refusal.
    wave2_fetcher = _FakeFetcher([_TICKER_ROW])
    assert check_manifest_not_stale(wave2_fetcher, dataset="short-volume") == _MANIFEST_OK
    assert wave2_fetcher.calls


@pytest.mark.unit
@pytest.mark.parametrize("raw", LEGAL_REFUSAL_ENV_VALUES)
def test_entry_points_refused_under_every_legal_env_value(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """``DIGISEARCH_REFUSED_FEEDS`` can only widen the refused set.

    Deny-only: a value that names the refused dataset, a wildcard, a
    permission-sounding token, or garbage all leave the refusal standing.
    """
    monkeypatch.setenv("DIGISEARCH_REFUSED_FEEDS", raw)
    fetcher = _FakeFetcher([_TICKER_ROW])

    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        fetch_congress_trades_latest(fetcher)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        check_manifest_not_stale(fetcher)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trade(_TICKER_ROW)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trades(fetcher)
    assert fetcher.calls == []
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
def test_entry_points_refused_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing env var → refused (fail-closed, never fail-open)."""
    monkeypatch.delenv("DIGISEARCH_REFUSED_FEEDS", raising=False)
    fetcher = _FakeFetcher([_TICKER_ROW])

    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        fetch_congress_trades_latest(fetcher)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        check_manifest_not_stale(fetcher)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trade(_TICKER_ROW)
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trades(fetcher)
    assert fetcher.calls == []


@pytest.mark.unit
def test_module_docstring_no_longer_documents_the_parsed_filing_schema() -> None:
    """The module docstring must not present the filing row as an indexed record.

    Documenting the parsed schema is a reintroduction path: the next reader
    copies it into a new adapter.
    """
    doc = congress.__doc__ or ""
    for leaked in ("bioguideId", "amountRange", "rowIndex", "docId"):
        assert leaked not in doc, f"module docstring still documents {leaked!r}"


@pytest.mark.unit
def test_fetch_boundary_refuses_url_fragment_on_any_host() -> None:
    """The fetch boundary itself refuses a refused URL, whatever the host.

    Repointing the feed constant at another aggregator relocates the violation
    rather than resolving it, so the fragment denylist must still refuse — and
    must refuse before the transport is touched. Added by the implementer:
    DIG-1329 requires this guard and no other test in the suite reaches it.
    """
    repointed = "https://aggregator.invalid/mirror/congress/trades/latest.json"
    assert "/congress/trades/" in congress.CODE_REFUSED_URL_FRAGMENTS
    fetcher = _FakeFetcher([_TICKER_ROW])
    with pytest.raises(RefusedDatasetError) as excinfo:
        congress._fetch_feed_json(repointed, fetcher, congress.TRACKERS_ALLOWED_HOSTS)
    assert repointed in str(excinfo.value), "refusal must name the offending url"
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    # A non-refused feed url on the allowlisted host is untouched.
    ok_url = "https://raw.githubusercontent.com/LuxAlgo/market-trackers-data/main/insider/x.json"
    ok_fetcher = _FakeFetcher([_TICKER_ROW])
    congress._fetch_feed_json(ok_url, ok_fetcher, congress.TRACKERS_ALLOWED_HOSTS)
    assert ok_fetcher.calls == [ok_url]


# --- Unchanged behaviour: the pure row→payload mapper -----------------------


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
