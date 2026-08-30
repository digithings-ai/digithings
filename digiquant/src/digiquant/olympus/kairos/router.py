"""Order-intent router: submit approved intents to an external venue (K4).

Builds a :class:`~digiquant.brokers.contracts.BrokerOrderRequest` from a pending
Hermes :class:`~digiquant.olympus.hermes.models.portfolio_ledger.OrderIntent`,
submits via a :class:`~digiquant.brokers.base.BrokerAdapter`, and appends one
``broker_orders`` row with a deterministic id. Retries collide on the primary
key — never duplicate.

Direction comes from ``DecisionIntent.action`` via the same
:func:`~digiquant.olympus.hermes.writers.execution_io._directions_by_order`
walk the paper executor uses. The positions book is never consulted for side.

``upsert`` must not appear in this module (append-only mirror, same rule as
:mod:`digiquant.olympus.hermes.writers.execution_io`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous Supabase row dicts
)
from uuid import UUID, uuid5

from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.connections import Broker, BrokerConnection, ConnectionEnv
from digiquant.brokers.contracts import (
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    ExecutionVenue,
    LiveVenueNotAuthorizedError,
    OrderSide,
    OrderType,
    TimeInForce,
)
from digiquant.olympus.hermes.models.portfolio_ledger import DecisionAction
from digiquant.olympus.hermes.writers.execution_io import (
    _directions_by_order,
    _pending_order_heads,
)
from digiquant.olympus.hermes.writers.ledger_io import _insert
from digiquant.olympus.kairos.policy import (
    ForeignWorkspaceIntentError,
    InconsistentOrderChainError,
    resolve_venue,
)

logger = logging.getLogger(__name__)

BROKER_ORDERS = "broker_orders"

# Same sell set as execution_io._SELL_ACTIONS — redeclared so this module does not
# depend on a private name, while staying bit-identical in meaning.
_SELL_ACTIONS = frozenset({DecisionAction.TRIM, DecisionAction.EXIT})

# Separate namespace per id family (mirrors execution_io). Spec §3:
# uuid5(order_intent_id, broker, submitted_date) — payload is the joined string.
_BROKER_ORDER_ID_NAMESPACE = UUID("a1e8c4f2-7b3d-5e90-9c12-6f4a8d0b2e57")

_VENUE_TO_BROKER: dict[ExecutionVenue, Broker] = {
    ExecutionVenue.ALPACA_PAPER: Broker.ALPACA,
    ExecutionVenue.IBKR_PAPER: Broker.IBKR,
}


def broker_order_id(
    order_intent_id: UUID,
    broker: Broker | str,
    submitted_date: date,
) -> UUID:
    """Deterministic id for the initial ``broker_orders`` submit row.

    Spec §3: ``uuid5(order_intent_id, broker, submitted_date)``. A retry after a
    crash recomputes the same id and collides on the primary key — never
    duplicates.
    """
    broker_value = broker.value if isinstance(broker, Broker) else str(broker)
    return uuid5(
        _BROKER_ORDER_ID_NAMESPACE,
        f"{order_intent_id}:{broker_value}:{submitted_date.isoformat()}",
    )


def broker_order_status_id(
    prior_id: UUID,
    status: BrokerOrderStatus | str,
    recorded_at: datetime,
) -> UUID:
    """Deterministic id for a status-supersession ``broker_orders`` row.

    Distinct payload from :func:`broker_order_id` so a status change never
    aliases the submit row. The sync job uses this when the venue reports a
    new lifecycle state.
    """
    status_value = status.value if isinstance(status, BrokerOrderStatus) else str(status)
    return uuid5(
        _BROKER_ORDER_ID_NAMESPACE,
        f"status:{prior_id}:{status_value}:{recorded_at.isoformat()}",
    )


def side_from_action(action: DecisionAction) -> OrderSide:
    """Map a ledger ``DecisionAction`` to an order side.

    ``TRIM`` / ``EXIT`` → sell; ``ADD`` → buy. ``NO_OP`` / ``REJECT`` raise
    :class:`InconsistentOrderChainError` — they imply no order, so a pending
    intent under either is a broken chain (same refusal as ``execution_io``).
    """
    if action in _SELL_ACTIONS:
        return OrderSide.SELL
    if action is DecisionAction.ADD:
        return OrderSide.BUY
    raise InconsistentOrderChainError(
        f"pending order intent chained to DecisionAction.{action.value}; "
        "NO_OP/REJECT imply no order — refusing to invent a side"
    )


@dataclass(frozen=True)
class RoutedOrder:
    """One successfully submitted (or already-mirrored) external order."""

    order_intent_id: UUID
    broker_order_row_id: UUID
    external_order_id: str | None
    side: OrderSide
    symbol: str
    already_mirrored: bool = False


@dataclass
class RouteResult:
    """Outcome of :func:`route_pending_orders` for one run_date."""

    venue: ExecutionVenue
    routed: list[RoutedOrder] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)
    skipped_paper_internal: bool = False


def _pending_quantity(raw: Any) -> Decimal:
    value = Decimal(str(raw))
    if value <= 0:
        raise ValueError(f"order intent quantity must be > 0, got {value}")
    return value


def _request_from_intent(
    *,
    order_intent_id: UUID,
    symbol: str,
    quantity: Decimal,
    side: OrderSide,
) -> BrokerOrderRequest:
    """Build a market DAY request; ``client_order_id = str(order_intent_id)``."""
    return BrokerOrderRequest(
        client_order_id=str(order_intent_id),
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )


def _order_row(
    *,
    row_id: UUID,
    workspace_id: UUID,
    connection_id: UUID,
    order_intent_id: UUID,
    request: BrokerOrderRequest,
    ack: BrokerOrderAck | None,
    status: BrokerOrderStatus,
    submitted_at: datetime,
    recorded_at: datetime,
    supersedes_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": str(row_id),
        "workspace_id": str(workspace_id),
        "connection_id": str(connection_id),
        "order_intent_id": str(order_intent_id),
        "client_order_id": request.client_order_id,
        "external_order_id": None if ack is None else ack.external_order_id,
        "symbol": request.symbol,
        "side": request.side.value,
        "quantity": str(request.quantity) if request.quantity is not None else None,
        "notional": str(request.notional) if request.notional is not None else None,
        "order_type": request.order_type.value,
        "time_in_force": request.time_in_force.value,
        "status": status.value,
        "supersedes_id": None if supersedes_id is None else str(supersedes_id),
        "raw_payload_sha256": None if ack is None else ack.raw_sha256,
        "submitted_at": submitted_at.isoformat(),
        "recorded_at": recorded_at.isoformat(),
    }


def _existing_broker_order_ids(
    *,
    client: Any,
    order_intent_ids: list[str],
) -> set[str]:
    if not order_intent_ids:
        return set()
    resp = (
        client.table(BROKER_ORDERS)
        .select("id, order_intent_id, supersedes_id")
        .in_("order_intent_id", order_intent_ids)
        .execute()
    )
    return {str(row["id"]) for row in (resp.data or []) if row.get("id")}


def _scope_ledger_rows_to_workspace(
    *,
    pending: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    workspace_id: UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep only ``workspace_id`` rows; raise on missing id among candidates.

    Ledger helpers (``_pending_order_heads`` / ``_directions_by_order``) call
    ``_rows_for_date``. T4 made omitted ``workspace_id`` mean the house, never
    every row; this post-filter is the router's authority boundary on that
    house-visible set. Foreign-workspace intents are never consumed; a pending
    row with a null ``workspace_id`` is a disagreement and raises rather than
    being skipped silently. Overlay tenant visibility requires threading
    ``workspace_id`` into the helpers (next hop).
    """
    expected = str(workspace_id)
    for row in pending:
        wid = row.get("workspace_id")
        if wid is None or str(wid).strip() == "":
            raise ForeignWorkspaceIntentError(
                f"pending order intent id={row.get('id')!r} has no workspace_id; "
                f"refusing to route for connection workspace {expected}"
            )
    own_pending = [row for row in pending if str(row.get("workspace_id")) == expected]
    own_orders = [row for row in order_rows if str(row.get("workspace_id") or "") == expected]
    foreign = len(pending) - len(own_pending)
    if foreign:
        logger.warning(
            "kairos router scoped out %d foreign-workspace pending intent(s); "
            "connection workspace_id=%s",
            foreign,
            expected,
        )
    # Defense in depth: every row we will consume must match.
    for row in own_pending:
        if str(row.get("workspace_id")) != expected:
            raise ForeignWorkspaceIntentError(
                f"pending order intent id={row.get('id')!r} workspace_id="
                f"{row.get('workspace_id')!r} does not match connection "
                f"workspace {expected}"
            )
    return own_pending, own_orders


def route_pending_orders(
    *,
    client: Any,
    adapter: BrokerAdapter,
    connection: BrokerConnection,
    run_date: date,
    submitted_date: date,
    now: datetime,
    workspace_id: UUID | None = None,
    active_paper_brokers: list[Broker | str | ExecutionVenue] | None = None,
) -> RouteResult:
    """Route pending ledger order intents to ``connection``'s venue.

    Authority boundary
    ------------------
    * ``workspace_id`` is passed to :func:`resolve_venue` **unchanged** —
      ``None`` / house / system ⇒ ``PAPER_INTERNAL``; never substituted with
      ``connection.workspace_id``.
    * ``connection.env`` must be ``paper`` before any ``submit_order``; live
      raises :class:`LiveVenueNotAuthorizedError`.
    * Pending intents are scoped to ``connection.workspace_id`` after the
      omitted-workspace (house) ledger read; foreign-workspace intents are
      never submitted. Overlay tenant visibility is the next-hop threading
      of ``workspace_id`` into ``_pending_order_heads``.

    When :func:`resolve_venue` returns ``PAPER_INTERNAL``, this function returns
    immediately with ``skipped_paper_internal=True`` and writes nothing — the
    caller keeps the existing ``execution_io`` path.
    """
    if connection.env is not ConnectionEnv.PAPER:
        raise LiveVenueNotAuthorizedError(
            f"route_pending_orders refused connection env={connection.env.value!r}; "
            "only paper connections may reach submit_order"
        )

    # Pass the caller's workspace_id through unchanged (None stays None).
    brokers = active_paper_brokers
    if brokers is None:
        brokers = [connection.broker]
    venue = resolve_venue(workspace_id, active_paper_brokers=brokers)
    if venue is ExecutionVenue.PAPER_INTERNAL:
        return RouteResult(venue=venue, skipped_paper_internal=True)

    expected_broker = _VENUE_TO_BROKER.get(venue)
    if expected_broker is not None and connection.broker is not expected_broker:
        raise ValueError(
            f"connection broker {connection.broker.value!r} does not match "
            f"resolved venue {venue.value!r}"
        )
    if connection.workspace_id != workspace_id:
        # External routing requires an explicit tenant workspace that matches
        # the connection — a mismatched pair is a caller bug, not a silent remap.
        raise ForeignWorkspaceIntentError(
            f"route_pending_orders workspace_id={workspace_id!r} does not match "
            f"connection.workspace_id={connection.workspace_id!r}"
        )

    pending, order_rows = _pending_order_heads(client=client, run_date=run_date)
    pending, order_rows = _scope_ledger_rows_to_workspace(
        pending=pending,
        order_rows=order_rows,
        workspace_id=connection.workspace_id,
    )
    actions, stale = _directions_by_order(client=client, run_date=run_date, order_rows=order_rows)

    intent_ids = [str(row["id"]) for row in pending if row.get("id")]
    existing_ids = _existing_broker_order_ids(client=client, order_intent_ids=intent_ids)

    result = RouteResult(venue=venue)
    for row in pending:
        raw_id = row.get("id")
        symbol = str(row.get("symbol") or "").upper()
        if not raw_id or not symbol:
            continue
        order_intent_id = UUID(str(raw_id))
        order_key = str(order_intent_id)

        if order_key in stale:
            result.refused.append((order_key, "stale_approved_target"))
            continue

        action = actions.get(order_key)
        if action is None:
            result.refused.append((order_key, "missing_decision_action"))
            continue

        try:
            side = side_from_action(action)
            quantity = _pending_quantity(row.get("quantity"))
        except (InconsistentOrderChainError, ValueError) as exc:
            result.refused.append((order_key, str(exc)))
            logger.warning(
                "kairos router refused order_intent_id=%s: %s",
                order_key,
                exc,
            )
            continue

        row_id = broker_order_id(order_intent_id, connection.broker, submitted_date)
        if str(row_id) in existing_ids:
            result.routed.append(
                RoutedOrder(
                    order_intent_id=order_intent_id,
                    broker_order_row_id=row_id,
                    external_order_id=None,
                    side=side,
                    symbol=symbol,
                    already_mirrored=True,
                )
            )
            continue

        request = _request_from_intent(
            order_intent_id=order_intent_id,
            symbol=symbol,
            quantity=quantity,
            side=side,
        )
        ack = adapter.submit_order(request)
        payload = _order_row(
            row_id=row_id,
            workspace_id=connection.workspace_id,
            connection_id=connection.id,
            order_intent_id=order_intent_id,
            request=request,
            ack=ack,
            status=ack.status,
            submitted_at=ack.submitted_at,
            recorded_at=now,
        )
        _insert(client=client, table=BROKER_ORDERS, rows=[payload])
        result.routed.append(
            RoutedOrder(
                order_intent_id=order_intent_id,
                broker_order_row_id=row_id,
                external_order_id=ack.external_order_id,
                side=side,
                symbol=symbol,
            )
        )

    return result


__all__ = [
    "BROKER_ORDERS",
    "ForeignWorkspaceIntentError",
    "RouteResult",
    "RoutedOrder",
    "broker_order_id",
    "broker_order_status_id",
    "route_pending_orders",
    "side_from_action",
]
