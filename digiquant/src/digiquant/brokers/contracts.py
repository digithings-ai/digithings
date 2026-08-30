"""Kairos execution contracts: typed venue/order/position models for broker adapters.

Every real or stub `BrokerAdapter` implementation (`base.py`) exchanges these Pydantic
models with a venue instead of loose positional args. This closes the surface a K1/K2
adapter has to fill in and gives every downstream caller (K4's router/sync) one shared,
strict vocabulary for "what an order is", "what a fill is", and "what a position is",
rather than each adapter inventing its own dict shape.

Scope — contracts and typing only, mirroring `hermes/models/portfolio_ledger.py`'s style
exactly (`StrEnum` vocabularies, a frozen strict base, `Decimal` money/quantity fields,
`model_validator(mode="after")` business rules). This module performs **no I/O**: no HTTP
client, no broker SDK, no database access, and it does not construct or call any venue
router — `ExecutionVenue` enumerates `*_LIVE` values so the vocabulary is complete for a
later work package's routing policy, but nothing here, or anywhere else in this module,
ever resolves to or dispatches against one.

Money and quantity fields are always `Decimal`, never `float`, matching the ledger's
established convention (a `float` share count or dollar amount is exactly the kind of
silent precision loss that convention exists to rule out). Every timestamp field is a
UTC-only `AwareDatetime`, rejected if naive or offset by anything other than +00:00,
mirroring `portfolio_ledger._reject_non_utc` (reimplemented locally rather than imported,
since that helper is private to its module and this module must not import from
`hermes/`).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Symbol: TypeAlias = Annotated[str, Field(min_length=1, max_length=20)]
PositiveQuantity: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
# A position's signed share/contract count: positive is long, negative is short, zero is
# a flat/closed row a venue may still report. Deliberately unconstrained in sign, unlike
# `PositiveQuantity`, which every order/fill quantity uses instead.
SignedQuantity: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
PositivePrice: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegativePrice: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
# Money, in total dollars. `PositiveMoney` is kept as its own alias rather than reusing
# `PositiveQuantity` even though the numeric constraint is identical: a dollar notional
# typed as a share count is exactly the unit confusion `portfolio_ledger.py`'s `Fee`
# comment warns reads as correct forever.
PositiveMoney: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegativeMoney: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
# Equity/cash/market-value/P&L can legitimately go negative (a margin debit, an
# underwater short's market value, an unrealized loss) so these admit both signs.
SignedMoney: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
Fee: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class ExecutionVenue(StrEnum):
    """Closed vocabulary of execution venues an `OrderIntent` can be routed to.

    `ALPACA_LIVE`/`IBKR_LIVE` are defined so this vocabulary is complete for a later
    work package's venue-resolution policy, but this module never routes to them: K0
    is contracts only, with no router, no resolver, and no dispatch logic of any kind.
    """

    PAPER_INTERNAL = "paper_internal"
    ALPACA_PAPER = "alpaca_paper"
    IBKR_PAPER = "ibkr_paper"
    ALPACA_LIVE = "alpaca_live"
    IBKR_LIVE = "ibkr_live"


class BrokerOrderStatus(StrEnum):
    """Closed vocabulary of broker-reported order lifecycle states."""

    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(StrEnum):
    """Closed vocabulary of order sides."""

    BUY = "buy"
    SELL = "sell"


class TimeInForce(StrEnum):
    """Closed vocabulary of supported time-in-force values."""

    DAY = "day"
    GTC = "gtc"
    OPG = "opg"
    IOC = "ioc"


class OrderType(StrEnum):
    """Closed vocabulary for `BrokerOrderRequest.order_type`.

    v1 supports market/limit only; stop and stop-limit are not modeled until a later
    work package's behavior spec actually needs them.
    """

    MARKET = "market"
    LIMIT = "limit"


def _reject_non_utc(*values: AwareDatetime | None) -> None:
    """Raise unless every non-null timestamp is UTC (offset exactly +00:00).

    Mirrors `hermes.models.portfolio_ledger._reject_non_utc` exactly; reimplemented here
    rather than imported because that helper is private to its module.
    """
    for value in values:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("broker contract timestamps must be UTC")


class BrokerContractModel(BaseModel):
    """Strict, immutable base for every Kairos broker contract.

    Mirrors `hermes.models.portfolio_ledger.PortfolioLedgerModel`: unknown fields are
    rejected rather than silently dropped, and instances are frozen — a submitted order
    request, an ack, or a fill is never mutated in place; a caller that needs a changed
    value constructs a new instance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class _SymbolNormalizingModel(BrokerContractModel):
    """Shared `symbol` before-validator: strip + uppercase ahead of length validation.

    Every contract below that carries a `symbol` field inherits this so `" aapl "` and
    `"AAPL"` validate to the identical stored value, instead of three copies of the same
    validator drifting apart over time.
    """

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _normalize_symbol(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class BrokerOrderRequest(_SymbolNormalizingModel):
    """A caller's request to submit one order to a venue via `BrokerAdapter.submit_order`.

    `client_order_id` is set to `str(order_intent_id)` when the request is derived from a
    Hermes `OrderIntent` (a later work package), so a resubmit after a crash is
    recoverable by looking the id up on the venue before retrying, never by inferring one
    from a freshly randomized id. `quantity`/`notional` are XOR — exactly one is set,
    mirroring `RequestedTarget`'s weight/quantity XOR in `portfolio_ledger.py`.
    `limit_price` is required iff `order_type` is `limit` and forbidden otherwise.
    """

    client_order_id: Annotated[str, Field(min_length=1, max_length=100)]
    symbol: Symbol
    side: OrderSide
    quantity: PositiveQuantity | None = None
    notional: PositiveMoney | None = None
    order_type: OrderType = OrderType.MARKET
    limit_price: PositivePrice | None = None
    time_in_force: TimeInForce = TimeInForce.DAY

    @model_validator(mode="after")
    def validate_lifecycle(self) -> BrokerOrderRequest:
        if (self.quantity is None) == (self.notional is None):
            raise ValueError(
                "a broker order request requires exactly one of quantity/notional, "
                "never both or neither"
            )
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required when order_type is 'limit'")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("limit_price must be absent when order_type is 'market'")
        return self


class BrokerOrderAck(BrokerContractModel):
    """A venue's acknowledgement of a submitted (or later re-queried) order.

    `raw_sha256` is the SHA-256 hex digest of the venue's raw response payload — a
    tamper-evident fingerprint for audit, never the payload itself, so a log or ledger
    row can prove which response an ack was derived from without persisting (and risking
    leaking) broker-specific fields this contract doesn't otherwise model.
    """

    external_order_id: Annotated[str, Field(min_length=1, max_length=100)]
    status: BrokerOrderStatus
    submitted_at: AwareDatetime
    raw_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def validate_lifecycle(self) -> BrokerOrderAck:
        _reject_non_utc(self.submitted_at)
        return self


class BrokerFill(_SymbolNormalizingModel):
    """An immutable fill a venue reports for a previously submitted order.

    `quantity` and `price` are required, strictly-positive `Decimal` fields — "no fill
    happened" is the absence of a `BrokerFill`, never a zero-valued one, mirroring
    `PaperExecution`'s identical invariant in `portfolio_ledger.py`.
    """

    external_fill_id: Annotated[str, Field(min_length=1, max_length=100)]
    symbol: Symbol
    quantity: PositiveQuantity
    price: PositivePrice
    fee: Fee | None = None
    executed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self) -> BrokerFill:
        _reject_non_utc(self.executed_at)
        return self


class BrokerPosition(_SymbolNormalizingModel):
    """A venue-reported open position, signed by direction (long positive, short negative)."""

    symbol: Symbol
    quantity: SignedQuantity
    avg_entry_price: NonNegativePrice
    market_value: SignedMoney
    unrealized_pl: SignedMoney


class BrokerAccountSnapshot(BrokerContractModel):
    """A point-in-time snapshot of one broker account's cash/equity/buying-power state."""

    account_id: Annotated[str, Field(min_length=1, max_length=100)]
    equity: SignedMoney
    cash: SignedMoney
    buying_power: NonNegativeMoney
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    as_of: AwareDatetime

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> BrokerAccountSnapshot:
        _reject_non_utc(self.as_of)
        return self


# --- Broker exception family (K1; shared with K2) ---------------------------------
# Appended for the Alpaca paper adapter (K1) and reused by IBKR (K2). Do not reorder
# the models above; new exception types only land below this banner.


class BrokerError(Exception):
    """Base for every broker-adapter failure a caller is expected to handle."""


class BrokerAuthError(BrokerError):
    """Venue rejected credentials (HTTP 401/403)."""


class BrokerOrderRejected(BrokerError):
    """Venue (or local pre-submit guard) rejected the order (HTTP 422 or local rule)."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class BrokerRateLimited(BrokerError):
    """Venue rate-limited the call (HTTP 429); ``retry_after`` is seconds when known."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__(f"broker rate limited; retry_after={retry_after!r}")
        self.retry_after = retry_after


class BrokerTransportError(BrokerError):
    """Network / non-mapped HTTP failure talking to the venue."""


class BrokerOrderNotFound(BrokerError):
    """Venue reports no order for the given id (HTTP 404).

    The only lookup outcome that authorizes a submit resubmit: any other failure
    must propagate without calling submit again.
    """


class LiveVenueNotAuthorizedError(BrokerError):
    """Construction or routing attempted a live venue that this program forbids."""


__all__ = [
    "BrokerAccountSnapshot",
    "BrokerContractModel",
    "BrokerFill",
    "BrokerOrderAck",
    "BrokerOrderRequest",
    "BrokerOrderStatus",
    "BrokerPosition",
    "ExecutionVenue",
    "Fee",
    "NonNegativeMoney",
    "NonNegativePrice",
    "OrderSide",
    "OrderType",
    "PositiveMoney",
    "PositivePrice",
    "PositiveQuantity",
    "SignedMoney",
    "SignedQuantity",
    "Symbol",
    "TimeInForce",
    # K1 exception family (appended; do not reorder entries above)
    "BrokerAuthError",
    "BrokerError",
    "BrokerOrderNotFound",
    "BrokerOrderRejected",
    "BrokerRateLimited",
    "BrokerTransportError",
    "LiveVenueNotAuthorizedError",
]
