"""H9 terminal I/O — portfolio booking, brief publish, commit manifest (#932)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.decision_log import persist_pending
from digiquant.olympus.atlas.state import AtlasResearchState, PublishedArtifact, RebalancePayload
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_prior_book,
    publish_document,
    query_price_deltas,
)
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.sector_map import sector_bucket

logger = logging.getLogger(__name__)

_SEED_NAV = 100.0
_RISK_FIELDS_ENV = "OLYMPUS_POSITION_RISK_FIELDS"
_ATR_STOP_MULT = 2.0
_ATR_TARGET_MULT = 3.0
_DEFAULT_HORIZON_DAYS = 21
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0
_MANIFEST_DOC_PREFIX = "commit-run/"


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


def _compute_nav(client: SupabaseClient, run_date: date, prior_book: list[dict[str, Any]]) -> float:
    prior_nav = _prior_nav(client, run_date)
    held = {
        str(r.get("ticker")): _coerce_float(r.get("weight_pct"))
        for r in prior_book
        if r.get("ticker") and not _is_cash(r.get("ticker"))
    }
    if not held:
        return round(prior_nav, 6)
    deltas = query_price_deltas(client=client, tickers=tuple(held), run_date=run_date)
    port_return = sum((w / 100.0) * deltas.get(t, 0.0) for t, w in held.items())
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
    except Exception as exc:  # noqa: BLE001 — advisory fields must never block the book
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
    horizon = preferences.get("holding_days")
    horizon_days = (
        int(horizon)
        if isinstance(horizon, (int, float)) and not isinstance(horizon, bool) and horizon > 0
        else _DEFAULT_HORIZON_DAYS
    )

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
    canonical = {k: round(v, 4) for k, v in sorted(weights.items())}
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(frozen=True)
class BookedPortfolio:
    """Result of booking H8 weights into ``positions`` + ``nav_history``."""

    weights: dict[str, float]
    cash_pct: float
    invested_pct: float
    nav: float
    position_rows: list[dict[str, Any]]


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

    pos_rows: list[dict[str, Any]] = [
        {"date": date_str, "ticker": t, "weight_pct": round(w, 4), "thesis_id": t.lower()}
        for t, w in weights.items()
    ]

    prior_book = load_prior_book(
        client, run_date, include_risk_fields=_position_risk_fields_enabled()
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
        except Exception as exc:  # noqa: BLE001 — advisory fields must never block the book
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

    client.table("nav_history").upsert(
        {
            "date": date_str,
            "nav": nav,
            "cash_pct": cash_pct,
            "invested_pct": round(invested, 4),
        },
        on_conflict="date",
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
        client.table("positions").upsert(row, on_conflict="date,ticker").execute()

    return BookedPortfolio(
        weights=weights,
        cash_pct=cash_pct,
        invested_pct=round(invested, 4),
        nav=nav,
        position_rows=pos_rows,
    )


def manifest_document_key(source_run_id: str) -> str:
    return f"{_MANIFEST_DOC_PREFIX}{source_run_id}"


def load_commit_manifest(
    *,
    client: SupabaseClient,
    source_run_id: str,
    run_date: date,
) -> dict[str, Any] | None:
    """Load a prior commit manifest for ``source_run_id`` on ``run_date``."""
    key = manifest_document_key(source_run_id)
    date_str = run_date.isoformat()

    store = getattr(client, "store", None)
    if isinstance(store, dict):
        for row in store.get("documents", []):
            if row.get("date") == date_str and row.get("document_key") == key:
                payload = row.get("payload")
                if isinstance(payload, dict):
                    return dict(payload)

    resp = (
        client.table("documents")
        .select("payload")
        .eq("date", date_str)
        .eq("document_key", key)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    payload = rows[0].get("payload")
    return dict(payload) if isinstance(payload, dict) else None


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
        document_key=manifest_document_key(source_run_id),
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
    """Publish operator brief — weights from H8 ``sized_book`` only."""
    date_str = state.run_date.isoformat()
    return publish_document(
        client=client,
        document_key="pm-rebalance",
        payload=dict(book),
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


def coherence_errors(state: AtlasResearchState, weights: dict[str, float]) -> list[str]:
    """Fail-closed checks before terminal write."""
    errors: list[str] = []
    flats = flat_tickers_from_memo(state)
    analysts = set(analyst_payloads(state).keys())

    for ticker in held_tickers(state):
        if weights.get(ticker, 0.0) <= 0 and ticker not in flats:
            errors.append(f"held ticker {ticker} missing from book and not flat in H7")

    for ticker, weight in weights.items():
        if weight <= 0:
            continue
        if ticker not in analysts and ticker not in flats:
            errors.append(f"open position {ticker} lacks H5 analyst doc and is not flat in H7")

    return errors


def persist_decision_log(*, client: SupabaseClient, state: AtlasResearchState) -> int:
    return persist_pending(client=client, state=state)


__all__ = [
    "BookedPortfolio",
    "book_portfolio",
    "coherence_errors",
    "flat_tickers_from_memo",
    "held_tickers",
    "load_commit_manifest",
    "manifest_document_key",
    "persist_decision_log",
    "publish_hermes_documents",
    "publish_portfolio_brief",
    "save_commit_manifest",
    "weights_fingerprint",
    "weights_from_sized_book",
]
