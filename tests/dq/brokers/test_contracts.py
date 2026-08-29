"""Tests for the Kairos execution contracts (K0): venue/order/position models and the
widened `BrokerAdapter` protocol.

Covers each `model_validator`/`field_validator` branch called out in the work package's
acceptance criteria — quantity/notional XOR, limit_price/order_type coupling, symbol and
currency normalization, UTC-only timestamp rejection, `raw_sha256` shape — plus the
frozen/extra-forbid base and runtime-checkable protocol conformance for every stub.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from digiquant.brokers import (
    AlpacaAdapterStub,
    BrokerAccountSnapshot,
    BrokerAdapter,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    ExecutionVenue,
    IBAdapterStub,
    OrderSide,
    OrderType,
    QuantConnectAdapterStub,
    TimeInForce,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_VALID_SHA256 = "a" * 64


def _ts(hour: int = 12) -> datetime:
    return datetime(2026, 8, 29, hour, 0, tzinfo=UTC)


def make_order_request(**overrides: object) -> BrokerOrderRequest:
    fields: dict[str, object] = dict(
        client_order_id="intent-1",
        symbol="aapl",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
    )
    fields.update(overrides)
    return BrokerOrderRequest(**fields)


class TestExecutionVenue:
    """Vocabulary is complete (incl. live values) but nothing routes to them here."""

    def test_members_are_strings(self) -> None:
        assert ExecutionVenue.PAPER_INTERNAL == "paper_internal"
        assert isinstance(ExecutionVenue.PAPER_INTERNAL, str)

    def test_live_members_defined_but_inert(self) -> None:
        # Defined for a later work package's routing policy; K0 ships no router.
        assert ExecutionVenue.ALPACA_LIVE == "alpaca_live"
        assert ExecutionVenue.IBKR_LIVE == "ibkr_live"

    def test_all_members_present(self) -> None:
        assert {member.value for member in ExecutionVenue} == {
            "paper_internal",
            "alpaca_paper",
            "ibkr_paper",
            "alpaca_live",
            "ibkr_live",
        }


class TestSmallVocabularies:
    def test_broker_order_status_members(self) -> None:
        assert {member.value for member in BrokerOrderStatus} == {
            "submitted",
            "accepted",
            "partially_filled",
            "filled",
            "canceled",
            "rejected",
            "expired",
        }

    def test_order_side_members(self) -> None:
        assert {member.value for member in OrderSide} == {"buy", "sell"}

    def test_time_in_force_members(self) -> None:
        assert {member.value for member in TimeInForce} == {"day", "gtc", "opg", "ioc"}

    def test_order_type_members(self) -> None:
        assert {member.value for member in OrderType} == {"market", "limit"}


class TestBrokerOrderRequest:
    def test_valid_market_order_with_quantity(self) -> None:
        req = make_order_request(quantity=Decimal("10"), notional=None)
        assert req.symbol == "AAPL"
        assert req.order_type is OrderType.MARKET
        assert req.time_in_force is TimeInForce.DAY

    def test_valid_market_order_with_notional(self) -> None:
        req = make_order_request(quantity=None, notional=Decimal("500.00"))
        assert req.notional == Decimal("500.00")
        assert req.quantity is None

    def test_symbol_is_stripped_and_uppercased(self) -> None:
        req = make_order_request(symbol="  msft  ")
        assert req.symbol == "MSFT"

    def test_quantity_and_notional_both_set_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=Decimal("10"), notional=Decimal("500"))

    def test_quantity_and_notional_both_absent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=None, notional=None)

    def test_non_positive_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=Decimal("0"), notional=None)

    def test_non_positive_notional_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=None, notional=Decimal("-1"))

    def test_limit_order_requires_limit_price(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(order_type=OrderType.LIMIT, limit_price=None)

    def test_limit_order_with_limit_price_is_valid(self) -> None:
        req = make_order_request(order_type=OrderType.LIMIT, limit_price=Decimal("150.25"))
        assert req.limit_price == Decimal("150.25")

    def test_market_order_forbids_limit_price(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(order_type=OrderType.MARKET, limit_price=Decimal("150.25"))

    def test_non_positive_limit_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(order_type=OrderType.LIMIT, limit_price=Decimal("0"))

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(unexpected_field="nope")

    def test_frozen_rejects_mutation(self) -> None:
        req = make_order_request()
        with pytest.raises(ValidationError):
            req.symbol = "TSLA"  # type: ignore[misc]

    def test_nan_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=Decimal("NaN"), notional=None)

    def test_infinite_notional_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_order_request(quantity=None, notional=Decimal("Infinity"))


class TestBrokerOrderAck:
    def _make(self, **overrides: object) -> BrokerOrderAck:
        fields: dict[str, object] = dict(
            external_order_id="ext-1",
            status=BrokerOrderStatus.ACCEPTED,
            submitted_at=_ts(),
            raw_sha256=_VALID_SHA256,
        )
        fields.update(overrides)
        return BrokerOrderAck(**fields)

    def test_valid_ack(self) -> None:
        ack = self._make()
        assert ack.status is BrokerOrderStatus.ACCEPTED

    def test_non_utc_offset_rejected(self) -> None:
        non_utc = datetime(2026, 8, 29, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
        with pytest.raises(ValidationError):
            self._make(submitted_at=non_utc)

    def test_raw_sha256_wrong_length_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(raw_sha256="a" * 63)

    def test_raw_sha256_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(raw_sha256="A" * 64)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            self._make(unexpected_field="nope")


class TestBrokerFill:
    def _make(self, **overrides: object) -> BrokerFill:
        fields: dict[str, object] = dict(
            external_fill_id="fill-1",
            symbol="aapl",
            quantity=Decimal("5"),
            price=Decimal("150.00"),
            executed_at=_ts(),
        )
        fields.update(overrides)
        return BrokerFill(**fields)

    def test_valid_fill(self) -> None:
        fill = self._make()
        assert fill.symbol == "AAPL"
        assert fill.fee is None

    def test_fee_defaults_to_none_not_zero(self) -> None:
        fill = self._make()
        assert fill.fee is None

    def test_explicit_zero_fee_is_valid(self) -> None:
        fill = self._make(fee=Decimal("0"))
        assert fill.fee == Decimal("0")

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(fee=Decimal("-1"))

    def test_non_positive_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(quantity=Decimal("0"))

    def test_non_positive_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(price=Decimal("-1"))

    def test_non_utc_offset_rejected(self) -> None:
        non_utc = datetime(2026, 8, 29, 12, 0, tzinfo=timezone(timedelta(hours=2)))
        with pytest.raises(ValidationError):
            self._make(executed_at=non_utc)

    def test_frozen_rejects_mutation(self) -> None:
        fill = self._make()
        with pytest.raises(ValidationError):
            fill.price = Decimal("999")  # type: ignore[misc]


class TestBrokerPosition:
    def _make(self, **overrides: object) -> BrokerPosition:
        fields: dict[str, object] = dict(
            symbol="aapl",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150.00"),
            market_value=Decimal("1550.00"),
            unrealized_pl=Decimal("50.00"),
        )
        fields.update(overrides)
        return BrokerPosition(**fields)

    def test_valid_long_position(self) -> None:
        pos = self._make()
        assert pos.symbol == "AAPL"
        assert pos.quantity == Decimal("10")

    def test_short_position_allows_negative_quantity(self) -> None:
        pos = self._make(
            quantity=Decimal("-10"),
            market_value=Decimal("-1550.00"),
            unrealized_pl=Decimal("-20.00"),
        )
        assert pos.quantity == Decimal("-10")

    def test_negative_avg_entry_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(avg_entry_price=Decimal("-1"))

    def test_nan_market_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(market_value=Decimal("NaN"))

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            self._make(unexpected_field="nope")


class TestBrokerAccountSnapshot:
    def _make(self, **overrides: object) -> BrokerAccountSnapshot:
        fields: dict[str, object] = dict(
            account_id="acct-1",
            equity=Decimal("100000.00"),
            cash=Decimal("50000.00"),
            buying_power=Decimal("100000.00"),
            currency="usd",
            as_of=_ts(),
        )
        fields.update(overrides)
        return BrokerAccountSnapshot(**fields)

    def test_valid_snapshot(self) -> None:
        snap = self._make()
        assert snap.currency == "USD"

    def test_negative_buying_power_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(buying_power=Decimal("-1"))

    def test_negative_equity_allowed(self) -> None:
        snap = self._make(equity=Decimal("-500"))
        assert snap.equity == Decimal("-500")

    def test_malformed_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(currency="US")

    def test_non_utc_as_of_rejected(self) -> None:
        non_utc = datetime(2026, 8, 29, 12, 0, tzinfo=timezone(timedelta(hours=2)))
        with pytest.raises(ValidationError):
            self._make(as_of=non_utc)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            self._make(unexpected_field="nope")


class TestBrokerAdapterProtocolConformance:
    """Stubs satisfy the widened runtime-checkable protocol (acceptance criterion)."""

    @pytest.mark.parametrize(
        "stub_cls",
        [IBAdapterStub, AlpacaAdapterStub, QuantConnectAdapterStub],
    )
    def test_stub_satisfies_broker_adapter_protocol(self, stub_cls: type) -> None:
        assert isinstance(stub_cls(), BrokerAdapter)

    def test_stub_submit_order_takes_request_and_raises(self) -> None:
        req = make_order_request()
        with pytest.raises(NotImplementedError):
            IBAdapterStub().submit_order(req)

    def test_stub_exposes_full_widened_surface(self) -> None:
        stub = AlpacaAdapterStub()
        for method_name in (
            "get_account",
            "get_positions",
            "get_order",
            "cancel_order",
            "list_fills",
        ):
            assert hasattr(stub, method_name), f"missing {method_name}"

        with pytest.raises(NotImplementedError):
            stub.get_account()
        with pytest.raises(NotImplementedError):
            stub.get_positions()
        with pytest.raises(NotImplementedError):
            stub.get_order("ext-1")
        with pytest.raises(NotImplementedError):
            stub.cancel_order("ext-1")
        with pytest.raises(NotImplementedError):
            stub.list_fills(_ts())
