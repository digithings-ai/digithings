"""H9 terminal I/O — portfolio booking, brief publish, commit manifest (#932)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)
from uuid import UUID

from digiquant.olympus.atlas.decision_log import persist_pending
from digiquant.olympus.atlas.pretrade_risk_registry import (
    PreTradeRiskRegistryConflict,
    PreTradeRiskRegistryWriteResult,
    persist_pretrade_risk_report,
    pretrade_risk_report_id,
)
from digiquant.olympus.atlas.state import AtlasResearchState, PublishedArtifact, RebalancePayload
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_prior_book,
    publish_document,
)
from digiquant.olympus.hermes.allocation_contracts import PreTradeRiskReport
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.risk_envelope import risk_horizon_days
from digiquant.olympus.hermes.sector_map import sector_bucket
from digiquant.olympus.tenancy import house_workspace_id

logger = logging.getLogger(__name__)

_SEED_NAV = 100.0
_RISK_FIELDS_ENV = "OLYMPUS_POSITION_RISK_FIELDS"
_PRETRADE_RISK_MODE_ENV = "OLYMPUS_PRETRADE_RISK_MODE"
_ATR_STOP_MULT = 2.0
_ATR_TARGET_MULT = 3.0
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0
_MANIFEST_DOC_PREFIX = "commit-run/"
_MANIFEST_SEQ_FIELD = "commit_seq"

# NAV interval window (#1745). ``_interval_price_returns`` needs one close at or
# before the prior book date, so the fetch floor is padded below it; the interval
# itself is capped so a pathological book gap cannot turn one commit into an
# unbounded ``price_history`` scan.
_NAV_INTERVAL_PAD_DAYS = 7
_NAV_MAX_INTERVAL_DAYS = 120
# Worst-case ``price_history`` window for ``_interval_price_returns``: the interval is
# capped at ``_NAV_MAX_INTERVAL_DAYS`` and the fetch floor is padded below the anchor.
_NAV_INTERVAL_WINDOW_DAYS = _NAV_MAX_INTERVAL_DAYS + _NAV_INTERVAL_PAD_DAYS
_NAV_INTERVAL_ROW_BUDGET = 900
_NAV_INTERVAL_TICKER_BATCH = max(1, _NAV_INTERVAL_ROW_BUDGET // (_NAV_INTERVAL_WINDOW_DAYS + 1))


def _position_risk_fields_enabled() -> bool:
    return os.environ.get(_RISK_FIELDS_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _coerce_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _is_cash(ticker: Any) -> bool:
    return isinstance(ticker, str) and ticker.strip().upper() == "CASH"


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp_conviction(value: float) -> float:
    return max(_CONVICTION_FLOOR, min(_CONVICTION_CAP, value))


def _effective_conviction(analyst: Any, debate: Any) -> float | None:
    base = _opt_float((analyst or {}).get("conviction_score"))
    if base is None:
        return None
    delta = _opt_float((debate or {}).get("conviction_delta")) or 0.0
    return round(_clamp_conviction(base + delta), 2)


def _prior_nav(client: SupabaseClient, run_date: date) -> float:
    resp = (
        client.table("nav_history")
        .select("date, nav")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return _SEED_NAV
    nav = _coerce_float(rows[0].get("nav"))
    return nav if nav > 0 else _SEED_NAV


def _prior_book_date(prior_book: list[dict[str, Any]]) -> date | None:
    """The single date ``load_prior_book`` returned rows for, or ``None``.

    The weights and the interval start must come from the *same* row set or the
    NAV return is computed over a window the book was not actually held for, so
    this reads the ``date`` column off the prior-book rows rather than
    re-deriving it from ``nav_history`` (which the metrics cron may extend to
    bookless dates — see the ownership contract in ``hermes/docs/ARCHITECTURE.md``).
    """
    for row in prior_book:
        raw = row.get("date")
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str) and raw:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    return None


def _interval_price_returns(
    *,
    client: SupabaseClient,
    tickers: tuple[str, ...],
    start_date: date,
    run_date: date,
) -> dict[str, float]:
    """``{ticker: pct_change}`` from the ``start_date`` close to the last close before ``run_date``.

    A *new* helper rather than a change to ``atlas.supabase_io.query_price_deltas``
    (#1745): that function is deliberately a one-trading-day signal shared with the
    triage rule evaluators, and re-pointing it at an interval would silently change
    every rule threshold calibrated against it.

    Why an interval and not the latest pair of trading days: ``nav_history`` is
    restated every evening by the metrics cron to "NAV as of this date's close", so
    ``_prior_nav`` already embeds the move up to the prior book date. Multiplying it
    by the latest one-day delta double-counts that move on a dense series (verified
    on 2026-07-28: the manifest applied the 07-24→07-27 return that ``nav_history``
    had already absorbed into 07-27) and *loses* the move entirely across a gap
    (2026-06-26 → 07-17 recorded +0.03% for a book that actually returned -0.37%).
    Anchoring on the prior book date makes both cases exact.

    Same conservative-drop contract as ``query_price_deltas``: a ticker with no
    usable close pair is omitted, and the caller treats a missing key as 0.0 —
    a name we cannot price must not move the index.
    """
    if not tickers or start_date >= run_date:
        return {}

    floor_from_cap = run_date - timedelta(days=_NAV_MAX_INTERVAL_DAYS)
    anchor = max(start_date, floor_from_cap)
    if anchor != start_date:
        logger.warning(
            "commit_io: NAV interval %s→%s exceeds the %d-day cap; anchoring at %s",
            start_date.isoformat(),
            run_date.isoformat(),
            _NAV_MAX_INTERVAL_DAYS,
            anchor.isoformat(),
        )

    floor = (anchor - timedelta(days=_NAV_INTERVAL_PAD_DAYS)).isoformat()
    anchor_str = anchor.isoformat()
    ordered = sorted(tickers)
    # Per ticker keep the latest close at-or-before the anchor (interval start) and
    # the latest close strictly before run_date (interval end). Small categorical
    # data — batched so a full window for every ticker fits under PostgREST's cap.
    begin: dict[str, tuple[str, float]] = {}
    end: dict[str, tuple[str, float]] = {}
    for start in range(0, len(ordered), _NAV_INTERVAL_TICKER_BATCH):
        resp = (
            client.table("price_history")
            .select("date, ticker, close")
            .in_("ticker", ordered[start : start + _NAV_INTERVAL_TICKER_BATCH])
            .gte("date", floor)
            .lt("date", run_date.isoformat())
            .execute()
        )
        for row in getattr(resp, "data", None) or []:
            ticker = row.get("ticker")
            row_date = row.get("date")
            close = _opt_float(row.get("close"))
            if not isinstance(ticker, str) or not isinstance(row_date, str) or close is None:
                continue
            if row_date <= anchor_str and row_date > begin.get(ticker, ("", 0.0))[0]:
                begin[ticker] = (row_date, close)
            if row_date > end.get(ticker, ("", 0.0))[0]:
                end[ticker] = (row_date, close)

    returns: dict[str, float] = {}
    for ticker, (begin_date, begin_close) in begin.items():
        end_entry = end.get(ticker)
        if end_entry is None or begin_close <= 0:
            continue
        end_date, end_close = end_entry
        if end_date <= begin_date:
            # No close after the anchor: the prior NAV is already as-of the latest
            # available close, so the book has not moved since it was booked.
            returns[ticker] = 0.0
            continue
        returns[ticker] = (end_close - begin_close) / begin_close
    return returns


def _compute_nav(client: SupabaseClient, run_date: date, prior_book: list[dict[str, Any]]) -> float:
    """NAV for ``run_date`` = prior NAV compounded by the prior book's interval return.

    See :func:`_interval_price_returns` for why the return is measured over the
    interval since the prior book date rather than the latest one-day delta (#1745).
    """
    prior_nav = _prior_nav(client, run_date)
    held = {
        str(r.get("ticker")): _coerce_float(r.get("weight_pct"))
        for r in prior_book
        if r.get("ticker") and not _is_cash(r.get("ticker"))
    }
    book_date = _prior_book_date(prior_book)
    if not held or book_date is None:
        return round(prior_nav, 6)
    returns = _interval_price_returns(
        client=client, tickers=tuple(held), start_date=book_date, run_date=run_date
    )
    port_return = sum((w / 100.0) * returns.get(t, 0.0) for t, w in held.items())
    return round(prior_nav * (1.0 + port_return), 6)


def _latest_values(
    client: SupabaseClient,
    table: str,
    value_col: str,
    tickers: list[str],
    run_date: date,
    *,
    lookback_days: int = 14,
) -> dict[str, float]:
    """``{ticker: value_col}`` from the latest row ≤ run_date per ticker (look-ahead-guarded).

    We only need each ticker's *most recent* value inside a short ``lookback_days``
    window. ``.order("date", desc=True)`` ensures truncation drops the *oldest* rows,
    so every ticker still resolves from the leading page — not because the requested
    ``.limit`` can exceed PostgREST's server-side row cap. Fail-soft on read errors.
    """
    if not tickers:
        return {}
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    try:
        resp = (
            client.table(table)
            .select(f"ticker,date,{value_col}")
            .in_("ticker", list(tickers))
            .lte("date", run_date.isoformat())
            .gte("date", since)
            .order("date", desc=True)
            .limit(len(tickers) * (lookback_days + 1))
            .execute()
        )
    except Exception as exc:  # advisory fields must never block the book
        logger.warning(
            "commit_io: %s.%s read failed (%s); risk fields degrade", table, value_col, exc
        )
        return {}
    out: dict[str, float] = {}
    for row in getattr(resp, "data", None) or []:
        ticker = row.get("ticker")
        if isinstance(ticker, str) and ticker not in out:
            value = _opt_float(row.get(value_col))
            if value is not None:
                out[ticker] = value
    return out


def _enrich_positions(
    *,
    client: SupabaseClient,
    run_date: date,
    date_str: str,
    pos_rows: list[dict[str, Any]],
    prior_book: list[dict[str, Any]],
    analysts: dict[str, Any],
    debates: dict[str, Any],
    preferences: dict[str, Any],
) -> None:
    tickers = [str(r["ticker"]) for r in pos_rows if not _is_cash(r.get("ticker"))]
    if not tickers:
        return
    prior = {str(r.get("ticker")): r for r in prior_book if r.get("ticker")}
    closes = _latest_values(client, "price_history", "close", tickers, run_date)
    atr_pct = _latest_values(client, "price_technicals", "atr_pct", tickers, run_date)
    horizon_days = risk_horizon_days(preferences)

    for row in pos_rows:
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or _is_cash(ticker):
            continue
        prev = prior.get(ticker) or {}
        prev_entry = _opt_float(prev.get("entry_price"))
        if prev_entry is not None and prev_entry > 0:
            row["entry_price"] = round(prev_entry, 6)
            row["entry_date"] = prev.get("entry_date") or date_str
        else:
            close = closes.get(ticker)
            if close is not None and close > 0:
                row["entry_price"] = round(close, 6)
            row["entry_date"] = date_str

        conviction = _effective_conviction(analysts.get(ticker), debates.get(ticker))
        if conviction is not None:
            row["conviction"] = conviction
        row["sector_bucket"] = sector_bucket(ticker)
        row["horizon_days"] = horizon_days

        atr = atr_pct.get(ticker)
        if atr is not None and atr > 0:
            row["stop_loss_pct"] = round(-_ATR_STOP_MULT * atr, 4)
            row["target_pct_gain"] = round(_ATR_TARGET_MULT * atr, 4)


def _action_rationale_by_ticker(book: RebalancePayload | dict[str, Any]) -> dict[str, str]:
    """Per-ticker rationale from H8 ``actions`` for ``positions`` booking (#2597)."""
    out: dict[str, str] = {}
    for action in book.get("actions") or []:
        if not isinstance(action, dict):
            continue
        ticker = action.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        rationale = str(action.get("rationale") or "").strip()
        if rationale:
            out[ticker.strip().upper()] = rationale
    return out


def weights_from_sized_book(book: RebalancePayload | dict[str, Any]) -> dict[str, float]:
    """Normalize H8 ``recommended_portfolio`` into non-CASH positive weights."""
    recommended = book.get("recommended_portfolio") or []
    weights: dict[str, float] = {}
    for row in recommended:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker or _is_cash(ticker):
            continue
        weight = _coerce_float(row.get("target_pct"))
        if weight <= 0:
            continue
        weights[ticker] = weights.get(ticker, 0.0) + weight

    gross = sum(weights.values())
    if gross > 100.0:
        scale = 100.0 / gross
        weights = {t: w * scale for t, w in weights.items()}
    return weights


def weights_fingerprint(weights: dict[str, float]) -> str:
    """Stable hash for idempotency comparisons."""
    from digiquant.olympus.hermes.allocation_hashes import weights_fingerprint as _weights_fp

    return _weights_fp(weights)


def _canonical_thesis_ids(
    client: SupabaseClient,
    run_date: date,
    tickers: list[str],
) -> dict[str, str]:
    """Return {ticker: canonical_thesis_id} for the given tickers on run_date.

    Queries thesis_vehicles (indexed on ticker, date DESC) in one round trip.
    Falls back to the vehicle-{ticker.lower()} convention for any ticker that
    has no entry — consistent with upsert_vehicle_thesis_from_analyst.
    """
    if not tickers:
        return {}
    try:
        resp = (
            client.table("thesis_vehicles")
            .select("thesis_id, ticker")
            .eq("date", run_date.isoformat())
            .in_("ticker", tickers)
            .execute()
        )
        rows = list(getattr(resp, "data", None) or [])
    except Exception:  # thesis lookup must never block booking
        rows = []
    # Latest-date row wins when multiple theses cover the same ticker.
    return {str(r["ticker"]): str(r["thesis_id"]) for r in rows if r.get("thesis_id")}


def _prune_orphan_positions(
    *,
    client: SupabaseClient,
    date_str: str,
    keep: set[str],
    workspace_id: str | None = None,
) -> list[str]:
    """Delete same-date ``positions`` rows absent from the book just written (#1744).

    ``positions`` is upserted on ``(date, ticker)``, so a second commit for the same
    date that *drops* a name leaves the dropped row behind at its old weight — the
    book then sums above 100% of NAV and reports a position no run intended to hold.
    ``refresh_performance_metrics`` sums non-CASH ``weight_pct`` into
    ``portfolio_metrics.invested_pct`` and ``execute_at_open.build_events_from_positions_book``
    derives OPEN/TRIM/EXIT from this table, so an orphan becomes both an inflated
    dashboard metric and a phantom Activity-feed event.

    ``keep`` carries CASH only when ``cash_pct > 0.01``, so a re-commit that goes
    fully invested also clears the stale CASH row that would otherwise contradict
    ``nav_history.cash_pct``.

    Deliberately **not** fail-soft: a silently-surviving orphan is the defect this
    closes, and it corrupts a published performance series rather than degrading an
    advisory field. The cost is honest — a raise here lands *after* the book is written
    and *before* ``save_commit_manifest``, leaving a booked-but-unmanifested date. That
    gap already existed; what the date-keyed guard adds is that the next attempt
    re-commits and re-prunes instead of stacking a second book on top.

    The two sibling scripts that already implement this pattern
    (``sync_positions_from_rebalance.py``, ``materialize_snapshot.py``) issue one
    DELETE per orphan; this issues a single ``in_`` delete instead — same effect,
    one round trip.

    T0 (#5-T0) used a date-only filter. T4 threads ``workspace_id`` for overlay
    so a private book cannot prune house rows. ``workspace_id is None`` keeps the
    house query byte-identical (date-only).
    """
    query = client.table("positions").select("ticker").eq("date", date_str)
    if workspace_id is not None:
        query = query.eq("workspace_id", workspace_id)
    resp = query.execute()
    existing = {
        str(row.get("ticker")) for row in getattr(resp, "data", None) or [] if row.get("ticker")
    }
    orphans = sorted(existing - keep)
    if not orphans:
        return []
    delete = client.table("positions").delete().eq("date", date_str)
    if workspace_id is not None:
        delete = delete.eq("workspace_id", workspace_id)
    delete.in_("ticker", orphans).execute()
    logger.warning(
        "commit_io: pruned %d orphan position row(s) for %s not in the committed book: %s",
        len(orphans),
        date_str,
        orphans,
    )
    return orphans


@dataclass(frozen=True)
class BookedPortfolio:
    """Result of booking H8 weights into ``positions`` + ``nav_history``."""

    weights: dict[str, float]
    cash_pct: float
    invested_pct: float
    nav: float
    position_rows: list[dict[str, Any]]
    pruned_tickers: list[str] = field(default_factory=list)


def book_portfolio(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    book: RebalancePayload | dict[str, Any],
) -> BookedPortfolio:
    """Upsert ``positions`` + ``nav_history`` from H8 weights only."""
    run_date = state.run_date
    date_str = run_date.isoformat()
    weights = weights_from_sized_book(book)
    gross = sum(weights.values())
    invested = round(gross, 4)
    cash_pct = max(0.0, round(100.0 - invested, 4))

    canonical_ids = _canonical_thesis_ids(client, run_date, list(weights))
    pos_rows: list[dict[str, Any]] = [
        {
            "date": date_str,
            "ticker": t,
            "weight_pct": round(w, 4),
            "thesis_id": canonical_ids.get(t, f"vehicle-{t.lower()}"),
        }
        for t, w in weights.items()
    ]
    rationale_by_ticker = _action_rationale_by_ticker(book)
    for row in pos_rows:
        rationale = rationale_by_ticker.get(str(row["ticker"]).strip().upper())
        if rationale:
            row["rationale"] = rationale

    prior_book = load_prior_book(
        client,
        run_date,
        include_risk_fields=_position_risk_fields_enabled(),
        workspace_id=getattr(state.config, "workspace_id", None),
    )
    nav = _compute_nav(client, run_date, prior_book)

    if _position_risk_fields_enabled():
        try:
            _enrich_positions(
                client=client,
                run_date=run_date,
                date_str=date_str,
                pos_rows=pos_rows,
                prior_book=prior_book,
                analysts=analyst_payloads(state),
                debates=deliberation_summaries(state),
                preferences=dict(state.config.preferences),
            )
        except Exception as exc:  # advisory fields must never block the book
            logger.warning(
                "commit_io: position risk-field enrichment failed (%s); booking plain weights",
                exc,
                exc_info=True,
            )
            pos_rows = [
                {
                    "date": date_str,
                    "ticker": r["ticker"],
                    "weight_pct": r["weight_pct"],
                    **({"thesis_id": r["thesis_id"]} if r.get("thesis_id") else {}),
                }
                for r in pos_rows
            ]

    # T0 stamped house_workspace_id(). T4 overlay threads config.workspace_id
    # through the pin seam; omitting it keeps the house stamp byte-identical.
    overlay_ws = getattr(state.config, "workspace_id", None)
    workspace_id = str(house_workspace_id()) if not overlay_ws else str(overlay_ws)

    client.table("nav_history").upsert(
        {
            "workspace_id": workspace_id,
            "date": date_str,
            "nav": nav,
            "cash_pct": cash_pct,
            "invested_pct": round(invested, 4),
        },
        on_conflict="workspace_id,date",
    ).execute()

    if cash_pct > 0.01:
        pos_rows.append(
            {
                "date": date_str,
                "ticker": "CASH",
                "weight_pct": cash_pct,
                "category": "fixed_income_cash",
            }
        )

    for row in pos_rows:
        row["workspace_id"] = workspace_id
        client.table("positions").upsert(row, on_conflict="workspace_id,date,ticker").execute()

    # Upsert first, then prune: the inverse order would leave a window in which the
    # date has no book at all.
    pruned = _prune_orphan_positions(
        client=client,
        date_str=date_str,
        keep={str(r["ticker"]) for r in pos_rows},
        workspace_id=overlay_ws,
    )

    return BookedPortfolio(
        weights=weights,
        cash_pct=cash_pct,
        invested_pct=round(invested, 4),
        nav=nav,
        position_rows=pos_rows,
        pruned_tickers=pruned,
    )


OVERLAY_MANIFEST_PREFIX = "overlay-commit/"


def manifest_document_key(source_run_id: str, workspace_id: str | None = None) -> str:
    """House keys stay ``commit-run/{run_id}``. Overlay is namespaced so a
    date-scoped house lookup cannot see (or last-writer-wins over) a private book.
    """
    if workspace_id:
        return f"{OVERLAY_MANIFEST_PREFIX}{workspace_id}/{source_run_id}"
    return f"{_MANIFEST_DOC_PREFIX}{source_run_id}"


def load_commit_manifests(
    *,
    client: SupabaseClient,
    run_date: date,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    """Every commit manifest already persisted for ``run_date`` (#1744).

    Keyed on the **date**, never on ``source_run_id``. ``AtlasResearchState.run_id``
    is a fresh ``uuid4()`` per process, so CI's outer retry always presents a new id
    and a run_id-keyed lookup structurally *cannot* see the manifest an earlier
    attempt on the same date wrote — the guard was dead across exactly the retries it
    existed to cover. Migration 044 re-keyed ``decision_log`` from ``(run_id, ticker)``
    to ``(run_date, ticker)`` for this same reason (#947); the commit manifest never
    got the same treatment, and 2026-06-24 carries three manifests with three
    different ``weights_fingerprint`` values as the proof.

    The manifest *document* stays per-run (``commit-run/{source_run_id}``) so each
    attempt keeps its own audit artefact; only the idempotency lookup is date-scoped.
    """
    date_str = run_date.isoformat()
    prefix = f"{OVERLAY_MANIFEST_PREFIX}{workspace_id}/" if workspace_id else _MANIFEST_DOC_PREFIX
    out: list[dict[str, Any]] = []

    store = getattr(client, "store", None)
    if isinstance(store, dict):
        for row in store.get("documents", []):
            key = row.get("document_key")
            if row.get("date") == date_str and isinstance(key, str) and key.startswith(prefix):
                payload = row.get("payload")
                if isinstance(payload, dict):
                    out.append(dict(payload))
    if out:
        return out

    resp = (
        client.table("documents")
        .select("payload")
        .eq("date", date_str)
        .like("document_key", f"{prefix}%")
        .execute()
    )
    for row in getattr(resp, "data", None) or []:
        payload = row.get("payload")
        if isinstance(payload, dict):
            out.append(dict(payload))
    return out


def manifest_commit_seq(manifest: dict[str, Any]) -> int:
    """``commit_seq`` of a manifest; ``0`` for pre-#1744 manifests that carry none."""
    try:
        return int(manifest.get(_MANIFEST_SEQ_FIELD) or 0)
    except (TypeError, ValueError):
        return 0


def resolve_prior_commit(
    manifests: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, int]:
    """Return ``(unambiguously-latest manifest | None, next commit_seq)``.

    ``documents`` has no ``created_at``/``updated_at`` column, so ordering comes from
    ``commit_seq`` inside the payload we control. Legacy manifests all read 0, which
    on a date with several of them (2026-06-24) makes "latest" genuinely undecidable
    — so this returns ``None`` rather than guess. ``None`` means "re-commit", which is
    always safe now that booking prunes orphans: matching a fingerprint against a
    manifest that is *not* the last writer would otherwise report "already booked"
    while the rows on disk belong to a different book.
    """
    if not manifests:
        return None, 1
    top = max(manifest_commit_seq(m) for m in manifests)
    at_top = [m for m in manifests if manifest_commit_seq(m) == top]
    return (at_top[0] if len(at_top) == 1 else None), top + 1


def save_commit_manifest(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    manifest: dict[str, Any],
) -> PublishedArtifact:
    source_run_id = str(state.run_id)
    date_str = state.run_date.isoformat()
    return publish_document(
        client=client,
        document_key=manifest_document_key(
            source_run_id, getattr(state.config, "workspace_id", None)
        ),
        payload=manifest,
        doc_type="Commit Run",
        run_type=state.run_type,
        title=f"Commit Run {date_str}",
        date_str=date_str,
        category="portfolio",
        segment="commit_run",
    )


def publish_portfolio_brief(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    book: RebalancePayload | dict[str, Any],
) -> PublishedArtifact:
    """Publish operator brief — weights from H8 ``sized_book`` only.

    ``adjustments`` and ``requested_pct`` are excluded from the document payload:
    H9 persists them on the portfolio ledger (#2768); carrying them into the
    ``pm-rebalance`` document would duplicate lineage without a reader contract.
    """
    date_str = state.run_date.isoformat()
    payload = {k: v for k, v in dict(book).items() if k not in {"adjustments", "requested_pct"}}
    return publish_document(
        client=client,
        document_key="pm-rebalance",
        payload=payload,
        doc_type="Rebalance Decision",
        run_type=state.run_type,
        title=f"PM Rebalance {date_str}",
        date_str=date_str,
        category="portfolio",
    )


def publish_hermes_documents(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
) -> list[PublishedArtifact]:
    """Publish H5/H6/H7 artifacts not covered by Atlas publish."""
    date_str = state.run_date.isoformat()
    run_type = state.run_type
    artifacts: list[PublishedArtifact] = []

    for ticker, payload in analyst_payloads(state).items():
        artifacts.append(
            publish_document(
                client=client,
                document_key=f"analyst/{ticker}",
                payload=dict(payload),
                doc_type=None,
                run_type=run_type,
                title=f"{ticker} analyst {date_str}",
                date_str=date_str,
                category="deep-dive",
                segment="analyst",
                sector=ticker,
            )
        )

    for ticker, debate in deliberation_summaries(state).items():
        if not isinstance(debate, dict) or "net_stance" not in debate:
            continue
        artifacts.append(
            publish_document(
                client=client,
                document_key=f"deliberation/{ticker}",
                payload=dict(debate),
                doc_type=None,
                run_type=run_type,
                title=f"{ticker} debate {date_str}",
                date_str=date_str,
                category="deep-dive",
                segment="deliberation",
                sector=ticker,
            )
        )

    memo = state.phase_hermes.pm_direction_memo
    if memo is not None:
        payload = memo.model_dump(mode="json") if hasattr(memo, "model_dump") else dict(memo)
        artifacts.append(
            publish_document(
                client=client,
                document_key="pm-direction-memo",
                payload=payload,
                doc_type="PM Direction Memo",
                run_type=run_type,
                title=f"PM Direction {date_str}",
                date_str=date_str,
                category="portfolio",
            )
        )

    return artifacts


def held_tickers(state: AtlasResearchState) -> set[str]:
    """Prior-book holdings + H4 roster entries marked ``held`` (#936)."""
    held = set(holdings_from_prior_book(state.prior_context.prior_book))
    for entry in state.phase_hermes.focus_roster:
        if entry.roster_reason == "held" and entry.ticker:
            held.add(entry.ticker.strip().upper())
    return held


def flat_tickers_from_memo(state: AtlasResearchState) -> set[str]:
    memo = state.phase_hermes.pm_direction_memo
    if memo is None:
        return set()
    roster = memo.roster if hasattr(memo, "roster") else memo.get("roster", [])
    flats: set[str] = set()
    for entry in roster:
        direction = entry.direction if hasattr(entry, "direction") else entry.get("direction")
        ticker = entry.ticker if hasattr(entry, "ticker") else entry.get("ticker")
        if direction == "flat" and isinstance(ticker, str) and ticker:
            flats.add(ticker.strip().upper())
    return flats


def gated_out_tickers(state: AtlasResearchState) -> set[str]:
    """HELD names deliberately not dispatched to H5 (Stage 1b staleness gate, #1030).

    The H4 staleness/delta gate records a quiet, unlinked held name in
    ``focus_roster_excluded`` instead of dispatching an analyst. The position is
    still carried in the book at its prior weight — "we own it and nothing
    material changed" is its decision — so commit-run treats it as an intentional
    carry, not a missing analyst doc.

    Intersected with :func:`held_tickers` so ONLY held carries are exempt: the
    ledger also records non-held below-screen names, and one of those reaching the
    book with a positive weight (a stray name never analyzed) must still fail
    closed — the exemption is a held-carry pass, not a blanket "anything in the
    ledger" pass.
    """
    excluded = {
        e.ticker.strip().upper() for e in state.phase_hermes.focus_roster_excluded if e.ticker
    }
    return excluded & held_tickers(state)


def memo_addressed_tickers(state: AtlasResearchState) -> set[str]:
    """Tickers the H7 PM memo's roster explicitly addressed (``long`` or ``flat``)."""
    memo = state.phase_hermes.pm_direction_memo
    if memo is None:
        return set()
    roster = memo.roster if hasattr(memo, "roster") else memo.get("roster", [])
    addressed: set[str] = set()
    for entry in roster:
        ticker = entry.ticker if hasattr(entry, "ticker") else entry.get("ticker")
        if isinstance(ticker, str) and ticker:
            addressed.add(ticker.strip().upper())
    return addressed


def carried_held_tickers(state: AtlasResearchState) -> set[str]:
    """HELD names carried at drifted weight instead of resized or dropped (#1030, #1649).

    Two deliberate-carry classes share ONE set so H8's carry injection and H9's
    coherence exemption can never diverge into a silent mismatch (the #1030
    principle):

    - **H4-gated** (:func:`gated_out_tickers`): quiet held names never dispatched
      to H5 — "we own it and nothing material changed".
    - **Memo-unaddressed** (#1649): held names the H7 PM memo's roster addresses
      with neither ``long`` nor ``flat``. Memo coverage is LLM discipline — run
      29936849103 (2026-07-22) omitted SEVEN held tickers and froze the commit.
      Owning a position with no explicit PM instruction defaults to "hold at
      drifted weight"; exiting requires an explicit ``flat``. Only applies when a
      memo exists — with no memo at all the legacy sizing path owns the decision.

    Intersected with :func:`held_tickers`: a non-held stray in the book still
    fails closed downstream — this is a held-carry pass, never a blanket one.
    """
    held = held_tickers(state)
    carried = gated_out_tickers(state)
    if state.phase_hermes.pm_direction_memo is not None:
        carried = carried | (held - memo_addressed_tickers(state))
    return carried & held


def coherence_errors(state: AtlasResearchState, weights: dict[str, float]) -> list[str]:
    """Fail-closed checks before terminal write."""
    errors: list[str] = []
    flats = flat_tickers_from_memo(state)
    analysts = set(analyst_payloads(state).keys())
    carried = carried_held_tickers(state)

    for ticker in held_tickers(state):
        if weights.get(ticker, 0.0) <= 0 and ticker not in flats:
            errors.append(f"held ticker {ticker} missing from book and not flat in H7")

    for ticker, weight in weights.items():
        if weight <= 0:
            continue
        # A deliberately-carried held name (#1030 gated, #1649 memo-unaddressed) needs
        # no fresh analyst doc. The exemption only covers held carries; a genuine
        # missing-doc gap (a non-held stray with a positive weight) still fails closed.
        if ticker not in analysts and ticker not in flats and ticker not in carried:
            errors.append(f"open position {ticker} lacks H5 analyst doc and is not flat in H7")

    return errors


class PreTradeRiskMode(StrEnum):
    """Rollout knob for H9 PreTradeRiskReport hash validation (#2754 / WP9.4).

    ``off`` — skip validation and persistence.
    ``shadow`` — validate + persist when present; never block the book (default).
    ``enforce`` — missing/unknown/mismatch rejects the commit before booking.
    """

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


@dataclass(frozen=True)
class PreTradeRiskValidation:
    """Outcome of H9 report identity checks — never recomputes metrics."""

    ok: bool
    mode: PreTradeRiskMode
    reason: str | None = None
    report: PreTradeRiskReport | None = None
    report_id: str | None = None


def resolve_pretrade_risk_mode() -> PreTradeRiskMode:
    """Read ``OLYMPUS_PRETRADE_RISK_MODE``; unknown values fall back to shadow."""
    raw = os.environ.get(_PRETRADE_RISK_MODE_ENV, PreTradeRiskMode.SHADOW.value).strip().lower()
    try:
        return PreTradeRiskMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            _PRETRADE_RISK_MODE_ENV,
            raw,
        )
        return PreTradeRiskMode.SHADOW


def validate_pretrade_risk_report(
    state: AtlasResearchState,
    weights: dict[str, float],
    *,
    mode: PreTradeRiskMode | None = None,
) -> PreTradeRiskValidation:
    """Validate attached PreTradeRiskReport identity against the book H9 will commit.

    Checks presence, Pydantic parse (unknown/corrupt), recomputed content hash via
    the contract validator, final-book fingerprint vs ``weights``, optional sized-book
    stamp, and optional allocation-bundle hash. Never calls report builders.
    """
    effective = mode if mode is not None else resolve_pretrade_risk_mode()
    if effective is PreTradeRiskMode.OFF:
        return PreTradeRiskValidation(ok=True, mode=effective, reason="mode_off")

    raw = state.phase_hermes.pre_trade_risk_report
    if raw is None:
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason="missing_pre_trade_risk_report",
        )
    if not isinstance(raw, dict):
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason="unknown_pre_trade_risk_report",
        )

    try:
        report = PreTradeRiskReport.model_validate(raw)
    except Exception as exc:
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason=f"unknown_pre_trade_risk_report:{type(exc).__name__}",
        )

    book_fp = weights_fingerprint(weights)
    if report.final_book_weights_fingerprint != book_fp:
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason="final_book_weights_fingerprint_mismatch",
            report=report,
        )

    book = state.phase_hermes.sized_book or {}
    stamped = book.get("pre_trade_risk_report_hash")
    if stamped is not None and str(stamped) != report.report_content_hash:
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason="pre_trade_risk_report_hash_mismatch",
            report=report,
        )

    bundle_raw = state.phase_hermes.allocation_input_bundle
    if isinstance(bundle_raw, dict):
        bundle_hash = bundle_raw.get("bundle_content_hash")
        if bundle_hash and str(bundle_hash) != report.allocation_input_bundle_hash:
            return PreTradeRiskValidation(
                ok=False,
                mode=effective,
                reason="allocation_input_bundle_hash_mismatch",
                report=report,
            )
    book_bundle = book.get("allocation_input_bundle_hash")
    if book_bundle and str(book_bundle) != report.allocation_input_bundle_hash:
        return PreTradeRiskValidation(
            ok=False,
            mode=effective,
            reason="allocation_input_bundle_hash_mismatch",
            report=report,
        )

    report_id = str(pretrade_risk_report_id(content_hash=report.report_content_hash))
    return PreTradeRiskValidation(
        ok=True,
        mode=effective,
        report=report,
        report_id=report_id,
    )


def persist_validated_pretrade_risk_report(
    *,
    client: SupabaseClient,
    validation: PreTradeRiskValidation,
    source_run_id: str,
    ledger_commit_id: UUID | None = None,
) -> dict[str, Any]:
    """Append-only persist after successful validation. Manifest status fields only."""
    if validation.mode is PreTradeRiskMode.OFF:
        return {
            "pretrade_risk_registry_status": "skipped",
            "pretrade_risk_registry_reason": "mode_off",
            "pretrade_risk_registry_reports_written": 0,
            "pretrade_risk_registry_reports_skipped": 0,
        }
    if not validation.ok or validation.report is None:
        status = "rejected" if validation.mode is PreTradeRiskMode.ENFORCE else "shadow_invalid"
        return {
            "pretrade_risk_registry_status": status,
            "pretrade_risk_registry_reason": validation.reason,
            "pretrade_risk_registry_reports_written": 0,
            "pretrade_risk_registry_reports_skipped": 0,
        }
    try:
        result: PreTradeRiskRegistryWriteResult = persist_pretrade_risk_report(
            client=client,
            report=validation.report,
            source_run_id=source_run_id,
            ledger_commit_id=ledger_commit_id,
        )
    except PreTradeRiskRegistryConflict as exc:
        return {
            "pretrade_risk_registry_status": "conflict",
            "pretrade_risk_registry_reason": str(exc)[:300],
            "pretrade_risk_registry_reports_written": 0,
            "pretrade_risk_registry_reports_skipped": 0,
            "pretrade_risk_registry_conflicts": [str(exc)[:200]],
            "pretrade_risk_report_id": validation.report_id,
            "pretrade_risk_report_hash": validation.report.report_content_hash,
        }
    except Exception as exc:
        logger.warning(
            "h9 pretrade risk registry degraded (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return {
            "pretrade_risk_registry_status": "degraded",
            "pretrade_risk_registry_reason": f"{type(exc).__name__}: {exc}"[:300],
            "pretrade_risk_registry_reports_written": 0,
            "pretrade_risk_registry_reports_skipped": 0,
            "pretrade_risk_report_id": validation.report_id,
            "pretrade_risk_report_hash": validation.report.report_content_hash,
        }
    status = "ok" if result.ok else "degraded"
    return {
        "pretrade_risk_registry_status": status,
        "pretrade_risk_registry_reason": result.degraded_reason,
        "pretrade_risk_registry_reports_written": result.reports_written,
        "pretrade_risk_registry_reports_skipped": result.reports_skipped,
        "pretrade_risk_registry_conflicts": list(result.conflicts),
        "pretrade_risk_report_id": result.report_id or validation.report_id,
        "pretrade_risk_report_hash": result.report_content_hash
        or validation.report.report_content_hash,
    }


def persist_decision_log(*, client: SupabaseClient, state: AtlasResearchState) -> int:
    return persist_pending(client=client, state=state)


__all__ = [
    "BookedPortfolio",
    "PreTradeRiskMode",
    "PreTradeRiskValidation",
    "book_portfolio",
    "carried_held_tickers",
    "coherence_errors",
    "flat_tickers_from_memo",
    "held_tickers",
    "load_commit_manifests",
    "manifest_commit_seq",
    "OVERLAY_MANIFEST_PREFIX",
    "manifest_document_key",
    "persist_decision_log",
    "persist_validated_pretrade_risk_report",
    "publish_hermes_documents",
    "publish_portfolio_brief",
    "resolve_pretrade_risk_mode",
    "validate_pretrade_risk_report",
    "resolve_prior_commit",
    "save_commit_manifest",
    "weights_fingerprint",
    "weights_from_sized_book",
]
