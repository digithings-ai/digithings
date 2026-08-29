"""Broker adapters: not implemented; raise NotImplementedError for every method.

Migrated to the widened Kairos `BrokerAdapter` protocol (K0) — each stub implements the
full surface (`get_account`, `get_positions`, `submit_order(req)`, `get_order`,
`cancel_order`, `list_fills`) so `isinstance(<stub>(), BrokerAdapter)` holds, even though
every method still raises `NotImplementedError`. No I/O happens anywhere in this module.
"""

from __future__ import annotations

from datetime import datetime

from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerPosition,
)


class IBAdapterStub:
    """Interactive Brokers native adapter stub."""

    name = "ib"

    def connect(self) -> None:
        raise NotImplementedError("IB adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("IB adapter not implemented.")

    def get_account(self) -> BrokerAccountSnapshot:
        raise NotImplementedError("IB adapter not implemented.")

    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("IB adapter not implemented.")

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        raise NotImplementedError("IB adapter not implemented.")

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        raise NotImplementedError("IB adapter not implemented.")

    def cancel_order(self, external_order_id: str) -> None:
        raise NotImplementedError("IB adapter not implemented.")

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        raise NotImplementedError("IB adapter not implemented.")


class AlpacaAdapterStub:
    """Alpaca adapter stub."""

    name = "alpaca"

    def connect(self) -> None:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def get_account(self) -> BrokerAccountSnapshot:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def cancel_order(self, external_order_id: str) -> None:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        raise NotImplementedError("Alpaca adapter not implemented.")


class QuantConnectAdapterStub:
    """QuantConnect adapter stub."""

    name = "quantconnect"

    def connect(self) -> None:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def get_account(self) -> BrokerAccountSnapshot:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def cancel_order(self, external_order_id: str) -> None:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        raise NotImplementedError("QuantConnect adapter not implemented.")
