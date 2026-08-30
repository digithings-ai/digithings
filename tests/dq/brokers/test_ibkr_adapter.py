"""Unit tests for the IBKR Web API read-first adapter (K2).

Fully mocked transport — no network. Pins binding rules from K2.md / spec §7:
read path never opens ssodh; orders flag default-off; pacing raises; reply allowlist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.contracts import (
    BrokerAuthError,
    BrokerOrderRejected,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerRateLimited,
    BrokerTransportError,
    OrderSide,
    OrderType,
)
from digiquant.brokers.ibkr import (
    PACE_SECONDS,
    PACED_PATH_MARKERS,
    SUPPRESSIBLE_MESSAGE_IDS,
    IbkrAdapter,
    IbkrHttpResponse,
    IbkrOrdersDisabledError,
    SessionCompetingError,
    _decimal_wire,
    _pace_key,
    encode_json_bytes,
    orders_enabled,
)

pytestmark = pytest.mark.unit


def _resp(body: object, status: int = 200) -> IbkrHttpResponse:
    raw = encode_json_bytes(body)
    return IbkrHttpResponse(status_code=status, body=body, raw_bytes=raw)


class MockTransport:
    """Records every request; returns scripted responses by (method, path) or path prefix."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object, object]] = []
        self._queue: dict[str, list[IbkrHttpResponse]] = {}
        self._defaults: dict[str, IbkrHttpResponse] = {}

    def enqueue(self, method: str, path: str, *responses: IbkrHttpResponse) -> None:
        key = f"{method.upper()} {path}"
        self._queue.setdefault(key, []).extend(responses)

    def set_default(self, method: str, path: str, response: IbkrHttpResponse) -> None:
        self._defaults[f"{method.upper()} {path}"] = response

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object = None,
        params: object = None,
    ) -> IbkrHttpResponse:
        self.calls.append((method.upper(), path, json_body, params))
        key = f"{method.upper()} {path}"
        queued = self._queue.get(key)
        if queued:
            return queued.pop(0)
        if key in self._defaults:
            return self._defaults[key]
        # Prefix match for dynamic account/reply paths.
        for default_key, response in self._defaults.items():
            m, p = default_key.split(" ", 1)
            if m == method.upper() and path.startswith(p.rstrip("/")):
                return response
        for qkey, qlist in list(self._queue.items()):
            m, p = qkey.split(" ", 1)
            if m == method.upper() and path.startswith(p) and qlist:
                return qlist.pop(0)
        raise AssertionError(f"unexpected transport call: {method} {path}")

    def paths_seen(self) -> list[str]:
        return [path for _, path, _, _ in self.calls]

    def saw_ssodh(self) -> bool:
        return any("ssodh/init" in path for path in self.paths_seen())


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _connected_adapter(
    transport: MockTransport,
    *,
    account_id: str = "DU123456",
    clock: FakeClock | None = None,
) -> IbkrAdapter:
    transport.set_default("GET", "/iserver/auth/status", _resp({"authenticated": True}))
    adapter = IbkrAdapter(transport, account_id=account_id, clock=clock or FakeClock())
    adapter.connect()
    return adapter


def _order_req(**overrides: object) -> BrokerOrderRequest:
    fields: dict[str, object] = dict(
        client_order_id="intent-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
    )
    fields.update(overrides)
    return BrokerOrderRequest(**fields)


class TestOrdersFlag:
    def test_orders_enabled_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_IBKR_ORDERS", raising=False)
        assert orders_enabled() is False

    def test_submit_order_raises_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_IBKR_ORDERS", raising=False)
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        with pytest.raises(IbkrOrdersDisabledError):
            adapter.submit_order(_order_req())
        assert not transport.saw_ssodh()

    def test_get_order_raises_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_IBKR_ORDERS", raising=False)
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        with pytest.raises(IbkrOrdersDisabledError):
            adapter.get_order("ord-1")
        assert not transport.saw_ssodh()
        assert not any("ssodh" in p or "suppress" in p for p in transport.paths_seen())

    def test_cancel_order_raises_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_IBKR_ORDERS", raising=False)
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        with pytest.raises(IbkrOrdersDisabledError):
            adapter.cancel_order("ord-1")
        assert not transport.saw_ssodh()

    def test_list_fills_raises_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGIQUANT_IBKR_ORDERS", raising=False)
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        with pytest.raises(IbkrOrdersDisabledError):
            adapter.list_fills(datetime(2026, 1, 1, tzinfo=UTC))
        assert not transport.saw_ssodh()

    def test_flag_on_allows_order_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        assert orders_enabled() is True


class TestReadPathNeverOpensBrokerageSession:
    def test_get_account_never_calls_ssodh(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.set_default(
            "GET",
            "/portfolio/DU123456/summary",
            _resp(
                {
                    "netliquidation": {"amount": 100000.5},
                    "totalcashvalue": {"amount": "25000.25"},
                    "buyingpower": {"amount": "50000"},
                }
            ),
        )
        transport.set_default(
            "GET",
            "/portfolio/DU123456/ledger",
            _resp({"BASE": {"currency": "USD", "cashbalance": "25000.25"}}),
        )
        snap = adapter.get_account()
        assert snap.account_id == "DU123456"
        assert snap.equity == Decimal("100000.5")
        assert snap.cash == Decimal("25000.25")
        assert snap.buying_power == Decimal("50000")
        assert snap.currency == "USD"
        assert not transport.saw_ssodh()
        assert all("ssodh" not in p for p in transport.paths_seen())

    def test_get_positions_paginates_without_ssodh(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        page0 = [
            {
                "ticker": "AAPL",
                "position": "10",
                "avgCost": "150.5",
                "mktValue": "1600",
                "unrealizedPnl": "95",
            },
            {
                "ticker": "MSFT",
                "position": "-5",
                "avgCost": "300",
                "mktValue": "-1400",
                "unrealizedPnl": "100",
            },
        ]
        transport.enqueue("GET", "/portfolio/DU123456/positions/0", _resp(page0))
        transport.enqueue("GET", "/portfolio/DU123456/positions/1", _resp([]))
        positions = adapter.get_positions()
        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("10")
        assert positions[0].avg_entry_price == Decimal("150.5")
        assert positions[1].quantity == Decimal("-5")
        assert not transport.saw_ssodh()
        assert "/portfolio/DU123456/positions/0" in transport.paths_seen()
        assert "/portfolio/DU123456/positions/1" in transport.paths_seen()


class TestSessionLifecycle:
    def test_connect_and_keepalive(self) -> None:
        transport = MockTransport()
        transport.set_default("GET", "/iserver/auth/status", _resp({"authenticated": True}))
        transport.set_default(
            "POST", "/tickle", _resp({"iserver": {"authStatus": {"authenticated": True}}})
        )
        adapter = IbkrAdapter(transport, account_id="DU1")
        adapter.connect()
        body = adapter.keepalive()
        assert "iserver" in body
        assert not transport.saw_ssodh()
        assert isinstance(adapter, BrokerAdapter)

    def test_connect_rejects_unauthenticated(self) -> None:
        transport = MockTransport()
        transport.set_default("GET", "/iserver/auth/status", _resp({"authenticated": False}))
        adapter = IbkrAdapter(transport)
        with pytest.raises(BrokerAuthError):
            adapter.connect()

    def test_expiry_one_reauth_then_auth_error(self) -> None:
        transport = MockTransport()
        clock = FakeClock()
        adapter = _connected_adapter(transport, clock=clock)
        # First summary call → session expired; reauth succeeds; second still expired → error.
        transport.enqueue(
            "GET",
            "/portfolio/DU123456/summary",
            _resp({"error": "not authenticated"}, status=401),
            _resp({"error": "not authenticated"}, status=401),
        )
        # reauth hook path uses transport GET auth status
        transport.enqueue("GET", "/iserver/auth/status", _resp({"authenticated": True}))

        def boom() -> None:
            raise BrokerAuthError("reauth refused")

        adapter._reauth_hook = boom
        with pytest.raises(BrokerAuthError):
            adapter.get_account()

    def test_transparent_reauth_succeeds_once(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.enqueue(
            "GET",
            "/portfolio/DU123456/summary",
            _resp({"error": "not authenticated"}, status=401),
            _resp(
                {
                    "netliquidation": {"amount": "1"},
                    "totalcashvalue": {"amount": "1"},
                    "buyingpower": {"amount": "0"},
                }
            ),
        )
        transport.enqueue(
            "GET",
            "/portfolio/DU123456/ledger",
            _resp({"BASE": {"currency": "USD"}}),
        )
        reauth_calls = {"n": 0}

        def ok_reauth() -> None:
            reauth_calls["n"] += 1

        adapter._reauth_hook = ok_reauth
        snap = adapter.get_account()
        assert snap.equity == Decimal("1")
        assert reauth_calls["n"] == 1


class TestPacingGuard:
    def test_second_immediate_paced_call_raises(self) -> None:
        transport = MockTransport()
        clock = FakeClock(start=0.0)
        adapter = _connected_adapter(transport, account_id="DU9", clock=clock)
        # Hit the paced /portfolio/accounts family via _call directly (account_id is
        # already known, so get_account would not re-fetch accounts).
        transport.enqueue("GET", "/portfolio/accounts", _resp([{"id": "DU9"}]))
        transport.enqueue("GET", "/portfolio/accounts", _resp([{"id": "DU9"}]))
        adapter._call("GET", "/portfolio/accounts", pace=True, allow_reauth=False)
        with pytest.raises(BrokerRateLimited) as exc_info:
            adapter._call("GET", "/portfolio/accounts", pace=True, allow_reauth=False)
        assert exc_info.value.retry_after is not None
        assert 0 < exc_info.value.retry_after <= PACE_SECONDS
        clock.advance(PACE_SECONDS)
        transport.enqueue("GET", "/portfolio/accounts", _resp([{"id": "DU9"}]))
        adapter._call("GET", "/portfolio/accounts", pace=True, allow_reauth=False)
        assert "/portfolio/accounts" in PACED_PATH_MARKERS

    def test_order_submit_path_is_paced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        clock = FakeClock(start=0.0)
        adapter = _connected_adapter(transport, clock=clock)
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        transport.enqueue(
            "GET",
            "/iserver/secdef/search",
            _resp([{"conid": 1, "symbol": "AAPL"}]),
        )
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp([{"order_id": "a", "order_status": "Submitted"}]),
            _resp([{"order_id": "b", "order_status": "Submitted"}]),
        )
        adapter.submit_order(_order_req())
        with pytest.raises(BrokerRateLimited) as exc_info:
            adapter.submit_order(_order_req())
        assert exc_info.value.retry_after is not None
        assert 0 < exc_info.value.retry_after <= PACE_SECONDS


class TestOrderReplyChain:
    def _prime_order_path(self, transport: MockTransport, clock: FakeClock) -> IbkrAdapter:
        adapter = _connected_adapter(transport, clock=clock)
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        transport.enqueue(
            "GET",
            "/iserver/secdef/search",
            _resp([{"conid": 265598, "symbol": "AAPL"}]),
        )
        return adapter

    def test_reply_chain_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        clock = FakeClock()
        adapter = self._prime_order_path(transport, clock)
        # First order response is a suppressible confirmation prompt.
        prompt = {
            "id": "reply-1",
            "message": ["Price percentage constraint"],
            "messageIds": ["o163"],
        }
        ack_body = [{"order_id": "ord-99", "order_status": "Submitted"}]
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp([prompt]),
        )
        transport.enqueue(
            "POST",
            "/iserver/reply/reply-1",
            _resp(ack_body),
        )
        ack = adapter.submit_order(_order_req())
        assert ack.external_order_id == "ord-99"
        assert ack.status is BrokerOrderStatus.SUBMITTED
        assert len(ack.raw_sha256) == 64
        assert transport.saw_ssodh()
        # Suppression list re-applied after session init.
        suppress_calls = [
            (m, p, body)
            for m, p, body, _ in transport.calls
            if p.endswith("/iserver/questions/suppress")
        ]
        assert len(suppress_calls) == 1
        assert set(suppress_calls[0][2]["messageIds"]) == SUPPRESSIBLE_MESSAGE_IDS
        # compete=false on ssodh init
        ssodh = next(c for c in transport.calls if "ssodh/init" in c[1])
        assert ssodh[2] == {"publish": True, "compete": False}

    def test_off_allowlist_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        clock = FakeClock()
        adapter = self._prime_order_path(transport, clock)
        prompt = {
            "id": "reply-x",
            "message": ["Unusual risk acknowledgement required"],
            "messageIds": ["o9999-not-on-list"],
        }
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp([prompt]),
        )
        with pytest.raises(BrokerOrderRejected):
            adapter.submit_order(_order_req())
        # Whole-array classification rejects offlist before any reply POST.
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())
        assert transport.saw_ssodh()  # session opened for the submit attempt

    def test_competing_session_surfaces_without_kick(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": True}),
        )
        with pytest.raises(SessionCompetingError):
            adapter.submit_order(_order_req())
        assert adapter.session_competing is True
        assert adapter.brokerage_session_active is False
        ssodh = next(c for c in transport.calls if "ssodh/init" in c[1])
        assert ssodh[2]["compete"] is False

    def test_conid_cache_reused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        clock = FakeClock()
        adapter = self._prime_order_path(transport, clock)
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp([{"order_id": "o1", "order_status": "Filled"}]),
        )
        adapter.submit_order(_order_req())
        clock.advance(PACE_SECONDS + 0.1)
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp([{"order_id": "o2", "order_status": "Filled"}]),
        )
        adapter.submit_order(_order_req())
        search_calls = [c for c in transport.calls if c[1].startswith("/iserver/secdef/search")]
        assert len(search_calls) == 1


class TestProtocolAndImport:
    def test_isinstance_broker_adapter(self) -> None:
        transport = MockTransport()
        transport.set_default("GET", "/iserver/auth/status", _resp({"authenticated": True}))
        adapter = IbkrAdapter(transport)
        assert isinstance(adapter, BrokerAdapter)

    def test_package_imports_without_extra(self) -> None:
        # Import path used by the package must not require httpx/ibind at module load.
        import digiquant.brokers.ibkr as mod

        assert hasattr(mod, "IbkrAdapter")
        assert "ibind" not in dir(mod)

    def test_disconnect_clears_state(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        adapter.disconnect()
        with pytest.raises(BrokerAuthError):
            adapter.get_account()


class TestDecimalAndFingerprint:
    def test_decimal_only_parsing(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.set_default(
            "GET",
            "/portfolio/DU123456/summary",
            _resp(
                {
                    "netliquidation": {"amount": "12345.67"},
                    "totalcashvalue": {"amount": 100.1},
                    "buyingpower": {"amount": 0},
                }
            ),
        )
        transport.set_default(
            "GET",
            "/portfolio/DU123456/ledger",
            _resp({"USD": {"currency": "usd"}}),
        )
        snap = adapter.get_account()
        assert isinstance(snap.equity, Decimal)
        assert snap.equity == Decimal("12345.67")
        assert snap.cash == Decimal("100.1")

    def test_order_payload_serializes_high_precision_decimal_as_string(self) -> None:
        """High-precision Decimal must round-trip into the payload string losslessly.

        `float(Decimal("10.123456789012345678901234"))` silently becomes
        `10.123456789012346`; the wire form must stay a fixed-point string.
        """
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        precise = Decimal("10.123456789012345678901234")
        # Prove float would lose digits — the bug this test pins.
        assert Decimal(str(float(precise))) != precise
        req = _order_req(quantity=precise, order_type=OrderType.LIMIT, limit_price=precise)
        payload = adapter._build_order_payload(req, account_id="DU1", conid=265598)
        order = payload["orders"][0]
        assert isinstance(order, dict)
        assert order["quantity"] == "10.123456789012345678901234"
        assert order["price"] == "10.123456789012345678901234"
        assert isinstance(order["quantity"], str)
        assert Decimal(str(order["quantity"])) == precise
        # Exponent-form Decimals also become fixed-point strings (no "E").
        assert "E" not in _decimal_wire(Decimal("1E+2"))
        assert _decimal_wire(Decimal("1E+2")) == "100"


class TestReplyChainFailClosed:
    def test_malformed_id_only_body_rejects(self) -> None:
        """Reviewer reproduction: `[{"id": "reply-empty"}]` must not fabricate an ack."""
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        body = [{"id": "reply-empty"}]
        response = _resp(body)
        with pytest.raises(BrokerOrderRejected, match=response.fingerprint) as exc_info:
            adapter._resolve_order_reply_chain(response)
        assert response.fingerprint in str(exc_info.value)
        assert "reply-empty" not in str(exc_info.value)  # fingerprint only, not body

    def test_prompt_with_only_message_rejects(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        body = [{"id": "reply-1", "message": ["Confirm something"]}]
        response = _resp(body)
        with pytest.raises(BrokerOrderRejected, match=response.fingerprint):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

    def test_prompt_with_only_message_ids_rejects(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        body = [{"id": "reply-2", "messageIds": ["o163"]}]
        response = _resp(body)
        with pytest.raises(BrokerOrderRejected, match=response.fingerprint):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())


class TestPacingMarkersDerived:
    def test_pace_key_derived_from_exported_markers(self) -> None:
        assert _pace_key("/portfolio/accounts") == "/portfolio/accounts"
        assert _pace_key("/iserver/orders") == "/iserver/orders"
        assert _pace_key("/iserver/account/DU1/orders") == "/iserver/orders"
        assert _pace_key("/iserver/account/trades") == "/iserver/trades"
        assert _pace_key("/iserver/trades") == "/iserver/trades"
        assert _pace_key("/tickle") is None
        assert _pace_key("/iserver/questions/suppress") is None
        # Every PACED_PATH_MARKERS entry is reachable via _pace_key.
        for marker in PACED_PATH_MARKERS:
            assert _pace_key(marker) == marker


_ALLOW_PROMPT = {
    "id": "r-allow",
    "message": ["Price percentage constraint"],
    "messageIds": ["o163"],
}
_OFF_PROMPT = {
    "id": "r-off",
    "message": ["Unusual risk"],
    "messageIds": ["o9999-not-on-list"],
}
_ACK = {"order_id": "ord-1", "order_status": "Submitted"}
_ACK_OTHER = {"order_id": "ord-2", "order_status": "Submitted"}


class TestWholeArrayReplyClassification:
    """Deep-pass #2: classify every list entry before any reply POST."""

    def test_prompt_then_ack_mixed_rejects_without_reply_post(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        response = _resp([_ALLOW_PROMPT, _ACK])
        with pytest.raises(BrokerOrderRejected, match="mixes prompt"):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

    def test_ack_then_offlist_prompt_rejects_without_reply_post(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        response = _resp([_ACK, _OFF_PROMPT])
        with pytest.raises(BrokerOrderRejected):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

    def test_allowlisted_then_offlist_rejects_without_confirming_first(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        # Would previously confirm r-allow and ignore the offlist sibling.
        transport.enqueue(
            "POST",
            "/iserver/reply/r-allow",
            _resp([_ACK]),
        )
        response = _resp([_ALLOW_PROMPT, _OFF_PROMPT])
        with pytest.raises(BrokerOrderRejected, match="off allowlist|empty messageIds|multiple"):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

    def test_empty_message_and_empty_message_ids_rejects(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        empty = {"id": "empty", "message": [], "messageIds": []}
        transport.enqueue("POST", "/iserver/reply/empty", _resp([_ACK]))
        response = _resp([empty])
        with pytest.raises(BrokerOrderRejected):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

    def test_dual_distinct_order_ids_reject(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        response = _resp([_ACK, _ACK_OTHER])
        with pytest.raises(BrokerOrderRejected, match="multiple distinct order ids"):
            adapter._resolve_order_reply_chain(response)

    def test_multiple_allowlisted_prompts_unsupported(self) -> None:
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        second = {
            "id": "r-allow-2",
            "message": ["Missing market data"],
            "messageIds": ["o354"],
        }
        response = _resp([_ALLOW_PROMPT, second])
        with pytest.raises(BrokerOrderRejected, match="multi-reply unsupported"):
            adapter._resolve_order_reply_chain(response)
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())


class TestBrokerageSessionCoupling:
    """Session is active only after init AND suppression both succeed; re-auth clears it."""

    def test_suppress_500_not_sticky(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"error": "fail"}, status=500),
        )
        with pytest.raises(BrokerTransportError):
            adapter._ensure_brokerage_session()
        assert adapter.brokerage_session_active is False
        # Next attempt must re-run both init and suppress (not skip).
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        adapter._ensure_brokerage_session()
        assert adapter.brokerage_session_active is True
        assert sum(1 for p in transport.paths_seen() if "ssodh/init" in p) == 2
        assert sum(1 for p in transport.paths_seen() if "questions/suppress" in p) == 2

    def test_reauth_clears_brokerage_and_reapplies_suppress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        adapter = _connected_adapter(transport)
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        adapter._ensure_brokerage_session()
        assert adapter.brokerage_session_active is True
        assert sum(1 for p in transport.paths_seen() if "questions/suppress" in p) == 1

        adapter._reauth_hook = lambda: None
        transport.enqueue(
            "GET",
            "/iserver/account/order/status/ord-x",
            _resp({"error": "not authenticated"}, status=401),
            _resp({"order_id": "ord-x", "order_status": "Submitted"}),
        )
        adapter.get_order("ord-x")
        assert adapter.brokerage_session_active is False

        # Next order-lifecycle call must re-init + re-suppress.
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        transport.enqueue(
            "GET",
            "/iserver/account/order/status/ord-y",
            _resp({"order_id": "ord-y", "order_status": "Submitted"}),
        )
        adapter.get_order("ord-y")
        assert adapter.brokerage_session_active is True
        assert sum(1 for p in transport.paths_seen() if "ssodh/init" in p) == 2
        assert sum(1 for p in transport.paths_seen() if "questions/suppress" in p) == 2

    def test_reauth_retry_does_not_recharge_pacing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_IBKR_ORDERS", "1")
        transport = MockTransport()
        clock = FakeClock(start=0.0)
        adapter = _connected_adapter(transport, clock=clock)
        adapter._reauth_hook = lambda: None
        transport.enqueue(
            "POST",
            "/iserver/auth/ssodh/init",
            _resp({"authenticated": True, "competing": False}),
        )
        transport.enqueue(
            "POST",
            "/iserver/questions/suppress",
            _resp({"status": "submitted"}),
        )
        transport.enqueue(
            "GET",
            "/iserver/secdef/search",
            _resp([{"conid": 265598, "symbol": "AAPL"}]),
        )
        transport.enqueue(
            "POST",
            "/iserver/account/DU123456/orders",
            _resp({"error": "not authenticated"}, status=401),
            _resp([{"order_id": "ord-paced", "order_status": "Submitted"}]),
        )
        ack = adapter.submit_order(_order_req())
        assert ack.external_order_id == "ord-paced"
        # Same-instant retry must not raise BrokerRateLimited.
        order_posts = [c for c in transport.calls if c[1].endswith("/orders") and c[0] == "POST"]
        assert len(order_posts) == 2
