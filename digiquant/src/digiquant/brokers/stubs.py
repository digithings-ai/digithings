"""Broker adapters: not implemented; raise NotImplementedError for connect/submit."""

from __future__ import annotations


class IBAdapterStub:
    """Interactive Brokers native adapter stub."""

    name = "ib"

    def connect(self) -> None:
        raise NotImplementedError("IB adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("IB adapter not implemented.")

    def submit_order(
        self, symbol: str, side: str, quantity: float, order_type: str = "market"
    ) -> str:
        raise NotImplementedError("IB adapter not implemented.")


class AlpacaAdapterStub:
    """Alpaca adapter stub."""

    name = "alpaca"

    def connect(self) -> None:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("Alpaca adapter not implemented.")

    def submit_order(
        self, symbol: str, side: str, quantity: float, order_type: str = "market"
    ) -> str:
        raise NotImplementedError("Alpaca adapter not implemented.")


class QuantConnectAdapterStub:
    """QuantConnect adapter stub."""

    name = "quantconnect"

    def connect(self) -> None:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("QuantConnect adapter not implemented.")

    def submit_order(
        self, symbol: str, side: str, quantity: float, order_type: str = "market"
    ) -> str:
        raise NotImplementedError("QuantConnect adapter not implemented.")
