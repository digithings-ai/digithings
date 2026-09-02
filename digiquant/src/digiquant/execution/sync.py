"""Broker mirror sync: pull acks / fills / positions append-only (K4).

Callable from cron (~5 min during market hours for active connections). v1 is
REST polling only (Alpaca ``TradingStream`` has no OAuth support; IBKR
websocket needs a brokerage session — spec §6/§7).

Budgets (enforced here as call counters; adapters own their own pacing guards):
- Alpaca: ≤6 REST calls per connection per cycle.
- IBKR: ≥5s spacing on paced endpoints — rely on the adapter; this module does
  not sleep around IBKR calls.

Reconciliation: when a broker position snapshot disagrees with the fill-implied
expectation, append the snapshot with ``reconciliation_diverged=true`` plus a
structured report and log — **never** auto-submit corrective orders (D10).

``upsert`` must not appear in this module.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous Supabase row dicts
)
from uuid import UUID, uuid5

from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.connections import Broker, BrokerConnection
from digiquant.brokers.contracts import (
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderStatus,
    BrokerPosition,
    OrderSide,
)
from digiquant.portfolio.writers.ledger_io import _insert
from digiquant.execution.router import (
    BROKER_ORDERS,
    broker_order_status_id,
)

logger = logging.getLogger(__name__)

BROKER_EXECUTIONS = "broker_executions"
BROKER_POSITION_SNAPSHOTS = "broker_position_snapshots"

_SNAPSHOT_ID_NAMESPACE = UUID("d4b9e1a7-3c5f-5a82-8e06-9b7c2f4d1a90")

# Spec §6: Alpaca ≤6 calls/connection/cycle against ~200 req/min account limit.
ALPACA_MAX_CALLS_PER_CYCLE = 6


class SyncBudgetExceeded(RuntimeError):
    """A sync cycle would exceed the per-connection REST call budget."""


@dataclass(frozen=True)
class SyncCursor:
    """High-water mark for fill polling.

    Persistence is the caller's job (cron state / job_runs). This module is
    pure with respect to cursor storage: it accepts a cursor and returns the
    advanced one.
    """

    fills_since: datetime

    def __post_init__(self) -> None:
        offset = self.fills_since.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError("SyncCursor.fills_since must be UTC")


@dataclass
class SyncResult:
    """Outcome of one :func:`sync_connection` cycle."""

    connection_id: UUID
    status_rows_appended: int = 0
    fills_appended: int = 0
    fills_already_present: int = 0
    snapshot_id: UUID | None = None
    reconciliation_diverged: bool = False
    reconciliation_report: dict[str, Any] | None = None
    cursor: SyncCursor | None = None
    calls_used: int = 0
    refused_corrective_orders: bool = True  # invariant: sync never trades
    # Set when at least one venue fill could not be linked to a mirrored order.
    # Cursor is held so the orphan is re-read next cycle (see sync_connection).
    unlinked_fills_held_cursor: bool = False
    unlinked_fill_ids: list[str] = field(default_factory=list)


@dataclass
class _CallBudget:
    """Per-cycle REST call counter for Alpaca; no-op pass-through for IBKR."""

    broker: Broker
    max_calls: int | None
    used: int = 0

    def charge(self, n: int = 1) -> None:
        if self.max_calls is None:
            self.used += n
            return
        if self.used + n > self.max_calls:
            raise SyncBudgetExceeded(
                f"{self.broker.value} sync budget exceeded: "
                f"used={self.used} + {n} > max={self.max_calls}"
            )
        self.used += n


def broker_execution_id(connection_id: UUID, external_fill_id: str) -> UUID:
    """Deterministic fill id: ``uuid5(connection_id, external_fill_id)`` (spec §3)."""
    return uuid5(connection_id, external_fill_id)


def broker_snapshot_id(connection_id: UUID, as_of: datetime) -> UUID:
    """Deterministic snapshot id for ``(connection_id, as_of)``."""
    return uuid5(
        _SNAPSHOT_ID_NAMESPACE,
        f"{connection_id}:{as_of.astimezone(UTC).isoformat()}",
    )


def _budget_for(broker: Broker) -> _CallBudget:
    if broker is Broker.ALPACA:
        return _CallBudget(broker=broker, max_calls=ALPACA_MAX_CALLS_PER_CYCLE)
    # IBKR: pacing is inside the adapter (≥5s on paced endpoints). No cycle cap here.
    return _CallBudget(broker=broker, max_calls=None)


def _heads_by_external_order(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Latest (non-superseded) broker_orders row keyed by ``external_order_id``."""
    superseded = {str(r["supersedes_id"]) for r in rows if r.get("supersedes_id")}
    heads = [r for r in rows if str(r.get("id") or "") not in superseded]
    by_ext: dict[str, dict[str, Any]] = {}
    for row in heads:
        ext = row.get("external_order_id")
        if not ext:
            continue
        by_ext[str(ext)] = row
    return by_ext


def _load_connection_orders(*, client: Any, connection_id: UUID) -> list[dict[str, Any]]:
    resp = client.table(BROKER_ORDERS).select("*").eq("connection_id", str(connection_id)).execute()
    return list(resp.data or [])


def _existing_execution_ids(*, client: Any, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    resp = client.table(BROKER_EXECUTIONS).select("id").in_("id", ids).execute()
    return {str(row["id"]) for row in (resp.data or []) if row.get("id")}


def _fill_implied_positions(
    *,
    order_heads: dict[str, dict[str, Any]],
    fills: list[dict[str, Any]],
) -> dict[str, Decimal]:
    """Net signed quantity per symbol from mirrored fills (buy +, sell −).

    This is the *mirrored expectation* reconciliation compares against the
    broker snapshot. It never reads the mutable ``positions`` book.
    """
    order_by_id = {str(h["id"]): h for h in order_heads.values()}
    # Also index every head by id for fills that reference a superseded chain
    # member via broker_order_id — fills point at the submit/status row id they
    # were booked against.
    net: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for fill in fills:
        order_id = str(fill.get("broker_order_id") or "")
        order = order_by_id.get(order_id)
        if order is None:
            # Fill may reference a non-head (superseded) row; look up side from any row
            # carrying that id is handled by the caller passing all orders if needed.
            continue
        side = str(order.get("side") or "")
        qty = Decimal(str(fill["quantity"]))
        symbol = str(fill["symbol"]).upper()
        if side == OrderSide.SELL.value:
            net[symbol] -= qty
        else:
            net[symbol] += qty
    return {symbol: qty for symbol, qty in net.items() if qty != 0}


def _positions_from_snapshot(positions: list[BrokerPosition]) -> dict[str, Decimal]:
    return {p.symbol.upper(): p.quantity for p in positions if p.quantity != 0}


def _reconcile(
    *,
    expected: dict[str, Decimal],
    actual: dict[str, Decimal],
) -> tuple[bool, dict[str, Any]]:
    symbols = sorted(set(expected) | set(actual))
    divergences: list[dict[str, Any]] = []
    for symbol in symbols:
        exp = expected.get(symbol, Decimal("0"))
        act = actual.get(symbol, Decimal("0"))
        if exp != act:
            divergences.append(
                {
                    "symbol": symbol,
                    "expected_qty": str(exp),
                    "broker_qty": str(act),
                    "delta": str(act - exp),
                }
            )
    report: dict[str, Any] = {
        "diverged": bool(divergences),
        "divergences": divergences,
        "corrective_orders": [],  # D10: never auto-trade
        "note": (
            "broker is authoritative; digithings surfaces the divergence and "
            "never submits corrective orders"
        ),
    }
    return bool(divergences), report


def _append_status_row(
    *,
    client: Any,
    prior: dict[str, Any],
    ack: BrokerOrderAck,
    now: datetime,
) -> bool:
    """Append a superseding status row when the venue status advanced. Returns True if written."""
    prior_status = str(prior.get("status") or "")
    if prior_status == ack.status.value:
        return False
    prior_id = UUID(str(prior["id"]))
    row_id = broker_order_status_id(prior_id, ack.status, now)
    payload = {
        "id": str(row_id),
        "workspace_id": str(prior["workspace_id"]),
        "connection_id": str(prior["connection_id"]),
        "order_intent_id": prior.get("order_intent_id"),
        "client_order_id": prior["client_order_id"],
        "external_order_id": ack.external_order_id,
        "symbol": prior["symbol"],
        "side": prior["side"],
        "quantity": prior.get("quantity"),
        "notional": prior.get("notional"),
        "order_type": prior.get("order_type") or "market",
        "time_in_force": prior.get("time_in_force") or "day",
        "status": ack.status.value,
        "supersedes_id": str(prior_id),
        "raw_payload_sha256": ack.raw_sha256,
        "submitted_at": prior["submitted_at"],
        "recorded_at": now.isoformat(),
    }
    _insert(client=client, table=BROKER_ORDERS, rows=[payload])
    return True


def _append_fill(
    *,
    client: Any,
    connection: BrokerConnection,
    broker_order_id: UUID,
    fill: BrokerFill,
    now: datetime,
    existing_ids: set[str],
) -> bool:
    """Append one fill row. Returns False if the deterministic id already exists."""
    row_id = broker_execution_id(connection.id, fill.external_fill_id)
    if str(row_id) in existing_ids:
        return False
    payload = {
        "id": str(row_id),
        "workspace_id": str(connection.workspace_id),
        "broker_order_id": str(broker_order_id),
        "external_fill_id": fill.external_fill_id,
        "symbol": fill.symbol,
        "quantity": str(fill.quantity),
        "price": str(fill.price),
        "fee": None if fill.fee is None else str(fill.fee),
        "executed_at": fill.executed_at.isoformat(),
        "recorded_at": now.isoformat(),
    }
    _insert(client=client, table=BROKER_EXECUTIONS, rows=[payload])
    existing_ids.add(str(row_id))
    return True


def _load_all_fills_for_orders(*, client: Any, order_ids: list[str]) -> list[dict[str, Any]]:
    if not order_ids:
        return []
    resp = client.table(BROKER_EXECUTIONS).select("*").in_("broker_order_id", order_ids).execute()
    return list(resp.data or [])


def sync_connection(
    *,
    client: Any,
    adapter: BrokerAdapter,
    connection: BrokerConnection,
    cursor: SyncCursor,
    now: datetime | None = None,
    pull_snapshot: bool = True,
) -> SyncResult:
    """Pull order status + fills since ``cursor``; optionally snapshot positions.

    Unsealing credentials is the caller's job (use
    :func:`digiquant.brokers.connections.open_credential`'s lease around
    adapter construction). This function never sees plaintext secrets.

    Alpaca cycles charge every adapter call against
    :data:`ALPACA_MAX_CALLS_PER_CYCLE` and raise :class:`SyncBudgetExceeded`
    before crossing the cap. IBKR relies on the adapter's own ≥5s pacing
    guard — this function does not sleep.
    """
    stamp = now or datetime.now(UTC)
    budget = _budget_for(connection.broker)
    result = SyncResult(connection_id=connection.id, cursor=cursor)

    orders = _load_connection_orders(client=client, connection_id=connection.id)
    heads = _heads_by_external_order(orders)
    # Also map every row id → row so fills can resolve side via broker_order_id.
    orders_by_id = {str(r["id"]): r for r in orders if r.get("id")}

    # --- order status refresh (budget: 1 call per head, Alpaca-capped) ---
    for ext_id, head in list(heads.items()):
        try:
            budget.charge()
        except SyncBudgetExceeded:
            logger.warning(
                "execution sync connection_id=%s stopping status pull: %s",
                connection.id,
                budget.used,
            )
            break
        ack = adapter.get_order(ext_id)
        if _append_status_row(client=client, prior=head, ack=ack, now=stamp):
            result.status_rows_appended += 1
            # Refresh head view for subsequent fill linking.
            new_id = str(broker_order_status_id(UUID(str(head["id"])), ack.status, stamp))
            # Re-read is unnecessary: synthesize the new head for this cycle.
            updated = dict(head)
            updated["id"] = new_id
            updated["status"] = ack.status.value
            updated["external_order_id"] = ack.external_order_id
            updated["supersedes_id"] = str(head["id"])
            updated["raw_payload_sha256"] = ack.raw_sha256
            heads[ext_id] = updated
            orders_by_id[new_id] = updated

    # --- fills since cursor (1 list_fills call) ---
    try:
        budget.charge()
        fills = adapter.list_fills(cursor.fills_since)
    except SyncBudgetExceeded:
        logger.warning(
            "execution sync connection_id=%s skipping fills: budget exhausted used=%s",
            connection.id,
            budget.used,
        )
        fills = []

    fill_ids = [str(broker_execution_id(connection.id, f.external_fill_id)) for f in fills]
    existing = _existing_execution_ids(client=client, ids=fill_ids)

    # Map fill → broker_order via client_order_id / external_order_id / symbol match.
    # Prefer external_order_id when the adapter fill doesn't carry it: fall back to
    # matching symbol against open heads. BrokerFill has no order id field — link by
    # symbol to the unique open head when unambiguous; otherwise skip with a log.
    #
    # Cursor advance: never move fills_since past an unlinked (orphan) fill.
    # Alpaca/IBKR list_fills use an exclusive `after`/`since` bound, so holding
    # AT the orphan's executed_at would drop it forever. When any orphan exists
    # we keep the previous cursor so the next cycle re-reads it. Operator remedy:
    # ensure the submit mirror row exists (same symbol / external_order_id) or
    # resolve symbol ambiguity among open heads; once the fill links, the cursor
    # advances normally.
    advanced_since = cursor.fills_since
    orphan_times: list[datetime] = []
    orphan_ids: list[str] = []
    for fill in fills:
        broker_order_row = _resolve_order_for_fill(
            fill=fill, heads=heads, orders_by_id=orders_by_id
        )
        if broker_order_row is None:
            orphan_times.append(fill.executed_at)
            orphan_ids.append(fill.external_fill_id)
            logger.warning(
                "execution sync connection_id=%s could not link fill %s symbol=%s; "
                "holding fills_since cursor so the orphan is re-read next cycle",
                connection.id,
                fill.external_fill_id,
                fill.symbol,
            )
            continue
        wrote = _append_fill(
            client=client,
            connection=connection,
            broker_order_id=UUID(str(broker_order_row["id"])),
            fill=fill,
            now=stamp,
            existing_ids=existing,
        )
        if wrote:
            result.fills_appended += 1
        else:
            result.fills_already_present += 1
        if fill.executed_at > advanced_since:
            advanced_since = fill.executed_at

    if orphan_times:
        earliest_orphan = min(orphan_times)
        # Do not advance beyond the earliest unlinked fill; exclusive-since
        # safety ⇒ hold at the previous cursor so the orphan remains visible.
        if advanced_since >= earliest_orphan:
            advanced_since = cursor.fills_since
        result.unlinked_fills_held_cursor = True
        result.unlinked_fill_ids = list(orphan_ids)
        logger.warning(
            "execution sync connection_id=%s held fills_since at %s due to %d unlinked "
            "fill(s); remedy: link mirror order rows or resolve symbol ambiguity",
            connection.id,
            advanced_since.isoformat(),
            len(orphan_ids),
        )

    result.cursor = SyncCursor(fills_since=advanced_since)
    result.calls_used = budget.used

    if not pull_snapshot:
        return result

    # --- positions + account snapshot (2 calls) ---
    try:
        budget.charge(2)
    except SyncBudgetExceeded:
        logger.warning(
            "execution sync connection_id=%s skipping snapshot: budget exhausted used=%s",
            connection.id,
            budget.used,
        )
        result.calls_used = budget.used
        return result

    positions = adapter.get_positions()
    account = adapter.get_account()
    as_of = account.as_of

    # Expectation from *all* mirrored fills for this connection's orders.
    all_order_ids = list(orders_by_id.keys())
    mirrored_fills = _load_all_fills_for_orders(client=client, order_ids=all_order_ids)
    # Build a side lookup that includes every order row (heads + superseded).
    side_index = {str(r["id"]): r for r in orders if r.get("id")}
    # Prefer latest head for side when present.
    for head in heads.values():
        side_index[str(head["id"])] = head
    expected = _fill_implied_positions(order_heads=side_index, fills=mirrored_fills)
    actual = _positions_from_snapshot(positions)
    diverged, report = _reconcile(expected=expected, actual=actual)

    if diverged:
        logger.warning(
            "execution sync reconciliation diverged connection_id=%s report=%s",
            connection.id,
            report,
        )

    snap_id = broker_snapshot_id(connection.id, as_of)
    payload = {
        "id": str(snap_id),
        "workspace_id": str(connection.workspace_id),
        "connection_id": str(connection.id),
        "as_of": as_of.isoformat(),
        "positions": [
            {
                "symbol": p.symbol,
                "qty": str(p.quantity),
                "avg_entry": str(p.avg_entry_price),
                "market_value": str(p.market_value),
                "unrealized_pl": str(p.unrealized_pl),
            }
            for p in positions
        ],
        "account": {
            "account_id": account.account_id,
            "equity": str(account.equity),
            "cash": str(account.cash),
            "buying_power": str(account.buying_power),
            "currency": account.currency,
        },
        "reconciliation_diverged": diverged,
        "reconciliation_report": report if diverged else None,
        "recorded_at": stamp.isoformat(),
    }
    # Append-only: collision on (connection_id, as_of) UNIQUE is a retry no-op for the
    # caller to handle; we still attempt insert. Tests use fakes that ignore duplicates.
    try:
        _insert(client=client, table=BROKER_POSITION_SNAPSHOTS, rows=[payload])
    except Exception as exc:
        # Unique violation on retry — treat as already snapshotted.
        if "duplicate" not in str(exc).lower() and "unique" not in str(exc).lower():
            raise
        logger.info(
            "execution sync snapshot already present connection_id=%s as_of=%s",
            connection.id,
            as_of.isoformat(),
        )

    result.snapshot_id = snap_id
    result.reconciliation_diverged = diverged
    result.reconciliation_report = report if diverged else None
    result.calls_used = budget.used
    # Explicit invariant for tests / callers: sync never submits orders.
    result.refused_corrective_orders = True
    return result


def _resolve_order_for_fill(
    *,
    fill: BrokerFill,
    heads: dict[str, dict[str, Any]],
    orders_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Best-effort link from a venue fill to a mirrored broker_orders head.

    ``BrokerFill`` carries no order id (K0 contract). Prefer a unique open head
    on the same symbol; if several match, refuse to guess.
    """
    matches = [
        row for row in heads.values() if str(row.get("symbol") or "").upper() == fill.symbol.upper()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Prefer a non-terminal head when unique among them.
        openish = {
            BrokerOrderStatus.SUBMITTED.value,
            BrokerOrderStatus.ACCEPTED.value,
            BrokerOrderStatus.PARTIALLY_FILLED.value,
            BrokerOrderStatus.FILLED.value,
        }
        open_matches = [m for m in matches if str(m.get("status")) in openish]
        if len(open_matches) == 1:
            return open_matches[0]
        return None
    # No head — fall back to any historical order row for the symbol (manual fills).
    hist = [
        row
        for row in orders_by_id.values()
        if str(row.get("symbol") or "").upper() == fill.symbol.upper()
    ]
    return hist[0] if len(hist) == 1 else None


def run_sync_batch(
    *,
    client: Any,
    cycles: list[tuple[BrokerAdapter, BrokerConnection, SyncCursor]],
    now: datetime | None = None,
    pull_snapshot: bool = True,
) -> list[SyncResult]:
    """Cron batch entry: sync each active connection, then fail-soft execution alerts.

      ``cycles`` is built by the caller (cron runner) from active ``broker_connections``
    rows + credential leases. This function does not load connections itself.
    """
    stamp = now or datetime.now(UTC)
    results: list[SyncResult] = []
    for adapter, connection, cursor in cycles:
        results.append(
            sync_connection(
                client=client,
                adapter=adapter,
                connection=connection,
                cursor=cursor,
                now=stamp,
                pull_snapshot=pull_snapshot,
            )
        )

    # -------------------------------------------------------------------------
    # K5: mid-day execution-alert dispatch — fail-soft; never fails the sync batch.
    # -------------------------------------------------------------------------
    try:
        from digiquant.notify.dispatch import dispatch_execution_alerts

        dispatch_execution_alerts(run_date=stamp.date())
    except Exception:
        logger.warning("execution sync: execution-alert dispatch skipped", exc_info=True)

    return results


__all__ = [
    "ALPACA_MAX_CALLS_PER_CYCLE",
    "BROKER_EXECUTIONS",
    "BROKER_POSITION_SNAPSHOTS",
    "SyncBudgetExceeded",
    "SyncCursor",
    "SyncResult",
    "broker_execution_id",
    "broker_snapshot_id",
    "run_sync_batch",
    "sync_connection",
]
