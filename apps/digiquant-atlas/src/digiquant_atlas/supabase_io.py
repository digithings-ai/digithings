"""Supabase adapter for the Atlas sub-graph.

Replaces the legacy ``scripts/publish_document.py`` and
``scripts/materialize_snapshot.py`` write paths from inside the DigiGraph
sub-graph. Same tables, same unique keys — the legacy scripts will be frozen
in commit 9 so both paths can never write concurrently.

Design:
- Thin wrapper over the ``supabase`` Python client. No ORM.
- Dependency-injected client (:class:`SupabaseClient` protocol) so unit tests
  use an in-memory fake without a live DB.
- Every write passes its payload through ``digibase.audit.redact_mapping``
  before the audit log line is emitted — non-negotiable per CLAUDE.md.
- Idempotency: all writes are upserts on the schema-declared unique keys
  (``(date, document_key)`` for ``documents``; ``date`` for ``daily_snapshots``).
  Retries of the same node are safe.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol  # noqa: F401 — used for Supabase payload dict shape

from digibase.audit import redact_mapping

from digiquant_atlas.state import PriorContext, PublishedArtifact

logger = logging.getLogger(__name__)


class SupabaseClient(Protocol):
    """Minimal surface we use from the ``supabase`` Python client.

    Defined as a Protocol so tests can inject a fake without pulling the
    supabase dependency. Production callers pass the real ``Client``.
    """

    def table(self, name: str) -> Any: ...  # noqa: D401, E704


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_KEY are missing at runtime."""


@dataclass(frozen=True)
class SupabaseConfig:
    """Runtime config. Resolved from env vars by default; override-able in tests."""

    url: str
    service_key: str

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        if not url or not key:
            raise SupabaseNotConfiguredError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        return cls(url=url, service_key=key)


def _build_client(cfg: SupabaseConfig) -> SupabaseClient:
    """Construct a live Supabase client. Kept module-local so tests can skip the import."""
    from supabase import create_client  # deferred — supabase is an optional dep for unit tests

    return create_client(cfg.url, cfg.service_key)  # type: ignore[return-value]


def _audit(event_type: str, payload: dict[str, Any]) -> None:
    """Emit an audit line with sensitive keys redacted.

    This module only logs via the standard logger; downstream JSONL audit
    writers (DigiGraph's ``audit.py``) will add timestamps/event envelopes.
    Redaction happens here so the audit writer never sees raw secrets.
    """
    logger.info("atlas_io audit: %s %s", event_type, redact_mapping(payload))


def publish_document(
    *,
    client: SupabaseClient,
    document_key: str,
    payload: dict[str, Any],
    doc_type: str,
    run_type: str,
    title: str,
    date_str: str,
    category: str = "research",
    segment: str | None = None,
    sector: str | None = None,
    content_markdown: str | None = None,
) -> PublishedArtifact:
    """Upsert one row into ``documents`` on ``(date, document_key)``.

    Returns a :class:`PublishedArtifact` that callers append to
    ``AtlasResearchState.published``. Idempotent — replays with the same
    (date, document_key) either update the row or no-op depending on whether
    the payload changed.
    """
    row = {
        "date": date_str,
        "title": title,
        "doc_type": doc_type,
        "phase": None,
        "category": category,
        "segment": segment or doc_type,
        "sector": sector,
        "run_type": run_type,
        "document_key": document_key,
        "payload": payload,
        "content": content_markdown,
    }
    resp = client.table("documents").upsert(row, on_conflict="date,document_key").execute()
    row_id = _extract_row_id(resp) or document_key
    _audit(
        "publish_document",
        {"document_key": document_key, "date": date_str, "doc_type": doc_type},
    )
    return PublishedArtifact(
        table="documents",
        document_key=document_key,
        row_id=str(row_id),
        published_at=_parse_date(date_str),
    )


def publish_daily_snapshot(
    *,
    client: SupabaseClient,
    date_str: str,
    snapshot: dict[str, Any],
    run_type: str,
    baseline_date: str | None = None,
    digest_markdown: str | None = None,
) -> PublishedArtifact:
    """Upsert one row into ``daily_snapshots`` on ``date``.

    ``snapshot`` is the validated digest payload (matches
    ``templates/digest-snapshot-schema.json``). Stored in the ``snapshot``
    JSONB column; the legacy column set (``bias`` fields, etc.) is populated
    by downstream readers or a follow-up schema migration — not this adapter.
    """
    row = {
        "date": date_str,
        "run_type": run_type,
        "baseline_date": baseline_date,
        "snapshot": snapshot,
        "digest_markdown": digest_markdown,
    }
    resp = client.table("daily_snapshots").upsert(row, on_conflict="date").execute()
    row_id = _extract_row_id(resp) or date_str
    _audit(
        "publish_daily_snapshot",
        {"date": date_str, "run_type": run_type, "baseline_date": baseline_date},
    )
    return PublishedArtifact(
        table="daily_snapshots",
        document_key=None,
        row_id=str(row_id),
        published_at=_parse_date(date_str),
    )


def load_prior_context(
    *,
    client: SupabaseClient,
    run_date: date,
    snapshot_lookback: int = 5,
) -> PriorContext:
    """Query recent ``daily_snapshots`` + latest-per-segment ``documents``.

    Returns a :class:`PriorContext` suitable for populating the
    ``shared_context`` block of every phase node's LLM call — so it's cached
    across the run.
    """
    snapshots_resp = (
        client.table("daily_snapshots")
        .select("date, run_type, baseline_date, snapshot")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(snapshot_lookback)
        .execute()
    )
    last_snapshots: list[dict[str, Any]] = list(getattr(snapshots_resp, "data", None) or [])

    # Latest row per document_key across recent dates. Keep it simple: one
    # query over the last ~30 days, then pick the max-date row per key in Python.
    docs_resp = (
        client.table("documents")
        .select("date, document_key, doc_type, payload")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(200)
        .execute()
    )
    latest_by_key: dict[str, dict[str, Any]] = {}
    for row in getattr(docs_resp, "data", None) or []:
        key = row.get("document_key")
        if key and key not in latest_by_key:
            latest_by_key[key] = row

    # Derive active-theses hint from documents whose doc_type signals a thesis.
    theses = [
        row.get("payload") or {}
        for row in latest_by_key.values()
        if "thesis" in (row.get("doc_type") or "").lower()
    ]

    return PriorContext(
        last_snapshots=last_snapshots,
        latest_segments=latest_by_key,
        active_theses=theses,
    )


def query_price_technicals_freshness(
    *,
    client: SupabaseClient,
) -> tuple[date | None, int]:
    """Return (latest_date, distinct_ticker_count) from ``price_technicals``.

    Used in pre-flight to decide whether to fall back to local fetch scripts
    (mirrors the Data Layer Check in ``skills/orchestrator/SKILL.md``).
    """
    resp = client.table("price_technicals").select("date, ticker").execute()
    rows: list[dict[str, Any]] = list(getattr(resp, "data", None) or [])
    if not rows:
        return None, 0
    dates = [_parse_date(r["date"]) for r in rows if r.get("date")]
    tickers = {r.get("ticker") for r in rows if r.get("ticker")}
    return (max(dates) if dates else None), len(tickers)


def query_macro_series_freshness(
    *,
    client: SupabaseClient,
) -> date | None:
    """Return the latest ``date`` observed in ``macro_series_observations``."""
    resp = (
        client.table("macro_series_observations")
        .select("date")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows: list[dict[str, Any]] = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    return _parse_date(rows[0]["date"])


def _extract_row_id(resp: Any) -> str | None:
    """Supabase client returns a response object with ``.data`` list-of-dicts on success."""
    data = getattr(resp, "data", None)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return str(first.get("id") or first.get("date") or "")
    return None


def _parse_date(raw: str | date) -> date:
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw)[:10])
