"""#2589 — one labeled ``legacy_opening_snapshot`` for portfolio-ledger cutover.

Empty ``portfolio_ledger_holding_lots`` with a non-empty legacy ``positions`` book is the
cold-start hazard: residuals read as zero, so the first sell of a held name books EXIT and
the first buy OPEN into append-only rows. This module seeds exactly one opening chain —
commit → decision → requested/approved quantity → executed order → paper fill → open lot —
derived from the committed book + NAV + marks. It does not invent pre-cutover fill history.

Sole-writer rule: this helper is owned by the execution path under ``hermes/writers/`` and
is the only module besides :mod:`execution_io` that may INSERT ``paper_executions`` /
``holding_lots``. All writes go through :func:`ledger_io._insert` (never upsert).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous Supabase row dicts
)
from uuid import UUID, uuid5

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    HoldingLot,
    HoldingLotStatus,
    OrderIntent,
    OrderIntentStatus,
    PaperExecution,
    PortfolioCommit,
    RequestedTarget,
    paper_execution_id,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
    _heads,
    _insert,
    _rows_for_date,
    _symbol,
)
from digiquant.olympus.tenancy import house_workspace_id

logger = logging.getLogger(__name__)

HOLDING_LOTS = "portfolio_ledger_holding_lots"
POLICY_VERSION_ID = "legacy_opening_snapshot"

_QUANTUM = Decimal("0.000001")
_CASH = "CASH"

# Distinct from execution_io's lot namespace so a seed lot id cannot alias a fill lot id.
_SEED_ID_NAMESPACE = UUID("a1b2c3d4-5e6f-4789-a012-3456789abcde")
_LOT_ID_NAMESPACE = UUID("c7e14a92-2f83-5b6d-9a10-4e8c7d2b5f36")

COLD_START_DECLINE = (
    "holding_lots empty while prior positions book is non-empty "
    "(cold start — seed legacy_opening_snapshot before trusting the ledger path; #2589)"
)


def open_lot_id(execution_id: UUID) -> UUID:
    """Same deterministic open-lot id :func:`execution_io.open_lot_id` uses.

    Duplicated here so this module does not import :mod:`execution_io` (and so the
    executor can import us without a cycle).
    """
    return uuid5(_LOT_ID_NAMESPACE, f"open:{execution_id}")


def _seed_id(kind: str, book_date: date, symbol: str = "") -> UUID:
    payload = (
        f"{kind}:{book_date.isoformat()}:{symbol}" if symbol else f"{kind}:{book_date.isoformat()}"
    )
    return uuid5(_SEED_ID_NAMESPACE, payload)


def _decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


def _shares(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _id_of(row: dict[str, Any] | None) -> UUID | None:
    if not row or not row.get("id"):
        return None
    return UUID(str(row["id"]))


def _open_lots_exist(*, client: SupabaseClient) -> bool:
    lots = (
        client.table(HOLDING_LOTS)
        .select("id")
        .eq("status", HoldingLotStatus.OPEN)
        .limit(1)
        .execute()
    )
    return bool(getattr(lots, "data", None))


def _held_positions(*, client: SupabaseClient, book_date: date) -> list[dict[str, Any]]:
    """House ``positions`` for ``book_date``. Overlay rows on the same date are ignored."""
    book = (
        client.table("positions")
        .select("ticker,weight_pct,entry_price")
        .eq("workspace_id", str(house_workspace_id()))
        .eq("date", book_date.isoformat())
        .execute()
    )
    held: list[dict[str, Any]] = []
    for row in getattr(book, "data", None) or []:
        if not isinstance(row, dict):
            continue
        ticker = _symbol(row.get("ticker"))
        if not ticker or ticker == _CASH:
            continue
        weight = _decimal(row.get("weight_pct")) or Decimal(0)
        if weight <= 0:
            continue
        held.append(row)
    return held


def cold_start_requires_seed(*, client: SupabaseClient, book_date: date | None) -> bool:
    """True when open lots are empty and the prior ``positions`` book has holdings."""
    if book_date is None:
        return False
    if _open_lots_exist(client=client):
        return False
    return bool(_held_positions(client=client, book_date=book_date))


def _nav_for_date(*, client: SupabaseClient, book_date: date) -> Decimal | None:
    """House ``nav_history.nav`` for ``book_date``. Overlay NAV cannot size house lots."""
    resp = (
        client.table("nav_history")
        .select("nav")
        .eq("workspace_id", str(house_workspace_id()))
        .eq("date", book_date.isoformat())
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    nav = _decimal(rows[0].get("nav"))
    if nav is None or nav <= 0:
        return None
    return nav


def _price_for_symbol(
    *,
    client: SupabaseClient,
    symbol: str,
    book_date: date,
    entry_price: Any,
) -> Decimal | None:
    entry = _decimal(entry_price)
    if entry is not None and entry > 0:
        return entry
    resp = (
        client.table("price_history")
        .select("close")
        .eq("ticker", symbol)
        .eq("date", book_date.isoformat())
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    close = _decimal(rows[0].get("close"))
    if close is None or close <= 0:
        return None
    return close


def ensure_legacy_opening_snapshot(
    client: SupabaseClient,
    book_date: date,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Idempotently seed open lots from the legacy ``positions`` book for ``book_date``.

    Returns ``(True, reason)`` when the ledger already has open lots, the book is empty,
    or the snapshot was written. Returns ``(False, reason)`` when NAV or prices needed
    for held names are missing (caller must decline rather than book mislabeled fills).
    """
    if _open_lots_exist(client=client):
        return True, "already seeded"

    held = _held_positions(client=client, book_date=book_date)
    if not held:
        return True, "empty book"

    nav = _nav_for_date(client=client, book_date=book_date)
    if nav is None:
        return False, f"nav_history.nav missing or non-positive for {book_date.isoformat()}"

    stamp = now or datetime.now(UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    effective_at = datetime.combine(book_date, time(0, 0), tzinfo=UTC)

    prior_commits = _rows_for_date(client=client, table=COMMITS, run_date=book_date)
    commit_heads = _heads(prior_commits)
    prior_approved = _rows_for_date(client=client, table=APPROVED_TARGETS, run_date=book_date)
    approved_heads = {
        _symbol(r.get("symbol")): r for r in _heads(prior_approved) if r.get("symbol")
    }
    prior_orders = _rows_for_date(client=client, table=ORDER_INTENTS, run_date=book_date)
    order_heads = {_symbol(r.get("symbol")): r for r in _heads(prior_orders) if r.get("symbol")}

    commit_id = _seed_id("commit", book_date)
    commit = PortfolioCommit(
        id=commit_id,
        run_date=book_date,
        policy_version_id=POLICY_VERSION_ID,
        supersedes_id=_id_of(commit_heads[0] if commit_heads else None),
        effective_at=effective_at,
        recorded_at=stamp,
    )

    intent_rows: list[dict[str, Any]] = []
    requested_rows: list[dict[str, Any]] = []
    approved_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    lot_rows: list[dict[str, Any]] = []
    missing_prices: list[str] = []
    seeded = 0

    for row in sorted(held, key=lambda r: _symbol(r.get("ticker"))):
        symbol = _symbol(row.get("ticker"))
        weight_pct = _decimal(row.get("weight_pct")) or Decimal(0)
        price = _price_for_symbol(
            client=client,
            symbol=symbol,
            book_date=book_date,
            entry_price=row.get("entry_price"),
        )
        if price is None:
            missing_prices.append(symbol)
            continue
        quantity = _shares((weight_pct / Decimal(100)) * nav / price)
        if quantity <= 0:
            continue

        decision_id = _seed_id("decision", book_date, symbol)
        requested_id = _seed_id("requested", book_date, symbol)
        approved_id = _seed_id("approved", book_date, symbol)
        order_id = _seed_id("order", book_date, symbol)
        execution_id = paper_execution_id(order_id, book_date)
        lot_id = open_lot_id(execution_id)

        intent_rows.append(
            DecisionIntent(
                id=decision_id,
                portfolio_commit_id=commit_id,
                run_date=book_date,
                symbol=symbol,
                action=DecisionAction.ADD,
                reason=DecisionReason.NEW_CONVICTION,
                effective_at=effective_at,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        requested_rows.append(
            RequestedTarget(
                id=requested_id,
                decision_intent_id=decision_id,
                run_date=book_date,
                symbol=symbol,
                requested_weight=None,
                requested_quantity=quantity,
                effective_at=effective_at,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        approved_rows.append(
            ApprovedTarget(
                id=approved_id,
                requested_target_id=requested_id,
                run_date=book_date,
                symbol=symbol,
                approved_weight=None,
                approved_quantity=quantity,
                supersedes_id=_id_of(approved_heads.get(symbol)),
                effective_at=effective_at,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        order_rows.append(
            OrderIntent(
                id=order_id,
                approved_target_id=approved_id,
                run_date=book_date,
                symbol=symbol,
                quantity=quantity,
                status=OrderIntentStatus.EXECUTED,
                supersedes_id=_id_of(order_heads.get(symbol)),
                effective_at=effective_at,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        execution_rows.append(
            PaperExecution(
                id=execution_id,
                order_intent_id=order_id,
                executed_date=book_date,
                symbol=symbol,
                quantity=quantity,
                price=price,
                fee=Decimal("0.00"),
                slippage=Decimal("0.00"),
                executed_at=stamp,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        lot_rows.append(
            HoldingLot(
                id=lot_id,
                opened_by_execution_id=execution_id,
                closed_by_execution_id=None,
                run_date=book_date,
                symbol=symbol,
                quantity=quantity,
                open_price=price,
                status=HoldingLotStatus.OPEN,
                opened_at=stamp,
                closed_at=None,
                recorded_at=stamp,
            ).model_dump(mode="json")
        )
        seeded += 1

    if missing_prices:
        return (
            False,
            "missing entry_price/price_history close for "
            + ", ".join(missing_prices)
            + f" on {book_date.isoformat()}",
        )
    if seeded == 0:
        return True, "empty book"

    # FK order: commit → intents → targets → orders → fills → lots.
    _insert(client=client, table=COMMITS, rows=[commit.model_dump(mode="json")])
    _insert(client=client, table=DECISION_INTENTS, rows=intent_rows)
    _insert(client=client, table=REQUESTED_TARGETS, rows=requested_rows)
    _insert(client=client, table=APPROVED_TARGETS, rows=approved_rows)
    _insert(client=client, table=ORDER_INTENTS, rows=order_rows)
    _insert(client=client, table=PAPER_EXECUTIONS, rows=execution_rows)
    _insert(client=client, table=HOLDING_LOTS, rows=lot_rows)

    logger.info(
        "opening_snapshot: seeded %d open lot(s) for %s under %s",
        seeded,
        book_date.isoformat(),
        POLICY_VERSION_ID,
    )
    return True, f"seeded {seeded} open lot(s)"


__all__ = [
    "COLD_START_DECLINE",
    "HOLDING_LOTS",
    "POLICY_VERSION_ID",
    "cold_start_requires_seed",
    "ensure_legacy_opening_snapshot",
    "open_lot_id",
]
