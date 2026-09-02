"""Kairos order-intent router + broker mirror sync (K4).

Routes approved Hermes order intents to the configured venue after H9 /
``execute_at_open``, and mirrors external acks / fills / positions append-only
(D10: broker is authoritative for external venues). The internal
``paper_internal`` path stays byte-for-byte unchanged.
"""

from __future__ import annotations

from digiquant.execution.policy import (
    AmbiguousVenueError,
    ForeignWorkspaceIntentError,
    InconsistentOrderChainError,
    is_house_or_system_workspace,
    resolve_venue,
    routing_enabled,
)
from digiquant.execution.router import (
    RouteResult,
    broker_order_id,
    broker_order_status_id,
    route_pending_orders,
)
from digiquant.execution.sync import (
    SyncCursor,
    SyncResult,
    broker_execution_id,
    broker_snapshot_id,
    run_sync_batch,
    sync_connection,
)

__all__ = [
    "AmbiguousVenueError",
    "ForeignWorkspaceIntentError",
    "InconsistentOrderChainError",
    "RouteResult",
    "SyncCursor",
    "SyncResult",
    "broker_execution_id",
    "broker_order_id",
    "broker_order_status_id",
    "broker_snapshot_id",
    "is_house_or_system_workspace",
    "route_pending_orders",
    "routing_enabled",
    "resolve_venue",
    "run_sync_batch",
    "sync_connection",
]
