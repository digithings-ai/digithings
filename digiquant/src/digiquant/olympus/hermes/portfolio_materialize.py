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
from dataclasses import dataclass
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient, query_price_deltas

logger = logging.getLogger(__name__)

# Seed value for the normalized NAV index on the first ever run.
_SEED_NAV = 100.0


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


def _prior_book(client: SupabaseClient, run_date: date) -> list[dict[str, Any]]:
    """Positions rows for the most recent date strictly before ``run_date``.

    Returns the held book coming into ``run_date`` (newest prior date only),
    or ``[]`` on the first ever run.
    """
    resp = (
        client.table("positions")
        .select("date, ticker, weight_pct")
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
        # First run, or prior book was all cash → index unchanged.
        return round(prior_nav, 6) if prior_book else _SEED_NAV
    deltas = query_price_deltas(client=client, tickers=tuple(held), run_date=run_date)
    port_return = sum((w / 100.0) * deltas.get(t, 0.0) for t, w in held.items())
    return round(prior_nav * (1.0 + port_return), 6)


def build_materialize_node(deps: MaterializeDeps):
    """Return the Phase 9D node bound to ``deps``."""

    def materialize(state: AtlasResearchState) -> dict[str, Any]:
        rebalance = state.phase7d_rebalance or {}
        recommended = rebalance.get("recommended_portfolio") or []
        if not recommended:
            return {}  # no PM decision this run → nothing to materialize

        run_date = state.run_date
        date_str = run_date.isoformat()
        client = deps.client

        # Target book from the PM's recommended weights.
        invested = 0.0
        pos_rows: list[dict[str, Any]] = []
        for row in recommended:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            if not isinstance(ticker, str) or not ticker or _is_cash(ticker):
                continue
            weight = _coerce_float(row.get("target_pct"))
            if weight <= 0:
                continue
            invested += weight
            pos_rows.append({"date": date_str, "ticker": ticker, "weight_pct": round(weight, 4)})
        if not pos_rows:
            return {}  # decision held only cash / zero weights — nothing to book

        cash_pct = max(0.0, round(100.0 - invested, 4))

        # NAV index: mark the prior book BEFORE overwriting with today's, then
        # record this run's NAV point and book. Reads come from prior dates, so
        # ordering between the nav and positions writes is immaterial.
        nav = _compute_nav(client, run_date, _prior_book(client, run_date))

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

        logger.info(
            "phase9d: booked %d positions (cash %.2f%%), nav=%.4f for %s",
            len(pos_rows),
            cash_pct,
            nav,
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
