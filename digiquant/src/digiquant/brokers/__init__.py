# Broker adapters: IB native + Alpaca/QuantConnect stubs. Phase 2.
# Kairos execution contracts (K0): typed venue/order/position models re-exported here
# alongside the protocol and stubs so a caller does not need to import `contracts`
# separately for the common case.
#
# K1: ``AlpacaAdapter`` is exported lazily via ``__getattr__`` so
# ``import digiquant.brokers`` succeeds without the optional ``brokers-alpaca`` extra
# (alpaca-py). Accessing ``AlpacaAdapter`` loads ``brokers.alpaca``, which itself
# guards the SDK import and raises a clear ImportError only on construction if the
# extra is missing.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerAuthError,
    BrokerContractModel,
    BrokerError,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderNotFound,
    BrokerOrderRejected,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerRateLimited,
    BrokerTransportError,
    ExecutionVenue,
    LiveVenueNotAuthorizedError,
    OrderSide,
    OrderType,
    TimeInForce,
)
from digiquant.brokers.stubs import AlpacaAdapterStub, IBAdapterStub, QuantConnectAdapterStub

if TYPE_CHECKING:
    from digiquant.brokers.alpaca import AlpacaAdapter, ApiKeyAuth, OAuthAuth

__all__ = [
    "AlpacaAdapter",
    "AlpacaAdapterStub",
    "ApiKeyAuth",
    "BrokerAccountSnapshot",
    "BrokerAdapter",
    "BrokerAuthError",
    "BrokerContractModel",
    "BrokerError",
    "BrokerFill",
    "BrokerOrderAck",
    "BrokerOrderNotFound",
    "BrokerOrderRejected",
    "BrokerOrderRequest",
    "BrokerOrderStatus",
    "BrokerPosition",
    "BrokerRateLimited",
    "BrokerTransportError",
    "ExecutionVenue",
    "IBAdapterStub",
    "LiveVenueNotAuthorizedError",
    "OAuthAuth",
    "OrderSide",
    "OrderType",
    "QuantConnectAdapterStub",
    "TimeInForce",
]


def __getattr__(name: str) -> Any:
    if name in {"AlpacaAdapter", "ApiKeyAuth", "OAuthAuth"}:
        from digiquant.brokers import alpaca as _alpaca

        return getattr(_alpaca, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
