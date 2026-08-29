# Broker adapters: IB native + Alpaca/QuantConnect stubs. Phase 2.
# Kairos execution contracts (K0): typed venue/order/position models re-exported here
# alongside the protocol and stubs so a caller does not need to import `contracts`
# separately for the common case.

from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerContractModel,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    ExecutionVenue,
    OrderSide,
    OrderType,
    TimeInForce,
)
from digiquant.brokers.stubs import AlpacaAdapterStub, IBAdapterStub, QuantConnectAdapterStub

__all__ = [
    "AlpacaAdapterStub",
    "BrokerAccountSnapshot",
    "BrokerAdapter",
    "BrokerContractModel",
    "BrokerFill",
    "BrokerOrderAck",
    "BrokerOrderRequest",
    "BrokerOrderStatus",
    "BrokerPosition",
    "ExecutionVenue",
    "IBAdapterStub",
    "OrderSide",
    "OrderType",
    "QuantConnectAdapterStub",
    "TimeInForce",
]
