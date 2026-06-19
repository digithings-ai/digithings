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
from typing import Any, Protocol, TypedDict  # noqa: F401 — Protocol for client surface

from digibase.audit import redact_mapping

from digiquant.olympus.atlas.state import Phase7DigestPayload, PriorContext, PublishedArtifact

logger = logging.getLogger(__name__)


class DocumentRowPayload(TypedDict, total=False):
    """``documents.payload`` JSONB — validated segment report or thesis body (SIMP-013)."""

    segment: str
    date: str
    bias: str
    headline: str
    material_findings: list[Any]
    sources: list[Any]
    notes: str


class DocumentUpsertRow(TypedDict, total=False):
    """``documents`` table upsert shape (SIMP-013)."""

    date: str
    title: str
    doc_type: str | None
    phase: None
    category: str
    segment: str
    sector: str | None
    run_type: str
    document_key: str
    payload: DocumentRowPayload
    content: str | None


class DailySnapshotUpsertRow(TypedDict, total=False):
    """``daily_snapshots`` table upsert shape (SIMP-013)."""

    date: str
    run_type: str
    baseline_date: str | None
    snapshot: Phase7DigestPayload
    digest_markdown: str | None


class DailySnapshotReadRow(TypedDict, total=False):
    """``daily_snapshots`` select shape for prior-context loads (SIMP-013)."""

    date: str
    run_type: str
    baseline_date: str | None
    snapshot: Phase7DigestPayload


class DocumentReadRow(TypedDict, total=False):
    """``documents`` select shape for prior-context loads (SIMP-013)."""

    date: str
    document_key: str
    doc_type: str | None
    payload: DocumentRowPayload


class PriceHistoryRow(TypedDict, total=False):
    """``price_history`` row used by delta / returns helpers (SIMP-013)."""

    date: str
    ticker: str
    close: float | str


class DecisionLogPendingRow(TypedDict, total=False):
    """``decision_log`` pending row for Phase 9 resolution (SIMP-013)."""

    id: str
    run_id: str
    run_date: str
    ticker: str
    stance: str
    conviction: str
    thesis: str
    benchmark: str
    holding_days: int
    status: str


class DecisionLogLessonRow(TypedDict, total=False):
    """Resolved ``decision_log`` row injected into PriorContext (SIMP-013)."""

    id: str
    run_id: str
    run_date: str
    ticker: str
    stance: str
    conviction: str
    thesis: str
    actual_return: float
    alpha: float
    reflection: str
    resolved_at: str


class SupabaseClient(Protocol):
    """Minimal surface we use from the ``supabase`` Python client.

    Defined as a Protocol so tests can inject a fake without pulling the
    supabase dependency. Production callers pass the real ``Client``.
    """

    def table(self, name: str) -> Any: ...  # noqa: D401, E704


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are missing at runtime."""


@dataclass(frozen=True)
class SupabaseConfig:
    """Runtime config. Resolved from env vars by default; override-able in tests."""

    url: str
    service_key: str

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        missing: list[str] = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
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
    payload: DocumentRowPayload,
    doc_type: str | None,
    run_type: str,
    title: str,
    date_str: str,
    category: str = "output",
    segment: str | None = None,
    sector: str | None = None,
    content_markdown: str | None = None,
) -> PublishedArtifact:
    """Upsert one row into ``documents`` on ``(date, document_key)``.

    ``doc_type=None`` is the canonical signal for per-segment Phase 1-5
    documents — the schema's ``chk_documents_doc_type`` constraint allows
    NULL precisely so we don't have to map every segment slug into the
    typed-doc enum. Phase 7 digest / Phase 7D rebalance / custom-research
    rows pass a non-None ``doc_type`` from the constraint allowlist.

    Returns a :class:`PublishedArtifact` that callers append to
    ``AtlasResearchState.published``. Idempotent — replays with the same
    (date, document_key) either update the row or no-op depending on whether
    the payload changed.
    """
    row: DocumentUpsertRow = {
        "date": date_str,
        "title": title,
        "doc_type": doc_type,
        "phase": None,
        "category": category,
        "segment": segment or doc_type or document_key,
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
    snapshot: Phase7DigestPayload,
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
    row: DailySnapshotUpsertRow = {
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


def upsert_onchain_cohort_positioning(
    *,
    client: SupabaseClient,
    rows: list[dict[str, Any]],
) -> int:
    """Idempotently upsert per-(date,market) on-chain cohort positioning rows (#801).

    Returns the number of rows written. A no-op (returns 0) when ``rows`` is empty, so the
    preflight caller can skip cleanly on a Hyperdash outage without a special case. Upserts one
    row at a time on ``(date, market)`` — the per-run market set is small (a handful) and this
    matches the single-dict upsert convention used by every other writer here.
    """
    if not rows:
        return 0
    for row in rows:
        client.table("onchain_cohort_positioning").upsert(row, on_conflict="date,market").execute()
    _audit(
        "upsert_onchain_cohort_positioning",
        {"date": rows[0].get("date"), "row_count": len(rows)},
    )
    return len(rows)


def load_prior_book(
    client: SupabaseClient,
    run_date: date,
    *,
    include_risk_fields: bool = False,
) -> list[dict[str, Any]]:
    """Positions rows for the most recent date strictly before ``run_date``.

    Returns the held book coming into ``run_date`` (newest prior date only),
    or ``[]`` on the first ever run.
    """
    columns = "date, ticker, weight_pct, entry_date"
    if include_risk_fields:
        columns += ", entry_price"
    resp = (
        client.table("positions")
        .select(columns)
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(200)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return []
    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    top_date = str(rows[0].get("date") or "")
    return [r for r in rows if str(r.get("date") or "") == top_date]


# Per-ticker analyst / deliberation docs are loaded separately (slim summaries) so
# ``load_prior_context`` does not stuff full decision artifacts into every node.
_CONTINUITY_EXCLUDED_DOC_PREFIXES = ("analyst/", "deliberation/")

_TERMINAL_THESIS_STATUSES = frozenset({"CLOSED", "INVALIDATED"})


def _slim_analyst_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract PM-relevant fields from a published ``analyst/{ticker}`` payload."""
    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    thesis = str(body.get("thesis") or "").strip()
    return {
        "conviction_score": body.get("conviction_score"),
        "stance": body.get("stance"),
        "thesis_excerpt": thesis[:400],
    }


def load_prior_analyst_summaries(
    client: SupabaseClient,
    run_date: date,
    tickers: list[str] | tuple[str, ...],
    *,
    lookback_days: int = 30,
) -> dict[str, dict[str, Any]]:
    """Latest prior ``analyst/{ticker}`` slim summary per held ticker.

    Returns ``{ticker: {date, document_key, conviction_score, stance, thesis_excerpt}}``.
    Empty when ``tickers`` is empty or no prior analyst docs exist.
    """
    from datetime import timedelta

    if not tickers:
        return {}
    keys = [f"analyst/{t}" for t in tickers]
    floor = (run_date - timedelta(days=lookback_days)).isoformat()
    resp = (
        client.table("documents")
        .select("date, document_key, payload")
        .in_("document_key", list(keys))
        .gte("date", floor)
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .execute()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in getattr(resp, "data", None) or []:
        key = str(row.get("document_key") or "")
        if not key.startswith("analyst/"):
            continue
        ticker = key.split("/", 1)[1]
        if ticker in out:
            continue
        slim = _slim_analyst_summary(row.get("payload") or {})
        out[ticker] = {
            "date": row.get("date"),
            "document_key": key,
            **slim,
        }
    return out


def load_active_theses_rows(
    client: SupabaseClient,
    run_date: date,
    *,
    row_cap: int = 100,
) -> list[dict[str, Any]]:
    """``theses`` rows for the latest date strictly before ``run_date``.

    Excludes terminal statuses (``CLOSED``, ``INVALIDATED``). Empty on first run.
    """
    resp = (
        client.table("theses")
        .select("date, thesis_id, name, vehicle, invalidation, status, notes")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(row_cap)
        .execute()
    )
    rows: list[dict[str, Any]] = list(getattr(resp, "data", None) or [])
    if not rows:
        return []
    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    top_date = str(rows[0].get("date") or "")
    return [
        r
        for r in rows
        if str(r.get("date") or "") == top_date
        and str(r.get("status") or "ACTIVE").upper() not in _TERMINAL_THESIS_STATUSES
    ]


def load_portfolio_performance_snapshot(
    client: SupabaseClient,
    run_date: date,
) -> dict[str, Any]:
    """Latest NAV point before ``run_date`` plus same-day ``portfolio_metrics``."""
    nav_resp = (
        client.table("nav_history")
        .select("date, nav, cash_pct, invested_pct")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    nav_rows: list[dict[str, Any]] = list(getattr(nav_resp, "data", None) or [])
    if not nav_rows:
        return {}
    nav_row = nav_rows[0]
    nav_date = str(nav_row.get("date") or "")
    metrics_resp = (
        client.table("portfolio_metrics")
        .select("date, pnl_pct, sharpe, volatility, max_drawdown, alpha")
        .eq("date", nav_date)
        .limit(1)
        .execute()
    )
    metrics_rows: list[dict[str, Any]] = list(getattr(metrics_resp, "data", None) or [])
    snapshot: dict[str, Any] = {
        "nav_date": nav_date,
        "nav": nav_row.get("nav"),
        "cash_pct": nav_row.get("cash_pct"),
        "invested_pct": nav_row.get("invested_pct"),
    }
    if metrics_rows:
        snapshot["metrics"] = metrics_rows[0]
    return snapshot


def prior_book_current_weights(prior_book: list[dict[str, Any]]) -> dict[str, float]:
    """Map prior ``positions`` rows to ``{ticker: weight_pct}`` for PM phase_inputs."""
    out: dict[str, float] = {}
    for row in prior_book:
        ticker = row.get("ticker")
        if not ticker:
            continue
        try:
            out[str(ticker)] = float(row.get("weight_pct") or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def load_prior_context(
    *,
    client: SupabaseClient,
    run_date: date,
    snapshot_lookback: int = 2,
    documents_lookback_days: int = 30,
    documents_row_cap: int = 500,
) -> PriorContext:
    """Query recent ``daily_snapshots`` + latest-per-segment ``documents``.

    Returns a :class:`PriorContext` suitable for populating the
    ``shared_context`` block of every phase node's LLM call — so it's cached
    across the run.

    Bounding strategy:
    - ``snapshot_lookback`` rows from ``daily_snapshots`` (default 2 — the
      baseline + latest delta; every research node re-serializes these in its
      shared context, so history depth is a direct token-cost multiplier, #696).
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
    last_snapshots: list[DailySnapshotReadRow] = list(getattr(snapshots_resp, "data", None) or [])

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
    latest_by_key: dict[str, DocumentReadRow] = {}
    for row in getattr(docs_resp, "data", None) or []:
        key = row.get("document_key")
        if not key or key in latest_by_key:
            continue
        if any(str(key).startswith(prefix) for prefix in _CONTINUITY_EXCLUDED_DOC_PREFIXES):
            continue
        latest_by_key[key] = row

    return PriorContext(
        last_snapshots=last_snapshots,
        latest_segments=latest_by_key,
        active_theses=[],
    )


def query_price_technicals_freshness(
    *,
    client: SupabaseClient,
    recent_days: int = 7,
) -> tuple[date | None, int]:
    """Return (latest_date, distinct_ticker_count) from ``price_technicals``.

    Used in pre-flight to decide whether to fall back to local fetch scripts
    (used by the preflight phase Data Layer Check).

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


def query_price_deltas(
    *,
    client: SupabaseClient,
    tickers: tuple[str, ...],
    run_date: date,
    lookback_days: int = 14,
) -> dict[str, float]:
    """Return ``{ticker: pct_change}`` over the latest pair of trading days
    in ``price_history`` strictly before ``run_date``.

    Trading-day vs. calendar-day handling is the load-bearing part:
    ``run_date - 1`` and ``run_date - 2`` would land on weekends or holidays
    every Monday and after every market close. Instead we fetch the most
    recent ``lookback_days`` of price rows (default 14 — covers any
    long-weekend gap with headroom) for the requested tickers, then per-
    ticker pick the latest two distinct dates and compute
    ``(close_t - close_t-1) / close_t-1``.

    Missing tickers / single-row tickers / zero-prior-close tickers are
    silently dropped from the result — the rule evaluators interpret a
    missing key as "no signal, regenerate" (conservative default that
    matches the existing triage docstring).

    The query is bounded:
    - ``in_(tickers)`` filters server-side, so we never pull rows for
      tickers we don't track.
    - ``lookback_days`` floors the date range to a small window so the
      response stays tiny even with weeks of Atlas history.
    """
    from datetime import timedelta

    if not tickers:
        return {}

    floor = (run_date - timedelta(days=lookback_days)).isoformat()
    resp = (
        client.table("price_history")
        .select("date, ticker, close")
        .in_("ticker", list(tickers))
        .gte("date", floor)
        .lt("date", run_date.isoformat())
        .execute()
    )
    rows: list[PriceHistoryRow] = list(getattr(resp, "data", None) or [])

    # Group by ticker, sort each group by date desc, take the top two
    # distinct dates, compute pct_change. Avoids any dataframe import — this
    # is small categorical data per the triage scope (single-digit dozens of
    # tickers, two-digit row counts).
    by_ticker: dict[str, list[PriceHistoryRow]] = {}
    for r in rows:
        t = r.get("ticker")
        if not isinstance(t, str):
            continue
        by_ticker.setdefault(t, []).append(r)

    deltas: dict[str, float] = {}
    for ticker, ticker_rows in by_ticker.items():
        # Sort newest first; dedupe same-date duplicates by keeping the first.
        ticker_rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
        seen_dates: set[str] = set()
        deduped: list[PriceHistoryRow] = []
        for r in ticker_rows:
            d = str(r.get("date") or "")
            if not d or d in seen_dates:
                continue
            seen_dates.add(d)
            deduped.append(r)
            if len(deduped) == 2:
                break
        if len(deduped) < 2:
            continue
        prev_close = _coerce_close(deduped[1].get("close"))
        latest_close = _coerce_close(deduped[0].get("close"))
        if prev_close is None or latest_close is None or prev_close == 0:
            continue
        deltas[ticker] = (latest_close - prev_close) / prev_close
    return deltas


def _coerce_close(val: Any) -> float | None:
    """Best-effort numeric coercion for a ``price_history.close`` cell.

    The column is ``numeric`` in Postgres which the Supabase Python client
    surfaces as a string in some configurations and as a float in others.
    A non-coercible value is treated as missing (returns ``None``) rather
    than raising — triage falls back to regenerate on missing data anyway.
    """
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def query_pending_decisions(
    *,
    client: SupabaseClient,
    run_date: date,
    holding_days_default: int = 5,
) -> list[DecisionLogPendingRow]:
    """Return ``decision_log`` rows where ``status='pending'`` and the holding
    window has elapsed.

    The "due" filter is applied client-side instead of in SQL because the
    relevant comparison is ``row.run_date + row.holding_days <= run_date`` —
    that's a per-row date arithmetic that PostgREST does not expose as a
    composable filter. We pull all pending rows whose ``run_date`` is at
    least ``holding_days_default`` calendar days old (server-side bound) and
    let the resolver finish the trading-day-aware check via ``price_history``.

    The bound is conservative: rows with ``holding_days < holding_days_default``
    are still due strictly earlier so they show up in the window; rows with
    ``holding_days > holding_days_default`` may show up early but the resolver
    skips them when their ticker has fewer than ``holding_days`` trading days
    of price data (graceful skip behavior — see ``decision_log.resolve_pending``).
    """
    from datetime import timedelta

    floor = (run_date - timedelta(days=holding_days_default)).isoformat()
    resp = (
        client.table("decision_log")
        .select(
            "id, run_id, run_date, ticker, stance, conviction, thesis, "
            "benchmark, holding_days, status"
        )
        .eq("status", "pending")
        # ``<=`` not ``<``: a decision dated exactly ``floor`` (= run_date − holding_days_default)
        # is due today (floor + holding_days_default == run_date), so it must be included.
        # ``<`` dropped that boundary row, delaying its resolution by a day (#726, 3A).
        .lte("run_date", floor)
        .order("run_date", desc=False)
        .execute()
    )
    return list(getattr(resp, "data", None) or [])


def query_returns_window(
    *,
    client: SupabaseClient,
    ticker: str,
    start_date: date,
    holding_days: int,
    lookback_days: int = 21,
) -> tuple[float, date, date] | None:
    """Compute ``(close_end - close_start) / close_start`` for ``ticker`` over
    a trading-day-aware window starting at or after ``start_date``.

    Returns ``(return_pct, start_date_used, end_date_used)`` or ``None`` when
    fewer than ``holding_days + 1`` distinct trading days are available in
    ``price_history`` between ``start_date`` and ``start_date +
    holding_days + lookback_days``. The ``+1`` accounts for the entry-day
    close needed to compute the first return.

    Trading-day handling: we don't filter against ``trading_calendar`` here —
    ``price_history`` only contains rows for actual trading days, so picking
    ordered distinct dates is equivalent. Mirrors the approach in
    :func:`query_price_deltas`.

    Missing data → ``None`` (caller skips the row gracefully — see
    AC #7 of the issue: "missing returns data skips resolution").
    """
    from datetime import timedelta

    if holding_days < 1:
        return None

    # Pull a wide-enough window: ``holding_days + lookback_days`` covers
    # weekends, holidays, and trailing gaps. Filtering ``ticker`` server-side
    # keeps the response tiny.
    end_floor = (start_date + timedelta(days=holding_days + lookback_days)).isoformat()
    resp = (
        client.table("price_history")
        .select("date, close")
        .eq("ticker", ticker)
        .gte("date", start_date.isoformat())
        .lt("date", end_floor)
        .order("date", desc=False)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None

    # De-duplicate by date and order ascending. The fake supabase client and
    # real PostgREST may both surface duplicates if ETL inserts a forward-fill
    # row; we keep the first close per date.
    by_date: dict[str, float] = {}
    for r in rows:
        d = str(r.get("date") or "")
        c = _coerce_close(r.get("close"))
        if not d or c is None or d in by_date:
            continue
        by_date[d] = c
    if len(by_date) < holding_days + 1:
        return None

    sorted_dates = sorted(by_date.keys())
    start_iso = sorted_dates[0]
    end_iso = sorted_dates[holding_days]  # offset by N trading days from start
    start_close = by_date[start_iso]
    end_close = by_date[end_iso]
    if start_close == 0:
        return None
    return (
        (end_close - start_close) / start_close,
        _parse_date(start_iso),
        _parse_date(end_iso),
    )


def update_decision_resolution(
    *,
    client: SupabaseClient,
    row_id: str,
    actual_return: float,
    alpha: float,
    reflection: str,
    resolved_at: str,
) -> None:
    """Mark a single pending ``decision_log`` row as resolved.

    The ``status='pending'`` filter on the update is the idempotency guard:
    if some other process resolved this row first (or this resolver replays
    after a partial failure), the row's already-resolved reflection is
    preserved instead of being clobbered. AC #8 of the issue requires that
    re-running Phase 9 must not overwrite a prior reflection.
    """
    payload = {
        "status": "resolved",
        "actual_return": actual_return,
        "alpha": alpha,
        "reflection": reflection,
        "resolved_at": resolved_at,
    }
    client.table("decision_log").update(payload).eq("id", row_id).eq("status", "pending").execute()
    _audit("update_decision_resolution", {"id": row_id, "alpha": alpha})


def query_recent_lessons(
    *,
    client: SupabaseClient,
    run_date: date,
    tickers: tuple[str, ...] = (),
    same_ticker_limit: int = 5,
    cross_ticker_limit: int = 3,
) -> list[DecisionLogLessonRow]:
    """Return resolved lessons for PriorContext injection.

    Strategy (matches the issue body's "last 5 same-ticker + 3 cross-ticker"):
    - For each ticker in ``tickers`` (typically the current watchlist), pull
      the latest ``same_ticker_limit`` resolved rows.
    - Add the latest ``cross_ticker_limit`` resolved rows whose ticker is NOT
      in ``tickers`` — keeps a small cross-pollination signal so the PM sees
      lessons even on fresh-watchlist tickers.

    All rows are dicts shaped for the LLM prompt (no Pydantic model — keeps
    PriorContext storage simple). De-duplicates by id in case a ticker
    appears in both the same-ticker and cross-ticker buckets (shouldn't, but
    cheap to guard).
    """
    out: list[DecisionLogLessonRow] = []
    seen_ids: set[str] = set()

    select_cols = (
        "id, run_id, run_date, ticker, stance, conviction, thesis, "
        "actual_return, alpha, reflection, resolved_at"
    )

    for ticker in tickers:
        resp = (
            client.table("decision_log")
            .select(select_cols)
            .eq("status", "resolved")
            .eq("ticker", ticker)
            .lt("run_date", run_date.isoformat())
            .order("run_date", desc=True)
            .limit(same_ticker_limit)
            .execute()
        )
        for row in getattr(resp, "data", None) or []:
            rid = str(row.get("id") or "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                out.append(row)

    if cross_ticker_limit > 0:
        # Over-fetch so the post-filter (skip rows whose ticker is in
        # ``tickers``) still leaves enough cross-ticker rows. The factor
        # accounts for the worst case where every same-day row belongs to
        # a watchlist ticker — in practice the watchlist is small and
        # cross-ticker activity is dense, so the over-fetch stays bounded.
        over_fetch_factor = max(1, len(tickers) + 1)
        resp = (
            client.table("decision_log")
            .select(select_cols)
            .eq("status", "resolved")
            .lt("run_date", run_date.isoformat())
            .order("run_date", desc=True)
            .limit(cross_ticker_limit * over_fetch_factor + cross_ticker_limit)
            .execute()
        )
        added = 0
        for row in getattr(resp, "data", None) or []:
            if added >= cross_ticker_limit:
                break
            if row.get("ticker") in tickers:
                continue
            rid = str(row.get("id") or "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                out.append(row)
                added += 1
    return out


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
