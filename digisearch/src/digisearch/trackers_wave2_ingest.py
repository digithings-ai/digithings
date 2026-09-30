"""luxalgo market-trackers-data wave-2 CC0 dumps → digisearch index (#4849).

Ticker-bearing follow-up to the congress-trades spike
(:mod:`digisearch.trackers_ingest`, #4826): ``insider-transactions`` (~17.5k
rows), ``thirteenf-holdings`` (~111k), ``short-volume`` (~122k daily),
``lobbying-filings`` (~56k), ``gov-contracts`` (~12.7k). Primary-source US
public-records depth **beside Gloomberg** (never replacing the terminal
digest), complementing the existing ``digifetch_13f_*`` / short-interest
coverage.

Row schemas (verified against live ``latest.json`` samples 2026-09-30; the
upstream repo carries no machine-readable zod schemas — ``explorer/`` is a
static page — so shapes below are pinned from observed samples):

- insider (``insider/transactions/latest.json``): bare array of ``{id,
  accessionNumber, formType, ticker|null, issuerCik, issuerName,
  insider{name, cik, title, ...}, transactedAt, filedAt, code,
  acquiredDisposed, securityTitle, shares, pricePerShare, sharesOwnedAfter,
  ownership, isDerivative, provenance{source, sourceUrl, retrievedAt,
  parser, confidence, needsReview}}``. ``id`` is
  ``{accessionNumber}:{direct-flag}:{leg}``.
- thirteenf (``thirteenf/holdings/latest.json``): bare array of ``{id,
  accessionNumber, managerCik, managerName, periodEnd, filedAt, cusip,
  ticker, issuerName, shareType, shares, valueUsd, putCall,
  provenance{...}}``. ``ticker`` is currently **always null** upstream
  (``thirteenf-xml@1`` does not resolve CUSIP→ticker) — rows stay keyed by
  issuer/cusip and are kept regardless. ``id`` is
  ``{accessionNumber}:{rowIndex}``.
- short-volume (``short-volume/daily/latest.json``): bare array of ``{id,
  date, ticker, market, shortVolume, shortExemptVolume, totalVolume,
  shortRatio, provenance{source: finra, ...}}``. ``id`` is
  ``{date}:{ticker}:{market}``.
- lobbying (``lobbying/filings/latest.json``): bare array of ``{id,
  filingUuid, registrant{name}, client{name, tickers[]}, amountUsd,
  filingYear, filingPeriod, filingType, issues[], billReferences[],
  provenance{source: lda, ...}}``. No top-level ticker — tickers live in
  ``client.tickers`` (often empty; only ~7% of sampled rows carry one).
- gov-contracts (``contracts/awards/latest.json``): bare array of ``{id,
  awardId, awardType, agency, subAgency, recipient{name, uei, tickers[]},
  amountUsd, actionDate, description, naicsCode, naicsDescription,
  provenance{source: usaspending, ...}}``. Tickers live in
  ``recipient.tickers`` (often empty; ~21% of sampled rows carry one).

Idempotency: the natural key ``{dataset}:{upstream-id}`` seeds stable
``Document``/chunk ids (``Document.id`` reuses
:func:`digisearch.research_ingest._stable_doc_id`), so every backend upserts
by id. The bulk entry points build the stub-index key set **once** and thread
it through (see :func:`digisearch.trackers_ingest._natural_keys_in_index`) —
rescanning per row is O(n²) and falls over on the 100k+ row datasets.

Null-ticker rows are ingested like any other row (no silent drop) — the
``ticker`` metadata key is simply absent after Chroma normalization, and the
row text falls back to the issuer/client/recipient name.

Network: all HTTP goes through
:func:`digisearch.pipeline.url_ingest.fetch_json_feed` — the single URL-fetch
site (SSRF-guarded digifetch ``HttpFetcher`` via ``validate_fetch_url``).
This module never opens sockets itself and never fetches URLs directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Protocol  # score:allow untyped any — heterogeneous JSON rows

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
from digisearch.trackers_ingest import (
    TRACKERS_ALLOWED_HOSTS,
    TRACKERS_INDEX_NAME,
    TrackersFetchError,
    _fetch_feed_json,
    _manifest_expected_rows,
    _natural_keys_in_index,
    check_manifest_not_stale,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrackerDatasetSpec:
    """Static config for one wave-2 tracker dataset."""

    #: Manifest key (``datasets.<key>``) and natural-key namespace.
    key: str
    #: Feed file with the current snapshot rows.
    feed_url: str
    #: ``Document.doc_type`` for rows of this dataset.
    doc_type: str
    #: Where tickers live: top-level ``ticker`` or a nested ``tickers`` list.
    ticker_path: str


def _feed_url(export_dir: str) -> str:
    base = "https://raw.githubusercontent.com/LuxAlgo/market-trackers-data/main"
    return f"{base}/{export_dir}/latest.json"


#: The five wave-2 datasets in issue order (insider → 13F → short-volume →
#: lobbying → gov-contracts). Row counts are the live manifest values
#: observed 2026-09-30.
TRACKER_DATASETS: dict[str, TrackerDatasetSpec] = {
    "insider-transactions": TrackerDatasetSpec(
        key="insider-transactions",
        feed_url=_feed_url("insider/transactions"),
        doc_type="luxalgo_insider_transaction",
        ticker_path="ticker",
    ),
    "thirteenf-holdings": TrackerDatasetSpec(
        key="thirteenf-holdings",
        feed_url=_feed_url("thirteenf/holdings"),
        doc_type="luxalgo_thirteenf_holding",
        ticker_path="ticker",
    ),
    "short-volume": TrackerDatasetSpec(
        key="short-volume",
        feed_url=_feed_url("short-volume/daily"),
        doc_type="luxalgo_short_volume",
        ticker_path="ticker",
    ),
    "lobbying-filings": TrackerDatasetSpec(
        key="lobbying-filings",
        feed_url=_feed_url("lobbying/filings"),
        doc_type="luxalgo_lobbying_filing",
        ticker_path="client.tickers",
    ),
    "gov-contracts": TrackerDatasetSpec(
        key="gov-contracts",
        feed_url=_feed_url("contracts/awards"),
        doc_type="luxalgo_gov_contract",
        ticker_path="recipient.tickers",
    ),
}

#: Manifest keys in issue order — the mandated implementation sequence.
TRACKER_DATASET_ORDER: tuple[str, ...] = (
    "insider-transactions",
    "thirteenf-holdings",
    "short-volume",
    "lobbying-filings",
    "gov-contracts",
)


def _resolve_spec(dataset: str | TrackerDatasetSpec) -> TrackerDatasetSpec:
    if isinstance(dataset, TrackerDatasetSpec):
        return dataset
    try:
        return TRACKER_DATASETS[dataset]
    except KeyError:
        raise ValueError(
            f"unknown tracker dataset {dataset!r} (expected one of {sorted(TRACKER_DATASETS)})"
        ) from None


class Wave2Result(BaseModel):
    """Outcome of one wave-2 dataset ingest run."""

    model_config = ConfigDict(extra="forbid")

    ingested: int = Field(ge=0)
    skipped: int = Field(ge=0)
    dataset: str


class _FetcherLike(Protocol):
    """Minimal fetch surface this module needs (duck-typed onto HttpFetcher)."""

    def fetch(self, url: str) -> Any:
        """GET *url* and return the decoded body (``.text`` is all we read)."""
        ...


def fetch_tracker_rows_latest(
    dataset: str | TrackerDatasetSpec,
    fetcher: _FetcherLike | None = None,
    *,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> list[dict[str, Any]]:
    """GET the dataset snapshot feed and return raw row dicts.

    Accepts the verified bare-array shape; also unwraps common
    ``{"rows" / "data" / "transactions" / "holdings" / "filings": [...]}``
    envelopes. Raises :class:`TrackersFetchError` when the body is not a row
    list.
    """
    spec = _resolve_spec(dataset)
    payload = _fetch_feed_json(spec.feed_url, fetcher, allowed_hosts)
    if isinstance(payload, list):
        rows: list[Any] = payload
    elif isinstance(payload, Mapping):
        rows = []
        for key in ("rows", "data", "transactions", "holdings", "filings", "awards"):
            if isinstance(payload.get(key), list):
                rows = list(payload[key])
                break
        else:
            raise TrackersFetchError(
                f"trackers feed at {spec.feed_url!r} has no row list (keys: {sorted(payload)})"
            )
    else:
        raise TrackersFetchError(
            f"trackers feed at {spec.feed_url!r} returned {type(payload).__name__}, not a row list"
        )
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            out.append(dict(row))
        else:
            logger.warning(
                "trackers feed row is not an object — counted as skipped at ingest",
                extra={
                    "operation": "fetch_tracker_rows_latest",
                    "outcome": "skipped",
                    "dataset": spec.key,
                    "row_type": type(row).__name__,
                },
            )
    return out


def _natural_key(spec: TrackerDatasetSpec, row: Mapping[str, Any]) -> str:
    """Natural-key id ``{dataset}:{upstream-id}`` (raises when incomplete)."""
    upstream_id = row.get("id")
    if upstream_id is None or not str(upstream_id).strip():
        raise ValueError(f"{spec.key} row requires a non-empty 'id'")
    return f"{spec.key}:{upstream_id}"


def _tickers_of(spec: TrackerDatasetSpec, row: Mapping[str, Any]) -> list[str]:
    """All tickers carried by *row* (empty when the row has none)."""
    if spec.ticker_path == "ticker":
        ticker = row.get("ticker")
        return [str(ticker).strip()] if ticker is not None and str(ticker).strip() else []
    holder_key, _, _ = spec.ticker_path.partition(".")
    holder = row.get(holder_key)
    tickers = holder.get("tickers") if isinstance(holder, Mapping) else None
    if not isinstance(tickers, list):
        return []
    return [str(t).strip() for t in tickers if t is not None and str(t).strip()]


def _provenance(row: Mapping[str, Any]) -> Mapping[str, Any]:
    provenance = row.get("provenance")
    return provenance if isinstance(provenance, Mapping) else {}


def _source_url(spec: TrackerDatasetSpec, row: Mapping[str, Any]) -> str:
    prov = _provenance(row)
    source_url = prov.get("sourceUrl")
    return str(source_url) if source_url else spec.feed_url


def _row_text(spec: TrackerDatasetSpec, row: Mapping[str, Any], tickers: list[str]) -> str:
    """One deterministic human-readable line per row (chunk content)."""
    key = spec.key
    if key == "insider-transactions":
        insider = row.get("insider")
        name = insider.get("name") if isinstance(insider, Mapping) else None
        asset = tickers[0] if tickers else str(row.get("issuerName") or "unknown issuer")
        direction = str(row.get("acquiredDisposed") or "n/a")
        shares = row.get("shares")
        price = row.get("pricePerShare")
        leg = f"{shares} sh @ {price}" if shares is not None else "shares n/a"
        return (
            f"insider {row.get('formType') or 'Form ?'}: {name or 'unknown insider'} "
            f"{direction} {leg} of {asset} "
            f"(transacted {row.get('transactedAt') or 'date n/a'}, "
            f"filed {row.get('filedAt') or 'date n/a'})"
        )
    if key == "thirteenf-holdings":
        asset = tickers[0] if tickers else str(row.get("issuerName") or "unknown issuer")
        cusip = row.get("cusip") or "cusip n/a"
        return (
            f"13F: {row.get('managerName') or 'unknown manager'} holds "
            f"{row.get('shares')} sh of {asset} ({cusip}) "
            f"worth ${row.get('valueUsd')} "
            f"(period {row.get('periodEnd') or 'n/a'}, filed {row.get('filedAt') or 'n/a'})"
        )
    if key == "short-volume":
        return (
            f"short-volume {row.get('date')}: {tickers[0] if tickers else 'unknown ticker'} "
            f"({row.get('market') or 'n/a'}) short {row.get('shortVolume')} / "
            f"total {row.get('totalVolume')} (ratio {row.get('shortRatio')})"
        )
    if key == "lobbying-filings":
        registrant = row.get("registrant")
        reg = registrant.get("name") if isinstance(registrant, Mapping) else None
        client = row.get("client")
        client_name = client.get("name") if isinstance(client, Mapping) else None
        asset = tickers[0] if tickers else (client_name or "unknown client")
        issues = row.get("issues")
        issues_text = ",".join(str(i) for i in issues) if isinstance(issues, list) else "n/a"
        return (
            f"lobbying {row.get('filingType') or 'filing'} {row.get('filingYear')}: "
            f"{reg or 'unknown registrant'} for {asset} "
            f"(${row.get('amountUsd')}, issues: {issues_text})"
        )
    # gov-contracts
    recipient = row.get("recipient")
    recipient_name = recipient.get("name") if isinstance(recipient, Mapping) else None
    asset = tickers[0] if tickers else (recipient_name or "unknown recipient")
    return (
        f"gov-contract {row.get('awardType') or 'award'}: "
        f"{row.get('agency') or 'unknown agency'} → {asset} "
        f"(${row.get('amountUsd')}, {row.get('actionDate') or 'date n/a'})"
    )


def _date_seed(spec: TrackerDatasetSpec, row: Mapping[str, Any]) -> str:
    key = spec.key
    if key == "insider-transactions":
        return str(row.get("transactedAt") or row.get("filedAt") or "")
    if key == "thirteenf-holdings":
        return str(row.get("periodEnd") or row.get("filedAt") or "")
    if key == "short-volume":
        return str(row.get("date") or "")
    if key == "lobbying-filings":
        return str(row.get("filingYear") or "")
    return str(row.get("actionDate") or "")


def normalize_tracker_row(
    dataset: str | TrackerDatasetSpec, row: Mapping[str, Any]
) -> dict[str, Any]:
    """Map one upstream row to ``{doc_id, text, metadata}``.

    ``doc_id`` is the natural key ``{dataset}:{upstream-id}``. ``metadata``
    carries the canonical ``source_url`` (upstream
    ``provenance.sourceUrl``), the primary ``ticker`` (first listed, else
    ``None`` — dropped later by Chroma normalization), the full ``tickers``
    list (comma-joined by Chroma normalization), plus lineage keys. Rows
    without tickers are always kept.
    """
    spec = _resolve_spec(dataset)
    key = _natural_key(spec, row)
    prov = _provenance(row)
    tickers = _tickers_of(spec, row)
    metadata: dict[str, Any] = {
        "source_url": _source_url(spec, row),
        "ticker": tickers[0] if tickers else None,
        "tickers": tickers,
        "needs_review": bool(prov.get("needsReview", False)),
        "origin": f"luxalgo-trackers/{spec.key}",
        "natural_key": key,
        "dataset": spec.key,
    }
    if spec.key == "insider-transactions":
        insider = row.get("insider")
        insider_map = insider if isinstance(insider, Mapping) else {}
        metadata.update(
            {
                "insider_name": insider_map.get("name"),
                "issuer": row.get("issuerName"),
                "form_type": row.get("formType"),
                "acquired_disposed": row.get("acquiredDisposed"),
                "shares": row.get("shares"),
                "price_per_share": row.get("pricePerShare"),
                "transacted_at": row.get("transactedAt"),
                "filed_at": row.get("filedAt"),
            }
        )
    elif spec.key == "thirteenf-holdings":
        metadata.update(
            {
                "manager_name": row.get("managerName"),
                "issuer": row.get("issuerName"),
                "cusip": row.get("cusip"),
                "shares": row.get("shares"),
                "value_usd": row.get("valueUsd"),
                "period_end": row.get("periodEnd"),
                "filed_at": row.get("filedAt"),
            }
        )
    elif spec.key == "short-volume":
        metadata.update(
            {
                "market": row.get("market"),
                "date": row.get("date"),
                "short_volume": row.get("shortVolume"),
                "total_volume": row.get("totalVolume"),
                "short_ratio": row.get("shortRatio"),
            }
        )
    elif spec.key == "lobbying-filings":
        registrant = row.get("registrant")
        reg_map = registrant if isinstance(registrant, Mapping) else {}
        client = row.get("client")
        client_map = client if isinstance(client, Mapping) else {}
        metadata.update(
            {
                "registrant": reg_map.get("name"),
                "client": client_map.get("name"),
                "amount_usd": row.get("amountUsd"),
                "filing_year": row.get("filingYear"),
                "filing_period": row.get("filingPeriod"),
                "filing_type": row.get("filingType"),
                "issues": list(row["issues"]) if isinstance(row.get("issues"), list) else None,
            }
        )
    else:  # gov-contracts
        recipient = row.get("recipient")
        recipient_map = recipient if isinstance(recipient, Mapping) else {}
        metadata.update(
            {
                "agency": row.get("agency"),
                "recipient": recipient_map.get("name"),
                "amount_usd": row.get("amountUsd"),
                "action_date": row.get("actionDate"),
                "award_type": row.get("awardType"),
            }
        )
    return {
        "doc_id": key,
        "text": _row_text(spec, row, tickers),
        "metadata": metadata,
    }


def ingest_tracker_row(
    dataset: str | TrackerDatasetSpec,
    row: Mapping[str, Any],
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    _known_keys: set[str] | None = None,
) -> str | None:
    """Index one tracker row; return its ``Document.id``.

    Returns ``None`` when the row's natural key is already indexed (idempotent
    skip). Raises :class:`ValueError` for rows without a natural key.
    ``_known_keys`` is the bulk-run memo (see
    :func:`digisearch.trackers_ingest.ingest_congress_trade`).
    """
    spec = _resolve_spec(dataset)
    normalized = normalize_tracker_row(spec, row)
    key = str(normalized["doc_id"])
    target_index = (index_name or TRACKERS_INDEX_NAME).strip() or TRACKERS_INDEX_NAME
    known = _known_keys if _known_keys is not None else _natural_keys_in_index(target_index)
    if key in known:
        logger.info(
            "trackers ingest skipped — row already indexed",
            extra={
                "operation": "ingest_tracker_row",
                "outcome": "skipped",
                "dataset": spec.key,
                "natural_key": key,
                "index_name": target_index,
            },
        )
        return None

    metadata = dict(normalized["metadata"])
    used_chunker = chunker or get_document_chunker()
    # Deterministic Document.id via the shared research helper, seeded by the
    # natural key — same row replayed → same id on every backend.
    doc_id = _stable_doc_id(
        {"date": _date_seed(spec, row), "document_key": f"luxalgo-trackers/{spec.key}:{key}"}
    )
    doc = Document(
        id=doc_id,
        content=str(normalized["text"]),
        source=str(metadata["source_url"]),
        doc_type=spec.doc_type,
        metadata=dict(metadata),
        chunks=[],
    )
    chunks = used_chunker.chunk(doc)
    upstream_id = key.split(":", 1)[1]
    for idx, chunk in enumerate(chunks):
        chunk.id = f"luxalgo-trackers::{spec.key}::{upstream_id}::{idx}"
        chunk.doc_id = doc_id
    merge_document_metadata_into_chunks(doc, chunks)
    for chunk in chunks:
        chunk.metadata = normalize_metadata_for_chroma(chunk.metadata)
    index_chunks(target_index, chunks)
    known.add(key)
    logger.info(
        "trackers ingest done",
        extra={
            "operation": "ingest_tracker_row",
            "outcome": "ok",
            "dataset": spec.key,
            "natural_key": key,
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "index_name": target_index,
        },
    )
    return doc_id


def ingest_tracker_dataset(
    dataset: str | TrackerDatasetSpec,
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index one wave-2 dataset snapshot (entry point).

    Checks the manifest freshness flag first (refuses on ``stale: true``),
    then ingests each row. Warns when the served row count differs from the
    manifest-declared count. Rows without a natural key are counted as
    skipped (logged, never silent); already-indexed rows are skipped
    idempotently. The stub-index key set is built once per run (O(n)).
    """
    spec = _resolve_spec(dataset)
    manifest = check_manifest_not_stale(fetcher, allowed_hosts=allowed_hosts, dataset=spec.key)
    rows = fetch_tracker_rows_latest(spec, fetcher, allowed_hosts=allowed_hosts)
    expected = _manifest_expected_rows(manifest, spec.key)
    if expected is not None and expected != len(rows):
        logger.warning(
            "trackers feed served %d rows, manifest declares %d — proceeding",
            len(rows),
            expected,
            extra={
                "operation": "ingest_tracker_dataset",
                "outcome": "degraded",
                "dataset": spec.key,
                "served_rows": len(rows),
                "manifest_rows": expected,
            },
        )
    target_index = (index_name or TRACKERS_INDEX_NAME).strip() or TRACKERS_INDEX_NAME
    known_keys = _natural_keys_in_index(target_index)

    ingested = 0
    skipped = 0
    for row in rows:
        if not isinstance(row, Mapping):
            logger.warning(
                "trackers ingest skipped — row is not an object",
                extra={
                    "operation": "ingest_tracker_dataset",
                    "outcome": "skipped",
                    "dataset": spec.key,
                    "row_type": type(row).__name__,
                },
            )
            skipped += 1
            continue
        try:
            doc_id = ingest_tracker_row(
                spec, row, index_name=target_index, chunker=chunker, _known_keys=known_keys
            )
        except ValueError as exc:
            logger.warning(
                f"trackers ingest skipped — {exc}",
                extra={
                    "operation": "ingest_tracker_dataset",
                    "outcome": "skipped",
                    "dataset": spec.key,
                },
            )
            skipped += 1
            continue
        if doc_id is None:
            skipped += 1
        else:
            ingested += 1
    return Wave2Result(ingested=ingested, skipped=skipped, dataset=spec.key)


def _dataset_ingest(
    dataset_key: str,
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    return ingest_tracker_dataset(
        dataset_key, fetcher, index_name=index_name, chunker=chunker, allowed_hosts=allowed_hosts
    )


def ingest_insider_transactions(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index the insider-transactions snapshot."""
    return _dataset_ingest(
        "insider-transactions",
        fetcher,
        index_name=index_name,
        chunker=chunker,
        allowed_hosts=allowed_hosts,
    )


def ingest_thirteenf_holdings(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index the thirteenf-holdings snapshot."""
    return _dataset_ingest(
        "thirteenf-holdings",
        fetcher,
        index_name=index_name,
        chunker=chunker,
        allowed_hosts=allowed_hosts,
    )


def ingest_short_volume(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index the short-volume daily snapshot."""
    return _dataset_ingest(
        "short-volume",
        fetcher,
        index_name=index_name,
        chunker=chunker,
        allowed_hosts=allowed_hosts,
    )


def ingest_lobbying_filings(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index the lobbying-filings snapshot."""
    return _dataset_ingest(
        "lobbying-filings",
        fetcher,
        index_name=index_name,
        chunker=chunker,
        allowed_hosts=allowed_hosts,
    )


def ingest_gov_contracts(
    fetcher: _FetcherLike | None = None,
    *,
    index_name: str | None = None,
    chunker: Chunker | None = None,
    allowed_hosts: tuple[str, ...] = TRACKERS_ALLOWED_HOSTS,
) -> Wave2Result:
    """Fetch → normalize → index the gov-contracts snapshot."""
    return _dataset_ingest(
        "gov-contracts",
        fetcher,
        index_name=index_name,
        chunker=chunker,
        allowed_hosts=allowed_hosts,
    )


__all__ = [
    "TRACKER_DATASETS",
    "TRACKER_DATASET_ORDER",
    "TrackerDatasetSpec",
    "Wave2Result",
    "fetch_tracker_rows_latest",
    "ingest_gov_contracts",
    "ingest_insider_transactions",
    "ingest_lobbying_filings",
    "ingest_short_volume",
    "ingest_thirteenf_holdings",
    "ingest_tracker_dataset",
    "ingest_tracker_row",
    "normalize_tracker_row",
]
