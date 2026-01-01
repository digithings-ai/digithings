"""Unit tests for luxalgo market-trackers-data wave-2 ingest (#4849).

DIG-1175 / DIG-959 leaf 15: all five wave-2 feeds are refused in code until
the client-side Art. 9 facts justify them, so the fetch → normalize →
``index_chunks`` path below is closed at every ingest entry point. What stays
live: the pure row→payload mapper (:func:`normalize_tracker_row`), pinned
unchanged, and the dataset order / unknown-key contracts.

Offline (mocked transport — no live HTTP): every ingest entry point must
raise :class:`RefusedDatasetError` naming the dataset before any URL is
fetched, and the ``trackers`` stub index stays empty. Golden rows are trimmed
copies of the live ``latest.json`` schemas (verified 2026-09-30); the two
synthetic rows (marked) exercise ticker paths the current upstream snapshots
never populate (13F ``ticker`` is always null from ``thirteenf-xml@1``;
short-volume always carries one).
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest
from digisearch.search._stub import _stub_index
from digisearch.trackers_ingest import (
    TRACKERS_INDEX_NAME,
    RefusedDatasetError,
)
from digisearch.trackers_wave2_ingest import (
    TRACKER_DATASET_ORDER,
    TRACKER_DATASETS,
    fetch_tracker_rows_latest,
    ingest_gov_contracts,
    ingest_insider_transactions,
    ingest_lobbying_filings,
    ingest_short_volume,
    ingest_thirteenf_holdings,
    ingest_tracker_dataset,
    normalize_tracker_row,
)

# --- Golden rows (live schemas, latest.json samples, 2026-09-30) ---------------

_INSIDER_TICKER_ROW: dict[str, Any] = {
    "id": "0000007536-26-000137:nd:0",
    "accessionNumber": "0000007536-26-000137",
    "formType": "4",
    "ticker": "ARW",
    "issuerCik": "0000007536",
    "issuerName": "ARROW ELECTRONICS, INC.",
    "insider": {"name": "Jean-Claude Carine Lamercie", "cik": "0001870985"},
    "transactedAt": "2026-09-03",
    "filedAt": "2026-09-04",
    "acquiredDisposed": "D",
    "shares": 1000,
    "pricePerShare": 209.85,
    "provenance": {
        "source": "edgar",
        "sourceUrl": "https://www.sec.gov/Archives/edgar/data/7536/0000007536-26-000137-index.htm",
        "retrievedAt": "2026-09-05T02:39:14.934Z",
        "parser": "form-ownership-xml@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_INSIDER_NULL_TICKER_ROW: dict[str, Any] = {
    "id": "0000123456-26-000001:d:0",
    "accessionNumber": "0000123456-26-000001",
    "formType": "3",
    "ticker": None,
    "issuerName": "PRIVATE HOLDINGS LLC",
    "insider": {"name": "Jane Q Insider", "cik": "0001999999"},
    "transactedAt": "2026-08-01",
    "filedAt": "2026-08-02",
    "acquiredDisposed": "A",
    "shares": 500,
    "pricePerShare": None,
    "provenance": {
        "source": "edgar",
        "sourceUrl": "https://www.sec.gov/Archives/edgar/data/123456/"
        "0000123456-26-000001-index.htm",
        "retrievedAt": "2026-09-05T02:39:14.934Z",
        "parser": "form-ownership-xml@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_THIRTEENF_NULL_TICKER_ROW: dict[str, Any] = {
    "id": "0000014745-26-000006:0",
    "accessionNumber": "0000014745-26-000006",
    "managerCik": "0000014745",
    "managerName": "BROWN, LISLE/CUMMINGS, INC.",
    "periodEnd": "2026-06-30",
    "filedAt": "2026-09-02",
    "cusip": "88579Y101",
    "ticker": None,
    "issuerName": "3M CO",
    "shares": 9829,
    "valueUsd": 1591359,
    "provenance": {
        "source": "edgar",
        "sourceUrl": "https://www.sec.gov/Archives/edgar/data/14745/0000014745-26-000006-index.htm",
        "retrievedAt": "2026-09-03T02:42:57.976Z",
        "parser": "thirteenf-xml@1",
        "confidence": 1,
        "needsReview": False,
    },
}

# Synthetic: upstream thirteenf-xml@1 never resolves CUSIP→ticker today, so no
# live ticker-bearing 13F row exists to copy. Shape mirrors the live row.
_THIRTEENF_TICKER_ROW: dict[str, Any] = {
    **_THIRTEENF_NULL_TICKER_ROW,
    "id": "0000014745-26-000006:1",
    "ticker": "MMM",
}

_SHORT_VOLUME_ROW: dict[str, Any] = {
    "id": "2026-09-04:A:CNMS",
    "date": "2026-09-04",
    "ticker": "A",
    "market": "CNMS",
    "shortVolume": 388208.245298,
    "shortExemptVolume": 1288,
    "totalVolume": 756283.190557,
    "shortRatio": 0.513311,
    "provenance": {
        "source": "finra",
        "sourceUrl": "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260904.txt",
        "retrievedAt": "2026-09-05T12:49:06.980Z",
        "parser": "finra-shortvol@1",
        "confidence": 1,
        "needsReview": False,
    },
}

# Synthetic: short-volume rows always carry a ticker upstream; this pins the
# null-ticker-kept contract for the mapper all the same.
_SHORT_VOLUME_NULL_TICKER_ROW: dict[str, Any] = {
    **_SHORT_VOLUME_ROW,
    "id": "2026-09-04:UNLISTED:OTC",
    "ticker": None,
    "market": "OTC",
}

_LOBBYING_TICKER_ROW: dict[str, Any] = {
    "id": "21ed6837-2081-4916-9299-32571264117e",
    "filingUuid": "21ed6837-2081-4916-9299-32571264117e",
    "registrant": {"name": "HUNTON ANDREWS KURTH LLP"},
    "client": {"name": "AMERICAN ELECTRIC POWER COMPANY, INC.", "tickers": ["AEP"]},
    "amountUsd": None,
    "filingYear": 2026,
    "filingPeriod": "third_quarter",
    "filingType": "RA",
    "issues": ["ENV"],
    "billReferences": [],
    "provenance": {
        "source": "lda",
        "sourceUrl": "https://lda.gov/filings/public/filing/"
        "21ed6837-2081-4916-9299-32571264117e/print/",
        "retrievedAt": "2026-09-07T15:12:19.471Z",
        "parser": "lda-filings@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_LOBBYING_NULL_TICKER_ROW: dict[str, Any] = {
    "id": "00ace018-e1b0-4b92-8135-5f2aec6486fd",
    "filingUuid": "00ace018-e1b0-4b92-8135-5f2aec6486fd",
    "registrant": {"name": "TALLEY STRATEGIES LLC"},
    "client": {"name": "LATITUDE ENERGY SERVICES LLC", "tickers": []},
    "amountUsd": 20000,
    "filingYear": 2026,
    "filingPeriod": "third_quarter",
    "filingType": "3T",
    "issues": ["TAX", "ENG"],
    "billReferences": [],
    "provenance": {
        "source": "lda",
        "sourceUrl": "https://lda.gov/filings/public/filing/"
        "00ace018-e1b0-4b92-8135-5f2aec6486fd/print/",
        "retrievedAt": "2026-09-07T15:12:19.471Z",
        "parser": "lda-filings@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_GOV_CONTRACT_TICKER_ROW: dict[str, Any] = {
    "id": "CONT_AWD_1232SA26F0543_12H2_1232SA26D0017_12H2",
    "awardId": "1232SA26F0543",
    "awardType": "DELIVERY ORDER",
    "agency": "Department of Agriculture",
    "subAgency": "Agricultural Research Service",
    "recipient": {
        "name": "PACIFIC BIOSCIENCES OF CALIFORNIA, INC",
        "uei": "CP22V46XYQK6",
        "tickers": ["PACB"],
    },
    "amountUsd": 149416.05,
    "actionDate": "2026-08-31",
    "description": "GBRU - REAGENTS SUPPORTING 24 ACQUISITIONS ON THE REVIO SYSTEM",
    "provenance": {
        "source": "usaspending",
        "sourceUrl": "https://www.usaspending.gov/award/"
        "CONT_AWD_1232SA26F0543_12H2_1232SA26D0017_12H2",
        "retrievedAt": "2026-09-07T15:11:27.557Z",
        "parser": "usaspending-awards@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_GOV_CONTRACT_NULL_TICKER_ROW: dict[str, Any] = {
    "id": "CONT_AWD_05GA0A26F0057_0559_NNG15SD74B_8000",
    "awardId": "05GA0A26F0057",
    "awardType": "DELIVERY ORDER",
    "agency": "Government Accountability Office",
    "subAgency": "GAO, Except Comptroller General",
    "recipient": {
        "name": "SOFTWARE INFORMATION RESOURCE CORP.",
        "uei": "EJJMMJHYDFH6",
        "tickers": [],
    },
    "amountUsd": 33842.56,
    "actionDate": "2026-09-01",
    "description": "SOFTWARE PROCUREMENT",
    "provenance": {
        "source": "usaspending",
        "sourceUrl": "https://www.usaspending.gov/award/"
        "CONT_AWD_05GA0A26F0057_0559_NNG15SD74B_8000",
        "retrievedAt": "2026-09-07T15:11:27.557Z",
        "parser": "usaspending-awards@1",
        "confidence": 1,
        "needsReview": False,
    },
}

_MANIFEST_OK: dict[str, Any] = {
    "generatedAt": "2026-09-07T15:13:09.121Z",
    "schemaVersion": 2,
    "datasets": {
        "insider-transactions": {"rows": 17499, "stale": False},
        "thirteenf-holdings": {"rows": 111207, "stale": False},
        "short-volume": {"rows": 122591, "stale": False},
        "lobbying-filings": {"rows": 56334, "stale": False},
        "gov-contracts": {"rows": 12694, "stale": False},
        "cot-reports": {"rows": 0, "stale": True},
    },
}

_CASES: dict[str, dict[str, Any]] = {
    "insider-transactions": {
        "ingest": ingest_insider_transactions,
        "ticker_row": _INSIDER_TICKER_ROW,
        "null_row": _INSIDER_NULL_TICKER_ROW,
        "ticker": "ARW",
        "source_host": "https://www.sec.gov/",
        "text_tokens": ("ARW", "Lamercie"),
    },
    "thirteenf-holdings": {
        "ingest": ingest_thirteenf_holdings,
        "ticker_row": _THIRTEENF_TICKER_ROW,
        "null_row": _THIRTEENF_NULL_TICKER_ROW,
        "ticker": "MMM",
        "source_host": "https://www.sec.gov/",
        "text_tokens": ("MMM", "BROWN"),
    },
    "short-volume": {
        "ingest": ingest_short_volume,
        "ticker_row": _SHORT_VOLUME_ROW,
        "null_row": _SHORT_VOLUME_NULL_TICKER_ROW,
        "ticker": "A",
        "source_host": "https://cdn.finra.org/",
        "text_tokens": ("CNMS",),
    },
    "lobbying-filings": {
        "ingest": ingest_lobbying_filings,
        "ticker_row": _LOBBYING_TICKER_ROW,
        "null_row": _LOBBYING_NULL_TICKER_ROW,
        "ticker": "AEP",
        "source_host": "https://lda.gov/",
        "text_tokens": ("AEP", "HUNTON"),
    },
    "gov-contracts": {
        "ingest": ingest_gov_contracts,
        "ticker_row": _GOV_CONTRACT_TICKER_ROW,
        "null_row": _GOV_CONTRACT_NULL_TICKER_ROW,
        "ticker": "PACB",
        "source_host": "https://www.usaspending.gov/",
        "text_tokens": ("PACB", "Agriculture"),
    },
}

_DATASET_IDS = sorted(_CASES)


class _FakeFetchResult:
    """Minimal digifetch ``FetchResult`` surface (``.text`` only)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeFetcher:
    """Offline fetcher: serves canned rows for one dataset + manifest."""

    def __init__(
        self,
        dataset: str,
        rows: list[dict[str, Any]],
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self._dataset = dataset
        self._rows = rows
        self._manifest = manifest if manifest is not None else _MANIFEST_OK
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FakeFetchResult:
        self.calls.append(url)
        if url.endswith("manifest.json"):
            return _FakeFetchResult(json.dumps(self._manifest))
        assert TRACKER_DATASETS[self._dataset].feed_url == url, f"unexpected feed {url!r}"
        return _FakeFetchResult(json.dumps(self._rows))


@pytest.fixture(autouse=True)
def _isolate_trackers_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test stub index + legacy recursive chunker (no model download)."""
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    _stub_index.pop(TRACKERS_INDEX_NAME, None)
    yield
    _stub_index.pop(TRACKERS_INDEX_NAME, None)


def _stale_manifest(dataset: str) -> dict[str, Any]:
    manifest = json.loads(json.dumps(_MANIFEST_OK))
    manifest["datasets"][dataset] = {"rows": 1, "stale": True}
    return manifest


@pytest.mark.unit
def test_dataset_order_matches_issue_sequence() -> None:
    """Wave-2 order is insider → 13F → short-volume → lobbying → gov-contracts."""
    assert TRACKER_DATASET_ORDER == (
        "insider-transactions",
        "thirteenf-holdings",
        "short-volume",
        "lobbying-filings",
        "gov-contracts",
    )
    assert set(TRACKER_DATASET_ORDER) == set(TRACKER_DATASETS)


@pytest.mark.unit
def test_unknown_dataset_rejected() -> None:
    """Unknown dataset keys fail fast (no silent misroute)."""
    with pytest.raises(ValueError, match="unknown tracker dataset"):
        ingest_tracker_dataset("cot-reports-typo", _FakeFetcher("insider-transactions", []))


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_normalize_maps_live_schema(dataset: str) -> None:
    """Ticker row → {doc_id, text, metadata} with natural-key id + source_url."""
    case = _CASES[dataset]
    row = case["ticker_row"]
    norm = normalize_tracker_row(dataset, row)
    assert norm["doc_id"] == f"{dataset}:{row['id']}"
    meta = norm["metadata"]
    assert meta["ticker"] == case["ticker"]
    assert meta["source_url"] == row["provenance"]["sourceUrl"]
    assert meta["origin"] == f"luxalgo-trackers/{dataset}"
    assert meta["natural_key"] == norm["doc_id"]
    assert meta["needs_review"] is False
    for token in case["text_tokens"]:
        assert token in norm["text"]


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_normalize_null_ticker_row_keeps_row(dataset: str) -> None:
    """Null-ticker row normalizes (ticker None) — never dropped silently."""
    case = _CASES[dataset]
    row = case["null_row"]
    norm = normalize_tracker_row(dataset, row)
    assert norm["doc_id"] == f"{dataset}:{row['id']}"
    assert norm["metadata"]["ticker"] is None
    assert norm["text"]


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_normalize_requires_upstream_id(dataset: str) -> None:
    """Rows without an upstream id raise before any side-effect."""
    with pytest.raises(ValueError):
        normalize_tracker_row(dataset, {"ticker": "ORPHAN"})
    with pytest.raises(ValueError):
        normalize_tracker_row(dataset, {})


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_fetch_refuses_before_transport(dataset: str) -> None:
    """DIG-1175: fetch refuses naming the dataset; transport untouched."""
    case = _CASES[dataset]
    fetcher = _FakeFetcher(dataset, [case["ticker_row"]])
    with pytest.raises(RefusedDatasetError, match=dataset):
        fetch_tracker_rows_latest(dataset, fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_ingest_wrappers_refuse_before_transport(dataset: str) -> None:
    """DIG-1175: per-dataset wrappers refuse; nothing is written."""
    case: dict[str, Any] = _CASES[dataset]
    ingest: Callable[..., Any] = case["ingest"]
    fetcher = _FakeFetcher(dataset, [case["ticker_row"], case["null_row"]])
    with pytest.raises(RefusedDatasetError, match=dataset):
        ingest(fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_ingest_dataset_refuses_before_transport(dataset: str) -> None:
    """DIG-1175: the generic bulk entry point refuses; nothing is written."""
    case = _CASES[dataset]
    fetcher = _FakeFetcher(dataset, [case["ticker_row"], case["null_row"]])
    with pytest.raises(RefusedDatasetError, match=dataset):
        ingest_tracker_dataset(dataset, fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_refusal_takes_precedence_over_stale_manifest(dataset: str) -> None:
    """DIG-1175: refusal fires before the freshness check, stale or not."""
    case = _CASES[dataset]
    fetcher = _FakeFetcher(dataset, [case["ticker_row"]], manifest=_stale_manifest(dataset))
    with pytest.raises(RefusedDatasetError, match=dataset):
        case["ingest"](fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", _DATASET_IDS)
def test_keyless_row_still_refused_at_dataset_level(dataset: str) -> None:
    """DIG-1175: refusal is per-feed, so a keyless row never reaches counting."""
    case = _CASES[dataset]
    fetcher = _FakeFetcher(dataset, [case["ticker_row"], {"ticker": "ORPHAN"}])
    with pytest.raises(RefusedDatasetError, match=dataset):
        case["ingest"](fetcher)
    assert fetcher.calls == []
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
def test_all_five_wrappers_refuse() -> None:
    """DIG-1175: every named wrapper is closed — no feed has a live path."""
    for dataset in TRACKER_DATASET_ORDER:
        case = _CASES[dataset]
        fetcher = _FakeFetcher(dataset, [case["ticker_row"]])
        with pytest.raises(RefusedDatasetError, match=dataset):
            case["ingest"](fetcher)
        assert fetcher.calls == []
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


# DIG-1307: `test_congress_bulk_scans_stub_index_once` was removed here.
# The congress-trades path is now refused before any fetch, so the O(n) bulk
# key-scan it pinned is unreachable. The same perf pin stays covered by
# `test_wave2_bulk_scans_stub_index_once` below, which drives the identical
# `_natural_keys_in_index` memo through a dataset that is still live.


# DIG-1175: `test_wave2_bulk_scans_stub_index_once` was removed here.
# Bulk ingest is refused before any fetch, so the O(n) key-scan it pinned is
# unreachable — the same reasoning as the DIG-1307 removal above. If the feeds
# are ever re-opened with per-dataset Art. 9 clearance, the pin must be
# restored alongside the entry points.
