"""Unit tests for DigiQuant broker stubs."""

from __future__ import annotations

import pytest

from digiquant.brokers import AlpacaAdapterStub, IBAdapterStub, QuantConnectAdapterStub


@pytest.mark.unit
class TestBrokerStubs:
    """Broker stubs raise NotImplementedError for connect/submit."""

    def test_ib_stub_connect_raises(self) -> None:
        stub = IBAdapterStub()
        assert stub.name == "ib"
        with pytest.raises(NotImplementedError):
            stub.connect()

    def test_ib_stub_submit_order_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            IBAdapterStub().submit_order("AAPL", "buy", 10.0)

    def test_alpaca_stub_connect_raises(self) -> None:
        assert AlpacaAdapterStub().name == "alpaca"
        with pytest.raises(NotImplementedError):
            AlpacaAdapterStub().connect()

    def test_quantconnect_stub_submit_raises(self) -> None:
        assert QuantConnectAdapterStub().name == "quantconnect"
        with pytest.raises(NotImplementedError):
            QuantConnectAdapterStub().submit_order("ETH", "sell", 1.0)
