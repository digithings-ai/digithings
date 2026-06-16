"""Phase 9D — materialize the PM decision into the paper portfolio (#700).

The Hermes PM (Phase 7D) emits ``state.phase7d_rebalance`` — a target book of
``recommended_portfolio`` weights. Previously that died as a document; the
``positions`` / ``nav_history`` tables the dashboard reads never got a row.
This terminal step turns the decision into the actual paper book, daily.

Owner decisions (2026-06-13):
- **Pipeline owns the book** — every non-monthly run auto-materializes.
- **NAV is a base-100 normalized index** (no FX, no notional dollars). Matches
  the ``nav_history`` schema intent (migration 012: "Indexed portfolio value
  (base 100) from simulated path"). No broker, no real money — paper only.

NAV chaining: ``nav(D) = nav(prev) × (1 + Σ wᵢ(prev) · deltaᵢ)`` where ``deltaᵢ``
is the freshest completed single-trading-day return from
:func:`query_price_deltas` (trading-day-aware; CASH delta = 0). The first run
(no prior positions) seeds ``nav = 100``. Because the scheduled run fires
intraday — before today's close lands in ``price_history`` — the index advances
using the most recent *available* close pair, i.e. one trading-day phase lag.
That is the standard, defensible behavior for an EOD-priced paper index.

All writes are idempotent upserts (``positions`` on ``(date, ticker)``,
``nav_history`` on ``date``), so a re-run of the same date is a no-op-equivalent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient, query_price_deltas
from digiquant.olympus.hermes.sector_map import sector_bucket

logger = logging.getLogger(__name__)

# Seed value for the normalized NAV index on the first ever run.
_SEED_NAV = 100.0

# Per-position advisory risk fields (Pillar 2E). Gated OFF by default: the new columns
# (migration 039) and entry_price/entry_date population only land when the flag is on AND
# the migration has been applied to prod — so merging this code never breaks the scheduled
# delta/baseline materialize (which would otherwise upsert columns that don't exist yet).
_RISK_FIELDS_ENV = "OLYMPUS_POSITION_RISK_FIELDS"
_ATR_STOP_MULT = 2.0  # advisory stop at ~2× daily ATR below entry
_ATR_TARGET_MULT = 3.0  # advisory target at ~3× daily ATR above entry (1.5 R:R)
_DEFAULT_HORIZON_DAYS = 21
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0


def _position_risk_fields_enabled() -> bool:
    return os.environ.get(_RISK_FIELDS_ENV, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class MaterializeDeps:
    """Wiring deps for the Phase 9D materialization node (injected client)."""

    client: SupabaseClient


def _coerce_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _is_cash(ticker: Any) -> bool:
    return isinstance(ticker, str) and ticker.strip().upper() == "CASH"


# Map the analyst stance onto a valid `theses.status` (migration 002 CHECK:
# ACTIVE | MONITORING | CHALLENGED | CLOSED | INVALIDATED | PAUSED | NEW).
_THESIS_STATUS_BY_STANCE = {
    "buy": "ACTIVE",
    "hold": "ACTIVE",
    "watch": "MONITORING",
    "sell": "CHALLENGED",
}
_DEFAULT_THESIS_STATUS = "ACTIVE"


def _stance_to_thesis_status(stance: Any) -> str:
    if isinstance(stance, str):
        return _THESIS_STATUS_BY_STANCE.get(stance.strip().lower(), _DEFAULT_THESIS_STATUS)
    return _DEFAULT_THESIS_STATUS


def _clip(text: Any, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _upsert_theses(
    *,
    client: SupabaseClient,
    date_str: str,
    weights: dict[str, float],
    analysts: dict[str, Any],
    debates: dict[str, Any],
) -> int:
    """Materialize one thesis row (+ vehicle) per booked holding (#713).

    The live Atlas→Hermes chain previously never wrote the ``theses`` table (only
    frozen legacy scripts did), so the dashboard's Theses surface stayed empty.
    This derives one thesis per held ticker — keyed ``(date, thesis_id=ticker.lower())``
    to match the ``theses`` unique key — from the per-ticker ``AnalystPayload``
    (thesis text → notes/name, stance → status, debate bear-case / analyst risks
    → invalidation). The vehicle is the holding's own ticker.

    ``thesis_vehicles`` FK-references ``(date, thesis_id)`` on ``theses``, so the
    parent rows are written first; vehicle writes are best-effort enrichment and
    never block the book.
    """
    if not weights:
        return 0
    thesis_rows: list[dict[str, Any]] = []
    vehicle_rows: list[dict[str, Any]] = []
    for ticker in weights:
        analyst = analysts.get(ticker) or {}
        debate = debates.get(ticker) or {}
        short = _clip(analyst.get("thesis"), 60)
        invalidation = _clip(
            debate.get("bear_case") or debate.get("key_tension") or analyst.get("risks"), 400
        )
        thesis_rows.append(
            {
                "date": date_str,
                "thesis_id": ticker.lower(),
                "name": f"{ticker} — {short}" if short else ticker,
                "vehicle": ticker,
                "invalidation": invalidation,
                "status": _stance_to_thesis_status(analyst.get("stance")),
                "notes": _clip(analyst.get("thesis"), 500),
            }
        )
        vehicle_rows.append(
            {
                "date": date_str,
                "thesis_id": ticker.lower(),
                "ticker": ticker,
                "rationale": "primary vehicle from PM allocation",
                "candidate_rank": 1,
            }
        )
    for row in thesis_rows:
        client.table("theses").upsert(row, on_conflict="date,thesis_id").execute()
    for row in vehicle_rows:
        try:
            client.table("thesis_vehicles").upsert(
                row, on_conflict="date,thesis_id,ticker"
            ).execute()
        except Exception as exc:  # noqa: BLE001 — vehicles are enrichment; never block the book
            logger.warning("phase9d: thesis_vehicles upsert failed (%s); continuing", exc)
    return len(thesis_rows)


def _prior_book(client: SupabaseClient, run_date: date) -> list[dict[str, Any]]:
    """Positions rows for the most recent date strictly before ``run_date``.

    Returns the held book coming into ``run_date`` (newest prior date only),
    or ``[]`` on the first ever run.
    """
    # entry_price/entry_date are only needed for the (flag-gated) risk-field carry-forward;
    # keep the SELECT byte-identical to the prior book shape when the flag is off.
    columns = "date, ticker, weight_pct"
    if _position_risk_fields_enabled():
        columns += ", entry_price, entry_date"
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


def _prior_nav(client: SupabaseClient, run_date: date) -> float:
    """Latest ``nav_history.nav`` strictly before ``run_date`` (seed if none)."""
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
    """Chain the prior book's realized return onto the prior NAV index value."""
    prior_nav = _prior_nav(client, run_date)
    held = {
        str(r.get("ticker")): _coerce_float(r.get("weight_pct"))
        for r in prior_book
        if r.get("ticker") and not _is_cash(r.get("ticker"))
    }
    if not held:
        # No held names (first run, prior book all-cash, or positions pruned
        # while nav_history persists) → carry the index forward flat. _prior_nav
        # already returns the 100.0 seed when nav_history is empty, so this also
        # covers the first-ever run without resetting an existing index.
        return round(prior_nav, 6)
    deltas = query_price_deltas(client=client, tickers=tuple(held), run_date=run_date)
    port_return = sum((w / 100.0) * deltas.get(t, 0.0) for t, w in held.items())
    return round(prior_nav * (1.0 + port_return), 6)


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp_conviction(value: float) -> float:
    return max(_CONVICTION_FLOOR, min(_CONVICTION_CAP, value))


def _effective_conviction(analyst: Any, debate: Any) -> float | None:
    """Analyst conviction_score + debate conviction_delta, clamped −5..+5; None when the
    ticker has no fresh analyst payload (don't fabricate a grade for a carried holding)."""
    base = _opt_float((analyst or {}).get("conviction_score"))
    if base is None:
        return None
    delta = _opt_float((debate or {}).get("conviction_delta")) or 0.0
    return round(_clamp_conviction(base + delta), 2)


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

    We only need each ticker's *most recent* value, so the query is bounded to a short
    ``lookback_days`` window — enough to clear weekends/holidays and find the latest daily
    row (``price_history`` / ``price_technicals`` are daily: ≤1 row/ticker/day). The page
    limit is tied to that window (``N × (lookback_days + 1)``) so it can never truncate a
    ticker still inside the window — the "crowding" failure mode this guards against. Fail-
    soft: a read error or missing value yields no entry for that ticker (the caller leaves
    the field unset rather than crashing the book); a partial resolve is logged.
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
    except Exception as exc:  # noqa: BLE001 — risk fields are advisory; never block the book
        logger.warning(
            "phase9d: %s.%s read failed (%s); risk fields degrade", table, value_col, exc
        )
        return {}
    out: dict[str, float] = {}
    for row in getattr(resp, "data", None) or []:
        ticker = row.get("ticker")
        if isinstance(ticker, str) and ticker not in out:
            value = _opt_float(row.get(value_col))
            if value is not None:
                out[ticker] = value
    if len(out) < len(tickers):
        logger.debug(
            "phase9d: %s.%s resolved %d/%d tickers (rest left unset)",
            table,
            value_col,
            len(out),
            len(tickers),
        )
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
    """Add advisory per-position risk fields to the non-CASH ``pos_rows`` IN PLACE (Pillar 2E).

    entry_price/entry_date carry forward from the prior book (or seed at today's close + date
    on a first open); conviction = analyst + debate delta; sector_bucket from sector_map;
    stop_loss_pct / target_pct_gain are ATR-derived (advisory, NOT orders); horizon_days from
    preferences. All best-effort — a missing input just leaves that field unset.
    """
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
        if prev_entry is not None and prev_entry > 0:  # held → carry the original entry
            row["entry_price"] = round(prev_entry, 6)
            row["entry_date"] = prev.get("entry_date") or date_str
        else:  # first open → seed at today's close
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
        if atr is not None and atr > 0:  # ATR% is daily; advisory stop/target as ATR multiples
            row["stop_loss_pct"] = round(-_ATR_STOP_MULT * atr, 4)
            row["target_pct_gain"] = round(_ATR_TARGET_MULT * atr, 4)


def build_materialize_node(deps: MaterializeDeps):
    """Return the Phase 9D node bound to ``deps``."""

    def materialize(state: AtlasResearchState) -> dict[str, Any]:
        # The PM never ran (partial graph / legacy / dry-run) → don't fabricate a
        # book. This is distinct from the PM running and choosing to hold cash.
        if state.phase7d_rebalance is None:
            return {}
        recommended = state.phase7d_rebalance.get("recommended_portfolio") or []

        run_date = state.run_date
        date_str = run_date.isoformat()
        client = deps.client

        # Target book from the PM's recommended weights. Coalesce duplicate
        # tickers (sum their weights — never double-count or upsert the same
        # (date,ticker) twice) and drop non-positive / CASH lines (CASH is the
        # residual, not a recommended holding).
        #
        # An EMPTY result is the PM's deliberate **100% CASH** stance (no
        # conviction this run) — a first-class position, booked as a CASH row
        # below. We do NOT pad the book with a cash-proxy ETF (BIL/SHY): those
        # are real holdings the PM picks on conviction, not a substitute for cash.
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

        # A malformed book summing > 100% is scaled proportionally to fully
        # invested (cash 0) rather than silently clamping the residual to an
        # inconsistent state.
        gross = sum(weights.values())
        if gross > 100.0:
            scale = 100.0 / gross
            weights = {t: w * scale for t, w in weights.items()}
            gross = 100.0
        invested = round(gross, 4)
        cash_pct = max(0.0, round(100.0 - invested, 4))
        pos_rows: list[dict[str, Any]] = [
            {"date": date_str, "ticker": t, "weight_pct": round(w, 4)} for t, w in weights.items()
        ]

        # NAV index: mark the prior book BEFORE overwriting with today's, then
        # record this run's NAV point and book. Reads come from prior dates, so
        # ordering between the nav and positions writes is immaterial.
        prior_book = _prior_book(client, run_date)
        nav = _compute_nav(client, run_date, prior_book)

        # Advisory per-position risk fields (Pillar 2E) — flag-gated so the migration-039
        # columns are only written once applied to prod; off → exact prior book shape.
        # Fail-soft: enrichment is advisory, so a config/read error here must never block the
        # book — log and book the plain weights.
        if _position_risk_fields_enabled():
            try:
                _enrich_positions(
                    client=client,
                    run_date=run_date,
                    date_str=date_str,
                    pos_rows=pos_rows,
                    prior_book=prior_book,
                    analysts=dict(state.phase7c_analysts),
                    debates=dict(state.phase7cd_debates),
                    preferences=dict(state.config.preferences),
                )
            except Exception as exc:  # noqa: BLE001 — advisory fields must never block the book
                logger.warning(
                    "phase9d: position risk-field enrichment failed (%s); booking plain weights",
                    exc,
                    exc_info=True,
                )
                # Strip any partial enrichment so the upsert stays schema-safe.
                pos_rows = [
                    {"date": date_str, "ticker": r["ticker"], "weight_pct": r["weight_pct"]}
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
                {"date": date_str, "ticker": "CASH", "weight_pct": cash_pct, "category": "cash"}
            )
        for row in pos_rows:
            client.table("positions").upsert(row, on_conflict="date,ticker").execute()

        # Theses surface (#713): one thesis per held ticker, from the analyst
        # payloads + debate summaries already in state. Skips the CASH ledger row
        # (not in ``weights``); a held ticker with no analyst payload still gets a
        # thesis (status defaults to ACTIVE). Writes nothing for a pure-cash book.
        n_theses = _upsert_theses(
            client=client,
            date_str=date_str,
            weights=weights,
            analysts=dict(state.phase7c_analysts),
            debates=dict(state.phase7cd_debates),
        )

        logger.info(
            "phase9d: booked %d positions (cash %.2f%%), nav=%.4f, %d theses for %s",
            len(pos_rows),
            cash_pct,
            nav,
            n_theses,
            date_str,
        )
        return {}

    return materialize


def build_materialize_phase(deps: MaterializeDeps) -> PipelinePhase:
    """Wrap the materialization node into a single-node ``PipelinePhase``."""
    return PipelinePhase(
        name="materialize",
        nodes=[NodeSpec(name="materialize-portfolio", run=build_materialize_node(deps))],
    )


__all__ = [
    "MaterializeDeps",
    "build_materialize_node",
    "build_materialize_phase",
]
