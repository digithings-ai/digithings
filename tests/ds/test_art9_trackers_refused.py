"""Unit tests for the trackers-feeds refusal ([DIG-1175](/DIG/issues/DIG-1175)).

Leaf 15 of the DIG-959 Art. 9 epic: the congress-trades feed and all five
wave-2 feeds stop ingesting until the client-side Art. 9 facts justify them.
Counsel recommended the refusal ([DIG-960](/DIG/issues/DIG-960)), spec S8
risk 5 records it as adopted, and the CEO confirmed it on DIG-959:
continuing to ingest Art. 9 data with no lawful basis is not a trade-off on
offer. These feeds carry named politicians' party affiliations and asset
holdings — political-opinion adjacent by construction — and v1 has no
free-text political-opinion detection, so screening field names cannot
reduce the risk.

Contract, one requirement per test:

1. Every ingest entry point refuses, naming the feed and the reason, and no
   chunk reaches ``index_chunks`` (stub index stays empty, transport
   untouched).
2. The refusal reason names the Art. 9 basis, so an operator reading a log
   knows this is a policy decision and not a bug.
3. A feed carrying no Art. 9 fields is *also* refused — the decision is about
   the feed, not about one payload.
4. The refusal is operator-visible where feed errors surface: it raises
   :class:`RefusedDatasetError`, never a fetch/stale error, and it precedes
   the manifest freshness check.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from digisearch.search._stub import _stub_index
from digisearch.trackers_ingest import (
    TRACKERS_INDEX_NAME,
    RefusedDatasetError,
    TrackersFetchError,
    fetch_congress_trades_latest,
    ingest_congress_trade,
)
from digisearch.trackers_wave2_ingest import (
    TRACKER_DATASET_ORDER,
    WAVE2_REFUSAL_BASIS,
    WAVE2_REFUSED_DATASETS,
    fetch_tracker_rows_latest,
    ingest_gov_contracts,
    ingest_insider_transactions,
    ingest_lobbying_filings,
    ingest_short_volume,
    ingest_thirteenf_holdings,
    ingest_tracker_dataset,
    ingest_tracker_row,
)

_WAVE2_WRAPPERS: dict[str, Callable[..., Any]] = {
    "insider-transactions": ingest_insider_transactions,
    "thirteenf-holdings": ingest_thirteenf_holdings,
    "short-volume": ingest_short_volume,
    "lobbying-filings": ingest_lobbying_filings,
    "gov-contracts": ingest_gov_contracts,
}

#: Values an operator might set trying (or pretending) to re-permit a feed.
#: None of them may lift the wave-2 refusal — there is no allow-list.
_PERMIT_ATTEMPTS: tuple[str, ...] = ("allow", "permit", "*", "none", "0", "")


class _FakeFetchResult:
    """Minimal ``FetchResult`` surface (``.text`` only)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeFetcher:
    """Offline fetcher that records every call (must stay empty)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        import json

        self._body = json.dumps(rows)
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FakeFetchResult:
        self.calls.append(url)
        return _FakeFetchResult(self._body)


@pytest.fixture(autouse=True)
def _isolate_trackers_index() -> Any:
    """Per-test stub index (refusals must leave it empty)."""
    _stub_index.pop(TRACKERS_INDEX_NAME, None)
    yield
    _stub_index.pop(TRACKERS_INDEX_NAME, None)


def _art9_laden_row(dataset: str) -> dict[str, Any]:
    """A row carrying Art. 9-adjacent content (party affiliation)."""
    return {
        "id": f"{dataset}-art9-row",
        "member": {"name": "Jane Doe", "party": "Democrat", "state": "CA"},
        "issues": ["taxation", "health"],
        "ticker": "ARW",
    }


def _art9_free_row(dataset: str) -> dict[str, Any]:
    """A row carrying no Art. 9 fields at all — still refused (req 3)."""
    return {"id": f"{dataset}-plain-row", "ticker": "ARW"}


@pytest.mark.unit
def test_refused_set_covers_every_wave2_dataset() -> None:
    """A dataset added to the order without being refused fails here.

    Fail-closed: the refused set must equal the dataset order, so a new
    feed arrives refused, never open.
    """
    assert set(WAVE2_REFUSED_DATASETS) == set(TRACKER_DATASET_ORDER)
    assert len(WAVE2_REFUSED_DATASETS) == 5


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
def test_fetch_refuses_before_transport(dataset: str) -> None:
    """Req 1: fetch refuses naming the feed; the transport is untouched."""
    fetcher = _FakeFetcher([_art9_laden_row(dataset)])
    with pytest.raises(RefusedDatasetError, match=dataset):
        fetch_tracker_rows_latest(dataset, fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
@pytest.mark.parametrize("row_kind", ["art9_laden", "art9_free"])
def test_ingest_row_refuses_whatever_the_payload_carries(dataset: str, row_kind: str) -> None:
    """Reqs 1+3: single-row ingest refuses Art. 9-laden AND Art. 9-free rows."""
    row = _art9_laden_row(dataset) if row_kind == "art9_laden" else _art9_free_row(dataset)
    with pytest.raises(RefusedDatasetError, match=dataset):
        ingest_tracker_row(dataset, row)
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
def test_ingest_dataset_refuses_before_transport(dataset: str) -> None:
    """Req 1: bulk ingest refuses before fetching; nothing is written."""
    fetcher = _FakeFetcher([_art9_laden_row(dataset), _art9_free_row(dataset)])
    with pytest.raises(RefusedDatasetError, match=dataset):
        ingest_tracker_dataset(dataset, fetcher)
    assert fetcher.calls == [], "refusal must happen before any URL is fetched"
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
def test_per_dataset_wrappers_refuse(dataset: str) -> None:
    """Req 1: every named wrapper is closed, not just the generic entry."""
    fetcher = _FakeFetcher([_art9_laden_row(dataset)])
    with pytest.raises(RefusedDatasetError, match=dataset):
        _WAVE2_WRAPPERS[dataset](fetcher)
    assert fetcher.calls == []
    assert not _stub_index.get(TRACKERS_INDEX_NAME)


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
def test_refusal_names_the_art9_basis(dataset: str) -> None:
    """Req 2: the reason names the Art. 9 basis — policy, not a bug."""
    with pytest.raises(RefusedDatasetError, match="Art. 9"):
        ingest_tracker_dataset(dataset, _FakeFetcher([]))
    with pytest.raises(RefusedDatasetError, match="DIG-959"):
        fetch_tracker_rows_latest(dataset, _FakeFetcher([]))
    assert "Art. 9" in WAVE2_REFUSAL_BASIS
    assert "DIG-959" in WAVE2_REFUSAL_BASIS


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
def test_refusal_is_not_a_fetch_problem(dataset: str) -> None:
    """Req 4: refusal is its own error — never a fetch/stale error."""
    assert not issubclass(RefusedDatasetError, TrackersFetchError)
    with pytest.raises(RefusedDatasetError):
        ingest_tracker_dataset(dataset, _FakeFetcher([]))


@pytest.mark.unit
@pytest.mark.parametrize("dataset", TRACKER_DATASET_ORDER)
@pytest.mark.parametrize("raw", _PERMIT_ATTEMPTS)
def test_no_env_value_permits_a_wave2_feed(
    monkeypatch: pytest.MonkeyPatch, dataset: str, raw: str
) -> None:
    """There is no allow-list: no env value lifts the wave-2 refusal."""
    monkeypatch.setenv("DIGISEARCH_REFUSED_FEEDS", raw)
    with pytest.raises(RefusedDatasetError, match=dataset):
        ingest_tracker_dataset(dataset, _FakeFetcher([]))
    monkeypatch.delenv("DIGISEARCH_REFUSED_FEEDS", raising=False)
    with pytest.raises(RefusedDatasetError, match=dataset):
        fetch_tracker_rows_latest(dataset, _FakeFetcher([]))


@pytest.mark.unit
def test_congress_trades_still_refuses() -> None:
    """Both feeds are closed: the congress-trades half holds beside wave-2."""
    fetcher = _FakeFetcher([{"id": "x"}])
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        fetch_congress_trades_latest(fetcher)
    assert fetcher.calls == []
    with pytest.raises(RefusedDatasetError, match="congress-trades"):
        ingest_congress_trade({"id": "x", "chamber": "senate"})
    assert not _stub_index.get(TRACKERS_INDEX_NAME)
