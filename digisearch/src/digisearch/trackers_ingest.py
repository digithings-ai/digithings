"""digisearch trackers adapter — the congress-trades path is refused here.

Counsel on DIG-1291 refused item (i) and the CTO disposition is REFUSED:
congressional transaction data, parsed under 5 U.S.C. 13105(l), must not be
fetched, indexed or served from a client-queryable digisearch index. This
module therefore closes the ``congress-trades`` fetch and ingest path **in
code**. No function here can reach :data:`CONGRESS_TRADES_URL`, and the parsed
filing shape is deliberately no longer documented here: documenting an indexed
record is how the next adapter gets written back into existence.

Refusal shape (DIG-1057 Q5): ``refused = CODE_CONSTANT ∪ ENV_DENYLIST``, and it
is deny-only and fail-closed. :data:`CODE_REFUSED_DATASETS` refuses
unconditionally; ``DIGISEARCH_REFUSED_FEEDS`` (:data:`REFUSAL_DENYLIST_ENV_VAR`)
can only *widen* the refused set. No value of that variable — ``allow``,
``permit``, ``*``, ``none``, ``0``, an empty string or garbage — ever permits a
refused feed, and a missing or unparseable value leaves the code constant
standing. There is deliberately no allow-list, no subtraction and no override:
CC0 is not a distribution right, and 5 U.S.C. 13107(c) is not a copyright right
a private party can waive.

What survives the refusal: :func:`normalize_congress_trade` stays a pure
in-memory row→payload mapper with no I/O, no fetch and no index write, so it is
not a way back in.

Not refused: the five wave-2 datasets (``insider-transactions``,
``thirteenf-holdings``, ``short-volume``, ``lobbying-filings``,
``gov-contracts``) in :mod:`digisearch.trackers_wave2_ingest` — scope item 3
enumerates congress-trades only. digisearch keeps its own denylist constant and
does not import digiquant; two independent constants beat one coupled one.

Network: all HTTP still goes through
:func:`digisearch.pipeline.url_ingest.fetch_json_feed` — the single URL-fetch
site (SSRF-guarded digifetch ``HttpFetcher`` via ``validate_fetch_url``).
This module never opens sockets itself and never fetches URLs directly.
``digifetch``/``url_ingest`` are imported lazily so importing this module
never requires the extra.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from digisearch.chunking.factory import get_document_chunker
from digisearch.core.evidence_metadata import (
    merge_document_metadata_into_chunks,
    normalize_metadata_for_chroma,
)
from digisearch.core.models import Document
from digisearch.ingestion.chunkers.base import Chunker
from digisearch.pipeline.ingest import index_chunks
from digisearch.research_ingest import _stable_doc_id
from digisearch.search._stub import _stub_index

logger = logging.getLogger(__name__)


#: Refused feed URL. Retained as an *identifier* only: every fetch path refuses
#: before this URL can be dialled (see :func:`_assert_url_not_refused`), so it is
#: never a live source. CC0 is not a distribution right.
CONGRESS_TRADES_URL: str = (
    "https://raw.githubusercontent.com/LuxAlgo/market-trackers-data"
    "/main/congress/trades/latest.json"
)

#: Dataset index: freshness flags per dataset (``datasets`` → ``stale``).
TRACKERS_MANIFEST_URL: str = (
    "https://raw.githubusercontent.com/LuxAlgo/market-trackers-data/main/manifest.json"
)

#: Dataset key inside the manifest ``datasets`` mapping.
CONGRESS_TRADES_DATASET: str = "congress-trades"

#: Host allowlist for the SSRF guard. Listing the feed host explicitly skips
#: DNS resolution in ``validate_fetch_url`` (offline-safe validation).
TRACKERS_ALLOWED_HOSTS: tuple[str, ...] = ("raw.githubusercontent.com",)

#: Origin tag carried on every chunk from this adapter.
TRACKERS_ORIGIN: str = "luxalgo-trackers/congress-trades"

#: Default index name for tracker rows. Override with
#: ``DIGISEARCH_TRACKERS_INDEX``. Kept separate from the research ``atlas``
#: index so the primary-source layer stays queryable beside Gloomberg.
TRACKERS_INDEX_NAME: str = os.environ.get("DIGISEARCH_TRACKERS_INDEX", "trackers")

# --- Refusal (DIG-1291 (i) REFUSED / DIG-1307) --------------------------------
#
# Shape: ``refused = CODE_CONSTANT ∪ ENV_DENYLIST``. Deny-only, fail-closed.
# ``DIGISEARCH_REFUSED_FEEDS`` can widen the refused set and nothing else — it
# is never an allow-list and never an override, and it can never subtract from
# the code constant.

#: Env var holding *additional* refused dataset names. Extra denylist only.
REFUSAL_DENYLIST_ENV_VAR: str = "DIGISEARCH_REFUSED_FEEDS"

#: Datasets refused unconditionally by code. Never derived from the environment.
CODE_REFUSED_DATASETS: frozenset[str] = frozenset({CONGRESS_TRADES_DATASET})

#: URL fragments refused unconditionally. Repointing :data:`CONGRESS_TRADES_URL`
#: at another aggregator relocates the violation; it does not lift it.
CODE_REFUSED_URL_FRAGMENTS: tuple[str, ...] = ("/congress/trades/",)


class StaleDatasetError(RuntimeError):
    """The upstream manifest flags this dataset ``stale`` — ingest refused."""


class TrackersFetchError(RuntimeError):
    """Fetch/validation/shape failure for the trackers feed.

    Raised for unreachable manifests, unvalidated URLs, non-JSON bodies, and
    row-list shape violations — never for a genuine ``stale: true`` flag
    (that stays :class:`StaleDatasetError`).
    """


class TrackersIngestResult(BaseModel):
    """Outcome of one trackers ingest run."""

    model_config = ConfigDict(extra="forbid")

    ingested: int = Field(ge=0)
    skipped: int = Field(ge=0)
    source: str = TRACKERS_ORIGIN


class RefusedDatasetError(RuntimeError):
    """A refused dataset or URL was reached — the call is denied, not degraded.

    Raised before any transport, index write or shape validation happens. It is
    not a :class:`TrackersFetchError`: a refused feed never becomes a fetch
    problem, and callers must not catch it and carry on.
    """


def refused_datasets() -> set[str]:
    """Every dataset name refused right now: code constant ∪ env tokens.

    Reads :data:`REFUSAL_DENYLIST_ENV_VAR` on every call (no import-time
    snapshot, so a test or a deployment can widen the set at runtime) and splits
    it on ``[,\\s]+``, lowercases the tokens and drops the empty ones.

    Deny-only by construction: the union is one-directional, so the env list can
    only add names. A missing, empty or unparseable value yields exactly
    :data:`CODE_REFUSED_DATASETS` — still refused, never fail-open.
    """
    raw = os.environ.get(REFUSAL_DENYLIST_ENV_VAR) or ""
    tokens = {token.lower() for token in re.split(r"[,\s]+", raw) if token}
    return set(CODE_REFUSED_DATASETS) | tokens


def _assert_not_refused(dataset: str) -> None:
    """Raise :class:`RefusedDatasetError` when *dataset* is refused."""
    if dataset in refused_datasets():
        raise RefusedDatasetError(
            f"dataset {dataset!r} is refused by policy (DIG-1291 (i) REFUSED) "
            f"— no fetch, no ingest, no substitute feed"
        )


def _assert_url_not_refused(url: str) -> None:
    """Raise :class:`RefusedDatasetError` when *url* hits a refused fragment.

    Second line of defence behind :func:`_assert_not_refused`: repointing a
    feed constant at another aggregator relocates the violation, and this must
    still refuse. The fetch boundary is the single choke point every feed in
    digisearch goes through, so this covers callers that never name a dataset.
    """
    for fragment in CODE_REFUSED_URL_FRAGMENTS:
        if fragment in url:
            raise RefusedDatasetError(
                f"fetch refused: url {url!r} matches refused feed "
                f"{CONGRESS_TRADES_DATASET!r} (fragment {fragment!r}) — "
                f"no fetch, no ingest, no substitute feed"
            )


class _FetcherLike(Protocol):
    """Minimal fetch surface this module needs (duck-typed onto HttpFetcher)."""

    def fetch(self, url: str) -> Any:
        """GET *url* and return the decoded body (``.text`` is all we read)."""
        ...


def _fetch_feed_json(
    url: str,
    fetcher: _FetcherLike | None,
    allowed_hosts: tuple[str, ...],
) -> Any:
    """Fetch + JSON-decode via ``pipeline.url_ingest`` (the only fetch site).

    The single choke point every trackers fetch goes through, and therefore the
    single fetch boundary the refusal is enforced at: a refused URL fragment
    raises :class:`RefusedDatasetError` here, before the fetcher is touched.

    Maps :class:`UrlFetchError` onto :class:`TrackersFetchError` so callers
    can distinguish transport problems from a genuine stale flag.
    """
    _assert_url_not_refused(url)

    from digisearch.pipeline.url_ingest import UrlFetchError, fetch_json_feed

    try:
        return fetch_json_feed(url, fetcher=fetcher, allowed_hosts=allowed_hosts)
    except UrlFetchError as exc:
        raise TrackersFetchError(f"trackers fetch failed for {url!r}: {exc}") from exc


def _manifest_dataset_entry(
    manifest: Any,
    dataset: str = CONGRESS_TRADES_DATASET,
) -> Mapping[str, Any] | None:
    """*dataset* entry of the manifest ``datasets`` section, any shape.

    Returns ``None`` when the manifest has no entry for this dataset, so a
    manifest reshape degrades to warn-and-proceed rather than blocking ingest
    or passing a stale flag silently.
    """
    datasets: Any = None
    if isinstance(manifest, Mapping):
        datasets = manifest.get("datasets")
    if isinstance(datasets, Mapping):
        entry = datasets.get(dataset)
        return entry if isinstance(entry, Mapping) else None
    if isinstance(datasets, list):
        for entry in datasets:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name") or entry.get("id") or entry.get("dataset")
            if name == dataset:
                return entry
    return None


def _manifest_dataset_stale(manifest: Any, dataset: str = CONGRESS_TRADES_DATASET) -> bool | None:
    """Return the ``stale`` flag for *dataset*, or ``None`` when unknown.

    Handles the verified manifest shape (``{"datasets": {name: {...}}}``) and
    degrades to ``None`` — warn-and-proceed — for anything else, so a manifest
    reshape never silently blocks ingest nor silently passes a stale flag.
    """
    entry = _manifest_dataset_entry(manifest, dataset)
    if entry is not None and "stale" in entry:
        return bool(entry.get("stale"))
    return None


def _manifest_expected_rows(manifest: Any, dataset: str = CONGRESS_TRADES_DATASET) -> int | None:
    """Manifest-declared row count for *dataset*, or ``None`` unknown."""
    entry = _manifest_dataset_entry(manifest, dataset)
    rows = entry.get("rows") if entry is not None else None
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        return None
    return rows


def check_manifest_not_stale(
    fetcher: _FetcherLike | None = None,
    *,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
    dataset: str = CONGRESS_TRADES_DATASET,
) -> Any | None:
    """Refuse ingest when the manifest flags *dataset* ``stale``.

    A missing/unreachable/unparseable manifest warns and proceeds (advisory
    signal); an explicit ``stale: true`` raises :class:`StaleDatasetError`.
    Returns the parsed manifest (``None`` when unreadable) so callers can
    reuse it — e.g. the row-count check — without a second fetch.

    Refusal is checked **first** and independently of freshness: this function
    defaults to :data:`CONGRESS_TRADES_DATASET`, so it is itself a live path
    into a refused dataset. Wave-2 callers pass their own (non-refused) dataset
    and are unaffected.
    """
    _assert_not_refused(dataset)

    try:
        manifest = _fetch_feed_json(TRACKERS_MANIFEST_URL, fetcher, allowed_hosts)
    except TrackersFetchError as exc:
        logger.warning(
            "trackers manifest unreadable — proceeding without freshness check",
            extra={
                "operation": "check_manifest_not_stale",
                "outcome": "degraded",
                "error": str(exc),
            },
        )
        return None
    stale = _manifest_dataset_stale(manifest, dataset)
    if stale is True:
        raise StaleDatasetError(
            f"dataset {dataset!r} flagged stale in {TRACKERS_MANIFEST_URL} — ingest refused"
        )
    if stale is None:
        logger.warning(
            f"trackers manifest has no freshness entry for {dataset} — proceeding",
            extra={"operation": "check_manifest_not_stale", "outcome": "degraded"},
        )
    return manifest


def fetch_congress_trades_latest(
    fetcher: _FetcherLike | None = None,
    *,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> list[dict[str, Any]]:
    """Always refuses — the congress-trades snapshot is not distributable.

    Raises :class:`RefusedDatasetError` as the first statement, before any
    transport. The body below is kept only so a future, separately-cleared feed
    has its shape handling one edit away; it is unreachable today and no
    environment value reaches it.
    """
    _assert_not_refused(CONGRESS_TRADES_DATASET)

    payload = _fetch_feed_json(CONGRESS_TRADES_URL, fetcher, allowed_hosts)
    url = CONGRESS_TRADES_URL
    if isinstance(payload, list):
        rows: list[Any] = payload
    elif isinstance(payload, Mapping):
        rows = []
        for key in ("trades", "rows", "data"):
            if isinstance(payload.get(key), list):
                rows = list(payload[key])
                break
        else:
            raise TrackersFetchError(
                f"trackers feed at {url!r} has no row list (keys: {sorted(payload)})"
            )
    else:
        raise TrackersFetchError(
            f"trackers feed at {url!r} returned {type(payload).__name__}, not a row list"
        )
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            out.append(dict(row))
        else:
            logger.warning(
                "trackers feed row is not an object — counted as skipped at ingest",
                extra={
                    "operation": "fetch_congress_trades_latest",
                    "outcome": "skipped",
                    "row_type": type(row).__name__,
                },
            )
    return out


def _natural_key(row: Mapping[str, Any]) -> str:
    """Natural-key id ``{chamber}:{docId}:{rowIndex}`` (raises when incomplete)."""
    chamber = row.get("chamber")
    doc_id = row.get("docId")
    row_index = row.get("rowIndex")
    if chamber is None or chamber == "" or doc_id is None or doc_id == "":
        raise ValueError("congress-trade row requires non-empty 'chamber' and 'docId'")
    if row_index is None or (isinstance(row_index, str) and not row_index.strip()):
        raise ValueError("congress-trade row requires 'rowIndex'")
    return f"{chamber}:{doc_id}:{row_index}"


def _trade_text(row: Mapping[str, Any], member_name: str, ticker: str | None) -> str:
    """One deterministic human-readable line per trade (chunk content)."""
    member = row.get("member")
    party = member.get("party") if isinstance(member, Mapping) else None
    state = member.get("state") if isinstance(member, Mapping) else None
    affiliation = f" ({party[0]}-{state})" if party and state else (f" ({state})" if state else "")
    asset = str(ticker) if ticker else str(row.get("assetDescription") or "unspecified asset")
    amount = row.get("amountRange")
    amount_text = (
        amount.get("text") if isinstance(amount, Mapping) and amount.get("text") else "amount n/a"
    )
    owner = row.get("owner") or "owner n/a"
    transacted = row.get("transactedAt") or "date n/a"
    filed = row.get("filedAt") or "date n/a"
    side = str(row.get("side") or "n/a")
    asset_type = str(row.get("assetType") or "n/a")
    return (
        f"{row.get('chamber')}: {member_name}{affiliation} {side} {asset} "
        f"({asset_type}) — {amount_text} "
        f"(owner: {owner}, transacted {transacted}, filed {filed})"
    )


def normalize_congress_trade(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one LuxAlgo congress-trade row to ``{doc_id, text, metadata}``.

    ``doc_id`` is the natural key ``{chamber}:{docId}:{rowIndex}``.
    ``metadata`` carries the canonical ``source_url`` (upstream
    ``provenance.sourceUrl``), the plan's tracker keys, plus lineage keys.
    Null tickers stay ``None`` (dropped later by Chroma normalization) — the
    row itself is always kept.
    """
    key = _natural_key(row)
    provenance = row.get("provenance")
    prov = provenance if isinstance(provenance, Mapping) else {}
    source_url = prov.get("sourceUrl") or CONGRESS_TRADES_URL
    member = row.get("member")
    member_map = member if isinstance(member, Mapping) else {}
    member_name = str(member_map.get("name") or "unknown member")
    ticker = row.get("ticker")
    ticker = str(ticker) if ticker is not None and str(ticker).strip() else None
    amount = row.get("amountRange")
    amount_text = (
        str(amount.get("text"))
        if isinstance(amount, Mapping) and amount.get("text") is not None
        else None
    )

    metadata: dict[str, Any] = {
        "source_url": str(source_url),
        "ticker": ticker,
        "side": row.get("side"),
        "amount_text": amount_text,
        "transacted_at": row.get("transactedAt"),
        "needs_review": bool(prov.get("needsReview", False)),
        "origin": TRACKERS_ORIGIN,
        "natural_key": key,
        "chamber": row.get("chamber"),
        "member_name": member_name,
        "asset_type": row.get("assetType"),
        "filed_at": row.get("filedAt"),
        "owner": row.get("owner"),
    }
    return {
        "doc_id": key,
        "text": _trade_text(row, member_name, ticker),
        "metadata": metadata,
    }


def _natural_keys_in_index(index_name: str) -> set[str]:
    """Natural keys already present in the in-memory stub index (test path).

    Production backends dedupe by stable chunk id at write time instead.
    Bulk callers build this set **once** and thread it through
    ``_known_keys`` — rescanning per row is O(n²) over the index and falls
    over on the 100k+ row datasets (#4849).
    """
    keys: set[str] = set()
    for chunk in _stub_index.get(index_name, []):
        natural_key = (chunk.metadata or {}).get("natural_key")
        if natural_key:
            keys.add(str(natural_key))
    return keys


def ingest_congress_trade(
    row: Mapping[str, Any],
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    _known_keys: set[str] | None = None,
) -> str | None:
    """Always refuses — the single-row entry point is closed.

    Raises :class:`RefusedDatasetError` as the first statement, before the row
    is normalized and before any index write. :func:`normalize_congress_trade`
    stays callable on its own; this function is the gate.
    """
    _assert_not_refused(CONGRESS_TRADES_DATASET)

    normalized = normalize_congress_trade(row)
    key = str(normalized["doc_id"])
    target_index = (index_name or TRACKERS_INDEX_NAME).strip() or TRACKERS_INDEX_NAME
    known = _known_keys if _known_keys is not None else _natural_keys_in_index(target_index)
    if key in known:
        logger.info(
            "trackers ingest skipped — row already indexed",
            extra={
                "operation": "ingest_congress_trade",
                "outcome": "skipped",
                "natural_key": key,
                "index_name": target_index,
            },
        )
        return None

    metadata = dict(normalized["metadata"])
    used_chunker = chunker or get_document_chunker()
    # Deterministic Document.id via the shared research helper, seeded by the
    # natural key — same row replayed → same id on every backend.
    date_seed = str(metadata.get("transacted_at") or metadata.get("filed_at") or "")
    doc_id = _stable_doc_id(
        {"date": date_seed, "document_key": f"luxalgo-trackers/congress-trades:{key}"}
    )
    doc = Document(
        id=doc_id,
        content=str(normalized["text"]),
        source=str(metadata["source_url"]),
        doc_type="luxalgo_congress_trade",
        metadata=dict(metadata),
        chunks=[],
    )
    chunks = used_chunker.chunk(doc)
    for idx, chunk in enumerate(chunks):
        chunk.id = f"luxalgo-trackers::congress-trades::{key}::{idx}"
        chunk.doc_id = doc_id
    merge_document_metadata_into_chunks(doc, chunks)
    for chunk in chunks:
        chunk.metadata = normalize_metadata_for_chroma(chunk.metadata)
    index_chunks(target_index, chunks)
    known.add(key)
    logger.info(
        "trackers ingest done",
        extra={
            "operation": "ingest_congress_trade",
            "outcome": "ok",
            "natural_key": key,
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "index_name": target_index,
        },
    )
    return doc_id


def ingest_congress_trades(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> TrackersIngestResult:
    """Always refuses — the congress-trades bulk entry point is closed.

    Raises :class:`RefusedDatasetError` as the first statement: before the
    manifest read, before the feed fetch, before any index write. The body below
    is unreachable today and exists only as the shape a future, separately
    cleared feed would need.
    """
    _assert_not_refused(CONGRESS_TRADES_DATASET)

    manifest = check_manifest_not_stale(fetcher, allowed_hosts=allowed_hosts)
    rows = fetch_congress_trades_latest(fetcher, allowed_hosts=allowed_hosts)
    expected = _manifest_expected_rows(manifest)
    if expected is not None and expected != len(rows):
        logger.warning(
            "trackers feed served %d rows, manifest declares %d — proceeding",
            len(rows),
            expected,
            extra={
                "operation": "ingest_congress_trades",
                "outcome": "degraded",
                "served_rows": len(rows),
                "manifest_rows": expected,
            },
        )
    target_index = (index_name or TRACKERS_INDEX_NAME).strip() or TRACKERS_INDEX_NAME

    # One stub-index scan per bulk run (not per row): the 100k+ row datasets
    # would otherwise rescan the whole index for every row — O(n²) (#4849).
    known_keys = _natural_keys_in_index(target_index)
    ingested = 0
    skipped = 0
    for row in rows:
        if not isinstance(row, Mapping):
            logger.warning(
                "trackers ingest skipped — row is not an object",
                extra={
                    "operation": "ingest_congress_trades",
                    "outcome": "skipped",
                    "row_type": type(row).__name__,
                },
            )
            skipped += 1
            continue
        try:
            doc_id = ingest_congress_trade(
                row, index_name=target_index, chunker=chunker, _known_keys=known_keys
            )
        except ValueError as exc:
            logger.warning(
                f"trackers ingest skipped — {exc}",
                extra={"operation": "ingest_congress_trades", "outcome": "skipped"},
            )
            skipped += 1
            continue
        if doc_id is None:
            skipped += 1
        else:
            ingested += 1
    return TrackersIngestResult(ingested=ingested, skipped=skipped, source=TRACKERS_ORIGIN)


__all__ = [
    "CODE_REFUSED_DATASETS",
    "CODE_REFUSED_URL_FRAGMENTS",
    "CONGRESS_TRADES_DATASET",
    "CONGRESS_TRADES_URL",
    "REFUSAL_DENYLIST_ENV_VAR",
    "TRACKERS_ALLOWED_HOSTS",
    "TRACKERS_INDEX_NAME",
    "TRACKERS_MANIFEST_URL",
    "TRACKERS_ORIGIN",
    "RefusedDatasetError",
    "StaleDatasetError",
    "TrackersFetchError",
    "TrackersIngestResult",
    "check_manifest_not_stale",
    "fetch_congress_trades_latest",
    "ingest_congress_trade",
    "ingest_congress_trades",
    "normalize_congress_trade",
    "refused_datasets",
]
