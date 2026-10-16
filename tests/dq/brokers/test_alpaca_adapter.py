"""Mocked unit tests for the Alpaca paper adapter (K1).

Every test mocks ``TradingClient`` / transport — no live HTTP. Covers happy-path
submit/cancel/positions/account, each mapped error class, the local TIF guard
(notional/fractional ⇒ DAY, no HTTP), idempotent recovery after submit transport
failure, and package import without ``alpaca-py``.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from digiquant.brokers.alpaca import AlpacaAdapter, ApiKeyAuth, OAuthAuth
from digiquant.brokers.base import BrokerAdapter
from digiquant.brokers.contracts import (
    BrokerAuthError,
    BrokerOrderNotFound,
    BrokerOrderRejected,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerRateLimited,
    BrokerTransportError,
    LiveVenueNotAuthorizedError,
    OrderSide,
    OrderType,
    TimeInForce,
)

pytestmark = pytest.mark.unit


def _patch_trading_client(monkeypatch: pytest.MonkeyPatch, ctor: object) -> None:
    """Patch ``_TradingClient`` on the module dict ``AlpacaAdapter`` closes over.

    Other tests (``test_sync_cron``) may drop ``sys.modules["digiquant.brokers.alpaca"]``.
    ``monkeypatch.setattr("digiquant.brokers.alpaca._TradingClient", ...)`` then
    patches a freshly imported copy while this file's ``AlpacaAdapter`` still
    looks up the original global — real paper-api HTTP and 401s. Patch the
    class's ``__globals__`` instead.
    """
    monkeypatch.setitem(AlpacaAdapter.__init__.__globals__, "_TradingClient", ctor)


def _ts() -> datetime:
    return datetime(2026, 8, 29, 15, 30, tzinfo=UTC)


def _fake_order(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = dict(
        id="ord-1",
        client_order_id="intent-1",
        status="accepted",
        submitted_at=_ts(),
        created_at=_ts(),
        updated_at=_ts(),
        filled_at=None,
        symbol="AAPL",
        filled_qty="0",
        filled_avg_price=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_request(**overrides: object) -> BrokerOrderRequest:
    fields: dict[str, object] = dict(
        client_order_id="intent-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        time_in_force=TimeInForce.DAY,
    )
    fields.update(overrides)
    return BrokerOrderRequest(**fields)


@pytest.fixture
def client() -> MagicMock:
    return MagicMock(name="TradingClient")


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> AlpacaAdapter:
    import digiquant.brokers.alpaca as alpaca_mod

    if alpaca_mod._MarketOrderRequest is None:
        pytest.skip("alpaca-py not installed — install digiquant[brokers-alpaca] for unit mocks")
    _patch_trading_client(monkeypatch, MagicMock(return_value=client))
    return AlpacaAdapter(auth=ApiKeyAuth(key_id="PK_TEST", secret="SK_TEST"))


class TestConstruction:
    def test_paper_true_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctor = MagicMock(return_value=MagicMock())
        _patch_trading_client(monkeypatch, ctor)
        import digiquant.brokers.alpaca as alpaca_mod

        if alpaca_mod._MarketOrderRequest is None:
            pytest.skip("alpaca-py not installed")
        AlpacaAdapter(auth=ApiKeyAuth(key_id="PK", secret="SK"))
        ctor.assert_called_once()
        kwargs = ctor.call_args.kwargs
        assert kwargs["paper"] is True
        assert kwargs["api_key"] == "PK"
        assert kwargs["secret_key"] == "SK"
        assert "oauth_token" not in kwargs

    def test_paper_true_with_oauth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctor = MagicMock(return_value=MagicMock())
        _patch_trading_client(monkeypatch, ctor)
        import digiquant.brokers.alpaca as alpaca_mod

        if alpaca_mod._MarketOrderRequest is None:
            pytest.skip("alpaca-py not installed")
        AlpacaAdapter(auth=OAuthAuth(access_token="tok_abc"))
        kwargs = ctor.call_args.kwargs
        assert kwargs["paper"] is True
        assert kwargs["oauth_token"] == "tok_abc"

    def test_oauth_mock_survives_sys_modules_pop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reimport after pop must not steal the collection-time class's client.

        String ``setattr`` on ``digiquant.brokers.alpaca._TradingClient`` patches
        the *new* module. ``AlpacaAdapter`` was imported at collection and still
        looks up ``_TradingClient`` on the original globals. Poison that slot
        first so a helper revert fails closed (RuntimeError) instead of live HTTP.
        """
        import digiquant.brokers.alpaca as alpaca_mod

        if alpaca_mod._MarketOrderRequest is None:
            pytest.skip("alpaca-py not installed")
        boom = MagicMock(side_effect=RuntimeError("unpatched collection-time TradingClient"))
        monkeypatch.setitem(AlpacaAdapter.__init__.__globals__, "_TradingClient", boom)
        monkeypatch.delitem(sys.modules, "digiquant.brokers.alpaca", raising=False)
        importlib.import_module("digiquant.brokers.alpaca")
        fresh_ctor = MagicMock(return_value=MagicMock())
        monkeypatch.setattr("digiquant.brokers.alpaca._TradingClient", fresh_ctor)
        ctor = MagicMock(return_value=MagicMock())
        _patch_trading_client(monkeypatch, ctor)
        AlpacaAdapter(auth=OAuthAuth(access_token="tok_abc"))
        ctor.assert_called_once()
        fresh_ctor.assert_not_called()
        boom.assert_not_called()
        assert ctor.call_args.kwargs["oauth_token"] == "tok_abc"
        assert ctor.call_args.kwargs["paper"] is True

    def test_live_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_trading_client(monkeypatch, MagicMock(return_value=MagicMock()))
        import digiquant.brokers.alpaca as alpaca_mod

        if alpaca_mod._MarketOrderRequest is None:
            # Guard still runs before SDK check when env != paper.
            pass
        with pytest.raises(LiveVenueNotAuthorizedError):
            AlpacaAdapter(auth=ApiKeyAuth(key_id="PK", secret="SK"), env="live")  # type: ignore[arg-type]

    def test_protocol_conformance(self, adapter: AlpacaAdapter) -> None:
        assert isinstance(adapter, BrokerAdapter)
        assert adapter.name == "alpaca"


class TestHappyPaths:
    def test_submit_market_order(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.submit_order.return_value = _fake_order()
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-1"
        assert ack.status is BrokerOrderStatus.ACCEPTED
        assert len(ack.raw_sha256) == 64
        order_req = client.submit_order.call_args.args[0]
        assert order_req.client_order_id == "intent-1"
        assert order_req.extended_hours is None

    def test_submit_limit_order(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.submit_order.return_value = _fake_order(status="new")
        ack = adapter.submit_order(
            _make_request(
                order_type=OrderType.LIMIT,
                limit_price=Decimal("150.25"),
            )
        )
        assert ack.status is BrokerOrderStatus.SUBMITTED
        order_req = client.submit_order.call_args.args[0]
        assert (
            str(order_req.limit_price) in {"150.25", "150.2500"}
            or float(order_req.limit_price) == 150.25
        )

    def test_cancel_order(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        adapter.cancel_order("ord-1")
        client.cancel_order_by_id.assert_called_once_with("ord-1")

    def test_get_positions_signs_short(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_all_positions.return_value = [
            SimpleNamespace(
                symbol="AAPL",
                qty="10",
                side="long",
                avg_entry_price="100.00",
                market_value="1050.00",
                unrealized_pl="50.00",
            ),
            SimpleNamespace(
                symbol="TSLA",
                qty="2",
                side="short",
                avg_entry_price="200.00",
                market_value="-400.00",
                unrealized_pl="-10.00",
            ),
        ]
        positions = adapter.get_positions()
        assert positions[0].quantity == Decimal("10")
        assert positions[1].quantity == Decimal("-2")
        assert positions[0].avg_entry_price == Decimal("100.00")

    def test_get_account(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_account.return_value = SimpleNamespace(
            id="acct-1",
            equity="100000.50",
            cash="25000.00",
            buying_power="50000.00",
            currency="usd",
        )
        snap = adapter.get_account()
        assert snap.account_id == "acct-1"
        assert snap.equity == Decimal("100000.50")
        assert snap.currency == "USD"
        assert snap.as_of.tzinfo is not None

    def test_list_fills_from_closed_orders(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_orders.return_value = [
            _fake_order(
                id="fill-1",
                filled_qty="3",
                filled_avg_price="150.10",
                filled_at=_ts(),
                status="filled",
            ),
            _fake_order(id="empty", filled_qty="0", filled_avg_price=None),
        ]
        fills = adapter.list_fills(since=_ts())
        assert len(fills) == 1
        assert fills[0].external_fill_id == "fill-1"
        assert fills[0].quantity == Decimal("3")
        assert fills[0].price == Decimal("150.10")


class TestLocalTifGuard:
    def test_notional_gtc_rejected_without_http(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        req = _make_request(
            quantity=None,
            notional=Decimal("100.00"),
            time_in_force=TimeInForce.GTC,
        )
        with pytest.raises(BrokerOrderRejected, match="fractional/notional requires day TIF") as ei:
            adapter.submit_order(req)
        assert ei.value.code == "local_tif_guard"
        client.submit_order.assert_not_called()

    def test_fractional_qty_gtc_rejected_without_http(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        req = _make_request(quantity=Decimal("1.5"), time_in_force=TimeInForce.GTC)
        with pytest.raises(BrokerOrderRejected, match="fractional/notional requires day TIF"):
            adapter.submit_order(req)
        client.submit_order.assert_not_called()


class TestErrorMapping:
    def _api_error(self, status: int, code: int = 42210000, message: str = "bad") -> Exception:
        from alpaca.common.exceptions import APIError

        http = MagicMock()
        http.response.status_code = status
        http.response.headers = {"X-Request-ID": "req-abc"}
        return APIError(f'{{"code":{code},"message":"{message}"}}', http_error=http)

    def test_401_maps_to_auth(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_account.side_effect = self._api_error(401, message="unauthorized")
        with pytest.raises(BrokerAuthError):
            adapter.get_account()

    def test_403_maps_to_auth(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_account.side_effect = self._api_error(403, message="forbidden")
        with pytest.raises(BrokerAuthError):
            adapter.get_account()

    def test_401_non_json_body_does_not_leak_json_error(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        from alpaca.common.exceptions import APIError

        http = MagicMock()
        http.response.status_code = 401
        http.response.headers = {}
        client.get_account.side_effect = APIError("not-json-body", http_error=http)
        with pytest.raises(BrokerAuthError):
            adapter.get_account()

    def test_422_maps_to_rejected(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.submit_order.side_effect = self._api_error(422, code=42210000, message="invalid qty")
        with pytest.raises(BrokerOrderRejected) as ei:
            adapter.submit_order(_make_request())
        assert ei.value.code == "42210000"
        assert "invalid qty" in ei.value.message

    def test_429_retries_then_raises(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", sleeps.append)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        from alpaca.common.exceptions import APIError

        http = MagicMock()
        http.response.status_code = 429
        http.response.headers = {"Retry-After": "1.5", "X-Request-ID": "r1"}
        err = APIError('{"code":42910000,"message":"slow down"}', http_error=http)
        client.get_account.side_effect = err
        with pytest.raises(BrokerRateLimited) as ei:
            adapter.get_account()
        assert ei.value.retry_after == 1.5
        assert client.get_account.call_count == 3
        assert len(sleeps) == 2

    def test_other_status_maps_to_transport(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        client.get_account.side_effect = self._api_error(500, message="boom")
        with pytest.raises(BrokerTransportError):
            adapter.get_account()

    def test_404_maps_to_order_not_found(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.get_order_by_client_id.side_effect = self._api_error(404, message="missing")
        with pytest.raises(BrokerOrderNotFound):
            adapter._call(client.get_order_by_client_id, "intent-1")


class TestIdempotentRecovery:
    def _api_error(self, status: int, message: str = "err") -> Exception:
        from alpaca.common.exceptions import APIError

        http = MagicMock()
        http.response.status_code = status
        http.response.headers = {"Retry-After": "0"} if status == 429 else {}
        body = f'{{"code":{status},"message":"{message}"}}'
        return APIError(body, http_error=http)

    def test_transport_failure_recovers_via_client_order_id(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        client.submit_order.side_effect = ConnectionError("connection reset")
        client.get_order_by_client_id.return_value = _fake_order(id="ord-recovered")
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-recovered"
        client.get_order_by_client_id.assert_called_once_with("intent-1")
        # No second submit — recovery found the order.
        assert client.submit_order.call_count == 1

    def test_transport_failure_retries_when_client_id_404(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        order = _fake_order(id="ord-retry")
        client.submit_order.side_effect = [ConnectionError("timeout"), order]
        client.get_order_by_client_id.side_effect = self._api_error(404, message="not found")
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-retry"
        assert client.submit_order.call_count == 2
        assert client.get_order_by_client_id.call_count == 1

    def test_submit_429_consults_client_id_before_each_retry(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """429 on submit: lookup → sleep → lookup again → resubmit (bounded)."""
        sleeps: list[float] = []
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", sleeps.append)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        client.submit_order.side_effect = self._api_error(429, message="slow")
        client.get_order_by_client_id.side_effect = self._api_error(404, message="missing")
        with pytest.raises(BrokerRateLimited):
            adapter.submit_order(_make_request())
        # 3 submits; per failed attempt with remaining budget: 2 lookups (pre+post sleep);
        # final exhaustion: 1 lookup → 2+2+1 = 5.
        assert client.submit_order.call_count == 3
        assert client.get_order_by_client_id.call_count == 5
        assert len(sleeps) == 2
        assert all(
            call.args == ("intent-1",) for call in client.get_order_by_client_id.call_args_list
        )

    def test_submit_429_recovers_without_duplicate_submit(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", lambda _s: None)
        client.submit_order.side_effect = self._api_error(429, message="slow")
        client.get_order_by_client_id.return_value = _fake_order(id="ord-from-429")
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-from-429"
        assert client.submit_order.call_count == 1
        assert client.get_order_by_client_id.call_count == 1

    def test_submit_429_recovers_on_post_backoff_lookup(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Late-indexed order found on the post-sleep re-lookup — no second submit."""
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", lambda _s: None)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        client.submit_order.side_effect = self._api_error(429, message="slow")
        client.get_order_by_client_id.side_effect = [
            self._api_error(404, message="missing"),
            _fake_order(id="ord-late"),
        ]
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-late"
        assert client.submit_order.call_count == 1
        assert client.get_order_by_client_id.call_count == 2

    def test_recovery_lookup_500_does_not_resubmit(
        self, adapter: AlpacaAdapter, client: MagicMock
    ) -> None:
        """Non-404 lookup failure through real ``_map_exception`` must not resubmit."""
        client.submit_order.side_effect = ConnectionError("boom")
        client.get_order_by_client_id.side_effect = self._api_error(500, message="upstream")
        with pytest.raises(BrokerTransportError):
            adapter.submit_order(_make_request())
        assert client.submit_order.call_count == 1
        assert client.get_order_by_client_id.call_count == 1

    def test_lookup_429_exhausted_does_not_resubmit(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", lambda _s: None)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        client.submit_order.side_effect = ConnectionError("boom")
        client.get_order_by_client_id.side_effect = self._api_error(429, message="slow")
        with pytest.raises(BrokerRateLimited):
            adapter.submit_order(_make_request())
        assert client.submit_order.call_count == 1
        # Lookup ``_call`` retries 429 internally (3 tries), never authorizes resubmit.
        assert client.get_order_by_client_id.call_count == 3

    def test_lookup_429_then_404_authorizes_one_resubmit(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", lambda _s: None)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        order = _fake_order(id="ord-after-lookup-429")
        client.submit_order.side_effect = [ConnectionError("boom"), order]
        client.get_order_by_client_id.side_effect = [
            self._api_error(429, message="slow"),
            self._api_error(404, message="missing"),
        ]
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-after-lookup-429"
        assert client.submit_order.call_count == 2
        assert client.get_order_by_client_id.call_count == 2

    def test_post_exhaustion_lookup_returns_found_ack(
        self, adapter: AlpacaAdapter, client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Final attempt fails; exhaustion lookup finds the order — return ack, no raise."""
        monkeypatch.setattr("digiquant.brokers.alpaca.time.sleep", lambda _s: None)
        monkeypatch.setattr("digiquant.brokers.alpaca.random.uniform", lambda _a, _b: 0.0)
        client.submit_order.side_effect = self._api_error(429, message="slow")
        # Attempts 0–1: pre-sleep 404 + post-sleep 404 (×2); attempt 2: found.
        client.get_order_by_client_id.side_effect = [
            self._api_error(404, message="missing"),
            self._api_error(404, message="missing"),
            self._api_error(404, message="missing"),
            self._api_error(404, message="missing"),
            _fake_order(id="ord-at-exhaustion"),
        ]
        ack = adapter.submit_order(_make_request())
        assert ack.external_order_id == "ord-at-exhaustion"
        assert client.submit_order.call_count == 3
        assert client.get_order_by_client_id.call_count == 5

    def test_422_no_retry_no_lookup(self, adapter: AlpacaAdapter, client: MagicMock) -> None:
        client.submit_order.side_effect = self._api_error(422, message="invalid")
        with pytest.raises(BrokerOrderRejected):
            adapter.submit_order(_make_request())
        assert client.submit_order.call_count == 1
        client.get_order_by_client_id.assert_not_called()

    @pytest.mark.parametrize(
        ("submit_side", "lookup_side", "expect_submits", "expect_lookups"),
        [
            ("auth", None, 1, 0),
            ("transport", "auth", 1, 1),
            ("transport_then_auth", "404", 2, 1),
        ],
        ids=["401-on-first-submit", "401-on-lookup", "401-on-retry-after-404"],
    )
    def test_auth_error_mid_loop_stops(
        self,
        adapter: AlpacaAdapter,
        client: MagicMock,
        submit_side: str,
        lookup_side: str | None,
        expect_submits: int,
        expect_lookups: int,
    ) -> None:
        auth_err = self._api_error(401, message="unauthorized")
        if submit_side == "auth":
            client.submit_order.side_effect = auth_err
        elif submit_side == "transport":
            client.submit_order.side_effect = ConnectionError("boom")
        else:
            client.submit_order.side_effect = [ConnectionError("boom"), auth_err]
        if lookup_side == "auth":
            client.get_order_by_client_id.side_effect = auth_err
        elif lookup_side == "404":
            client.get_order_by_client_id.side_effect = self._api_error(404, message="missing")
        with pytest.raises(BrokerAuthError):
            adapter.submit_order(_make_request())
        assert client.submit_order.call_count == expect_submits
        assert client.get_order_by_client_id.call_count == expect_lookups


class TestLazyImportWithoutAlpacaPy:
    def test_brokers_package_imports(self) -> None:
        import digiquant.brokers as brokers

        assert hasattr(brokers, "BrokerAdapter")
        assert hasattr(brokers, "BrokerOrderRequest")

    def test_alpaca_module_loads_when_sdk_import_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sys.modules / __import__ patching — proves import works without alpaca-py.

        Strategy: block ``alpaca*`` imports, drop the cached adapter module, reload.
        Construction must then raise ImportError pointing at the brokers-alpaca extra.
        Restores a clean module before leaving so later tests still see the real SDK.
        """
        real_import = builtins.__import__

        def _blocked(
            name: str,
            globals: dict[str, object] | None = None,
            locals: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "alpaca" or name.startswith("alpaca."):
                raise ImportError("simulated missing alpaca-py")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _blocked)
        for key in list(sys.modules):
            if key == "digiquant.brokers.alpaca" or key == "alpaca" or key.startswith("alpaca."):
                del sys.modules[key]

        try:
            mod = importlib.import_module("digiquant.brokers.alpaca")
            assert mod._TradingClient is None
            with pytest.raises(ImportError, match=r"digiquant\[brokers-alpaca\]"):
                mod.AlpacaAdapter(auth=mod.ApiKeyAuth(key_id="k", secret="s"))
        finally:
            monkeypatch.undo()
            for key in list(sys.modules):
                if key == "digiquant.brokers.alpaca":
                    del sys.modules[key]
            importlib.import_module("digiquant.brokers.alpaca")
