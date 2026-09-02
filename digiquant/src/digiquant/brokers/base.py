"""Broker adapter protocol. Phase 2.

Kairos execution contracts (K0) widen this protocol so a real adapter (a later work
package) has a complete surface to implement: account/position reads, the full order
lifecycle (submit/get/cancel), and fill polling — not just `connect`/`disconnect` and a
positional `submit_order`. The legacy positional `submit_order(symbol, side, quantity,
order_type)` signature is deliberately not part of this protocol; every adapter,
including the stubs in `stubs.py`, implements `submit_order(req: BrokerOrderRequest)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerPosition,
)


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol for broker adapters (IB, Alpaca, QuantConnect)."""

    @property
    def name(self) -> str:
        """Broker name."""
        ...

    def connect(self) -> None:
        """Connect to broker. Stub raises NotImplementedError."""
        ...

    def disconnect(self) -> None:
        """Disconnect. Stub raises NotImplementedError."""
        ...

    def get_account(self) -> BrokerAccountSnapshot:
        """Fetch the current account snapshot (equity/cash/buying power)."""
        ...

    def get_positions(self) -> list[BrokerPosition]:
        """Fetch current open positions."""
        ...

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        """Submit an order; returns the broker's acknowledgement."""
        ...

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        """Fetch the current status of a previously submitted order."""
        ...

    def cancel_order(self, external_order_id: str) -> None:
        """Cancel a previously submitted order."""
        ...

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        """List fills recorded since `since` (a UTC-aware datetime)."""
        ...
