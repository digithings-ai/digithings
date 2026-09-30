"""luxalgo market-trackers-data congress-trades CC0 dump → digisearch index.

Primary-source US public-records layer **beside Gloomberg** (never replacing
the terminal digest). Thin wrap mirroring :mod:`digisearch.research_ingest`:
fetch rows → normalize to flat payloads → write through the shared
:func:`digisearch.pipeline.ingest.index_chunks`.

Row schema (``congress/trades/latest.json``, verified 2026-09-30): a bare JSON
array of ``{id, chamber, docId, rowIndex, member{name,bioguideId,party,state},
filedAt, transactedAt, ticker|null, assetDescription, assetType, side,
amountRange{min,max,text}, owner|null, provenance{source, sourceUrl,
retrievedAt, parser, confidence, needsReview}}``. Null-ticker rows are
ingested like any other row (no silent drop) — the ``ticker`` metadata key is
simply absent after Chroma normalization.

Idempotency: the natural key ``{chamber}:{docId}:{rowIndex}`` seeds stable
``Document``/chunk ids (the ``Document.id`` reuses
:func:`digisearch.research_ingest._stable_doc_id`), so every backend upserts
by id. The ``ingested``/``skipped`` counts additionally probe the in-memory
stub index — exact on the unit-test path; on production backends a rewritten
row reports as ingested while storage still dedupes by stable id.

Network: all HTTP goes through
:func:`digisearch.pipeline.url_ingest.fetch_json_feed` — the single URL-fetch
site (SSRF-guarded digifetch ``HttpFetcher`` via ``validate_fetch_url``).
This module never opens sockets itself and never fetches URLs directly.
``digifetch``/``url_ingest`` are imported lazily so importing this module
never requires the extra.
"""

from __future__ import annotations

import logging
import os
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


#: Stable feed: current congress-trades snapshot (CC0-1.0 data).
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


class StaleDatasetError(RuntimeError):
    """The upstream manifest flags this dataset ``stale`` — ingest refused."""


class TrackersFetchError(RuntimeError):
    """Fetch/validation/shape failure for the trackers feed.

    Raised for unreachable manifests, unvalidated URLs, non-JSON bodies, and
    row-list shape violations — never for a genuine ``stale: true`` flag
    (that stays :class:`StaleDatasetError`).
    """


class TrackersIngestResult(BaseModel):
    """Outcome of one congress-trades ingest run."""

    model_config = ConfigDict(extra="forbid")

    ingested: int = Field(ge=0)
    skipped: int = Field(ge=0)
    source: str = TRACKERS_ORIGIN


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

    Maps :class:`UrlFetchError` onto :class:`TrackersFetchError` so callers
    can distinguish transport problems from a genuine stale flag.
    """
    from digisearch.pipeline.url_ingest import UrlFetchError, fetch_json_feed

    try:
        return fetch_json_feed(url, fetcher=fetcher, allowed_hosts=allowed_hosts)
    except UrlFetchError as exc:
        raise TrackersFetchError(f"trackers fetch failed for {url!r}: {exc}") from exc


def _manifest_dataset_entry(manifest: Any) -> Mapping[str, Any] | None:
    """congress-trades entry of the manifest ``datasets`` section, any shape.

    Returns ``None`` when the manifest has no entry for this dataset, so a
    manifest reshape degrades to warn-and-proceed rather than blocking ingest
    or passing a stale flag silently.
    """
    datasets: Any = None
    if isinstance(manifest, Mapping):
        datasets = manifest.get("datasets")
    if isinstance(datasets, Mapping):
        entry = datasets.get(CONGRESS_TRADES_DATASET)
        return entry if isinstance(entry, Mapping) else None
    if isinstance(datasets, list):
        for entry in datasets:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name") or entry.get("id") or entry.get("dataset")
            if name == CONGRESS_TRADES_DATASET:
                return entry
    return None


def _manifest_dataset_stale(manifest: Any) -> bool | None:
    """Return the ``stale`` flag for congress-trades, or ``None`` when unknown.

    Handles the verified manifest shape (``{"datasets": {name: {...}}}``) and
    degrades to ``None`` — warn-and-proceed — for anything else, so a manifest
    reshape never silently blocks ingest nor silently passes a stale flag.
    """
    entry = _manifest_dataset_entry(manifest)
    if entry is not None and "stale" in entry:
        return bool(entry.get("stale"))
    return None


def _manifest_expected_rows(manifest: Any) -> int | None:
    """Manifest-declared row count for congress-trades, or ``None`` unknown."""
    entry = _manifest_dataset_entry(manifest)
    rows = entry.get("rows") if entry is not None else None
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        return None
    return rows


def check_manifest_not_stale(
    fetcher: _FetcherLike | None = None,
    *,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Any | None:
    """Refuse congress-trades ingest when the manifest flags it ``stale``.

    A missing/unreachable/unparseable manifest warns and proceeds (advisory
    signal); an explicit ``stale: true`` raises :class:`StaleDatasetError`.
    Returns the parsed manifest (``None`` when unreadable) so callers can
    reuse it — e.g. the row-count check — without a second fetch.
    """
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
    stale = _manifest_dataset_stale(manifest)
    if stale is True:
        raise StaleDatasetError(
            f"dataset {CONGRESS_TRADES_DATASET!r} flagged stale in"
            f" {TRACKERS_MANIFEST_URL} — ingest refused"
        )
    if stale is None:
        logger.warning(
            "trackers manifest has no freshness entry for congress-trades — proceeding",
            extra={"operation": "check_manifest_not_stale", "outcome": "degraded"},
        )
    return manifest


def fetch_congress_trades_latest(
    fetcher: _FetcherLike | None = None,
    *,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> list[dict[str, Any]]:
    """GET the congress-trades snapshot and return raw row dicts.

    Accepts the verified bare-array shape; also unwraps common ``{"trades" /
    "rows" / "data": [...]}`` envelopes. Raises :class:`TrackersFetchError`
    when the body is not a row list.
    """
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
) -> str | None:
    """Index one congress-trade row; return its ``Document.id``.

    Returns ``None`` when the row's natural key is already indexed (idempotent
    skip). Raises :class:`ValueError` for rows without a natural key.
    """
    normalized = normalize_congress_trade(row)
    key = str(normalized["doc_id"])
    target_index = (index_name or TRACKERS_INDEX_NAME).strip() or TRACKERS_INDEX_NAME
    if key in _natural_keys_in_index(target_index):
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
    """Fetch → normalize → index the congress-trades snapshot (entry point).

    Checks the manifest freshness flag first (refuses on ``stale: true``),
    then ingests each row. Warns when the served row count differs from the
    manifest-declared count. Rows without a natural key are counted as
    skipped (logged, never silent); already-indexed rows are skipped
    idempotently.
    """
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
            doc_id = ingest_congress_trade(row, index_name=target_index, chunker=chunker)
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
    "CONGRESS_TRADES_DATASET",
    "CONGRESS_TRADES_URL",
    "TRACKERS_ALLOWED_HOSTS",
    "TRACKERS_INDEX_NAME",
    "TRACKERS_MANIFEST_URL",
    "TRACKERS_ORIGIN",
    "StaleDatasetError",
    "TrackersFetchError",
    "TrackersIngestResult",
    "check_manifest_not_stale",
    "fetch_congress_trades_latest",
    "ingest_congress_trade",
    "ingest_congress_trades",
    "normalize_congress_trade",
]
