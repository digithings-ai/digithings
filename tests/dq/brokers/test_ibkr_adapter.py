"""Unit tests for the IBKR Web API read-first adapter (K2).

Fully mocked transport — no network. Pins binding rules from K2.md / spec §7:
read path never opens ssodh; orders flag default-off; pacing raises; reply allowlist.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.contracts import (
    BrokerOrderRequest,
    BrokerOrderStatus,
    OrderSide,
    OrderType,
)
from digiquant.brokers.ibkr import (
    PACE_SECONDS,
    PACED_PATH_MARKERS,
    SUPPRESSIBLE_MESSAGE_IDS,
    BrokerAuthError,
    BrokerOrderRejected,
    BrokerRateLimited,
    IbkrAdapter,
    IbkrHttpResponse,
    IbkrOrdersDisabledError,
    SessionCompetingError,
    encode_json_bytes,
    orders_enabled,
)

pytestmark = pytest.mark.unit


def _resp(body: Any, status: int = 200) -> IbkrHttpResponse:
    raw = encode_json_bytes(body)
    return IbkrHttpResponse(status_code=status, body=body, raw_bytes=raw)


class MockTransport:
    """Records every request; returns scripted responses by (method, path) or path prefix."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any, Any]] = []
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
        json_body: Any = None,
        params: Any = None,
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
        with pytest.raises(BrokerRateLimited, match="portfolio/accounts"):
            adapter._call("GET", "/portfolio/accounts", pace=True, allow_reauth=False)
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
        with pytest.raises(BrokerRateLimited, match="iserver/orders"):
            adapter.submit_order(_order_req())


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
        with pytest.raises(BrokerOrderRejected) as exc_info:
            adapter.submit_order(_order_req())
        assert "Unusual risk" in (exc_info.value.question_text or "")
        # Must not have confirmed the off-allowlist prompt.
        assert not any("/iserver/reply/" in p for p in transport.paths_seen())

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
