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
        missing: list[str] = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_SERVICE_KEY")
        if missing:
            raise SupabaseNotConfiguredError(f"missing required env var(s): {', '.join(missing)}")
        return cls(url=url, service_key=key)


def build_client(cfg: SupabaseConfig) -> SupabaseClient:
    """Construct a live Supabase client from config.

    The ``supabase`` package is an optional extra; this helper defers the
    import so unit tests (which use :class:`FakeSupabaseClient`) never need
    it installed. Production entry points (commit 9's graph compiler) call
    this once at startup.
    """
    from supabase import create_client  # deferred — supabase is an optional dep

    return create_client(cfg.url, cfg.service_key)  # type: ignore[return-value]


def _audit(event_type: str, payload: dict[str, Any]) -> None:
    """Emit an audit line with top-level sensitive keys redacted.

    Contract — important:
    - ``digibase.audit.redact_mapping`` replaces VALUES of keys whose names
      contain ``password|api_key|token|secret``. It does not recurse into
      nested structures and does not pattern-match values.
    - Callers MUST pass only non-sensitive metadata (document_key, date,
      doc_type, run_type). Never pass raw LLM payloads, response bodies,
      or ``content``/``payload``/``snapshot`` blobs — those may contain
      PII or prompt text that the shallow redactor will not scrub.
    - This logger.info call emits to the standard logger; DigiGraph's
      ``audit.py`` wraps that into structured JSONL downstream.
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
    documents_lookback_days: int = 30,
    documents_row_cap: int = 500,
) -> PriorContext:
    """Query recent ``daily_snapshots`` + latest-per-segment ``documents``.

    Returns a :class:`PriorContext` suitable for populating the
    ``shared_context`` block of every phase node's LLM call — so it's cached
    across the run.

    Bounding strategy:
    - ``snapshot_lookback`` rows from ``daily_snapshots`` (default 5).
    - ``documents_lookback_days`` day floor on ``documents`` reads
      (default 30 — a week's baseline + six deltas + slack). Combined with
      ``documents_row_cap`` (default 500) this caps the bytes pulled even
      on extreme churn days; any key whose latest write predates the floor
      is treated as absent, which is the same behavior the sub-graph gets
      on a fresh tenant.
    """
    from datetime import timedelta

    snapshots_resp = (
        client.table("daily_snapshots")
        .select("date, run_type, baseline_date, snapshot")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(snapshot_lookback)
        .execute()
    )
    last_snapshots: list[dict[str, Any]] = list(getattr(snapshots_resp, "data", None) or [])

    # Documents window: [run_date - documents_lookback_days, run_date).
    # Anything older is intentionally ignored — the sub-graph treats a
    # missing segment the same regardless of whether it never existed or
    # simply hasn't been refreshed recently.
    floor = (run_date - timedelta(days=documents_lookback_days)).isoformat()
    docs_resp = (
        client.table("documents")
        .select("date, document_key, doc_type, payload")
        .gte("date", floor)
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(documents_row_cap)
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
    recent_days: int = 7,
) -> tuple[date | None, int]:
    """Return (latest_date, distinct_ticker_count) from ``price_technicals``.

    Used in pre-flight to decide whether to fall back to local fetch scripts
    (mirrors the Data Layer Check in ``skills/orchestrator/SKILL.md``).

    Two bounded queries instead of a full-table scan:
    1. ``order(date desc).limit(1)`` for the latest date.
    2. Rows from the last ``recent_days`` days for the distinct-ticker count.
       A 7-day window matches the orchestrator skill's "within 3 calendar
       days" staleness rule with headroom for weekend / holiday gaps.
    """
    from datetime import timedelta

    latest_resp = (
        client.table("price_technicals").select("date").order("date", desc=True).limit(1).execute()
    )
    latest_rows: list[dict[str, Any]] = list(getattr(latest_resp, "data", None) or [])
    if not latest_rows:
        return None, 0
    latest = _parse_date(latest_rows[0]["date"])

    floor = (latest - timedelta(days=recent_days)).isoformat()
    recent_resp = client.table("price_technicals").select("ticker").gte("date", floor).execute()
    recent_rows: list[dict[str, Any]] = list(getattr(recent_resp, "data", None) or [])
    tickers = {r.get("ticker") for r in recent_rows if r.get("ticker")}
    return latest, len(tickers)


def query_macro_series_freshness(
    *,
    client: SupabaseClient,
) -> date | None:
    """Return the latest obs_date observed in ``macro_series_observations``."""
    resp = (
        client.table("macro_series_observations")
        .select("obs_date")
        .order("obs_date", desc=True)
        .limit(1)
        .execute()
    )
    rows: list[dict[str, Any]] = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    return _parse_date(rows[0]["obs_date"])


def _extract_row_id(resp: Any) -> str | None:
    """Best-effort row identifier from a Supabase upsert response.

    ``PublishedArtifact.row_id`` is used only for audit correlation, not as
    a primary key. We prefer the Postgres ``id`` column when present and
    fall back to the natural key (``date``) if not. Callers whose schemas
    have autogen ids should add ``.select("id")`` to the upsert chain so
    this function finds the real id; otherwise the natural-key fallback
    is intentional and documented. Either way the returned string is a
    stable correlation handle for that upsert.
    """
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
