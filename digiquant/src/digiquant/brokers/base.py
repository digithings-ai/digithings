"""Broker adapter protocol. Phase 2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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

    def submit_order(self, symbol: str, side: str, quantity: float, order_type: str = "market") -> str:
        """Submit order; returns order_id. Stub raises NotImplementedError."""
        ...
