"""Keyless ``GET /bars`` for dashboard charts (#4880; feeds #4879 Vela wiring).

Offline: a ``httpx.MockTransport``-backed ``GloomberbClient`` is injected via
the ``digiquant.bars._build_gloomberb_client`` seam — never live HTTP. No
Nautilus import here, so this module also runs in the plain digiquant lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from digifetch import HttpFetcher, RateLimiter, RetryPolicy

pytestmark = pytest.mark.unit

from digiquant.bars import DEFAULT_RANGE_BY_TIMEFRAME  # noqa: E402
from digiquant.data.gloomberb import GloomberbClient  # noqa: E402
from digiquant.server import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _daily_bars(n: int) -> list[dict[str, Any]]:
    return [
        {
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000.0 + i,
        }
        for i in range(n)
    ]


def _history_response(bars: list[dict[str, Any]], **extra: Any) -> httpx.Response:
    payload = {"status": "success", "data": bars, "currency": "USD", **extra}
    return httpx.Response(200, json=payload)


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler: Any) -> dict[str, Any]:
    """Patch the bars client seam with a MockTransport client; return call log."""
    import digiquant.bars as bars_mod

    seen: dict[str, Any] = {"calls": 0, "urls": []}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        seen["urls"].append(str(request.url))
        return handler(request)

    fetcher = HttpFetcher(
        transport=httpx.MockTransport(_handler),
        allowed_hosts=["api.gloom.sh"],
    )
    client = GloomberbClient(
        fetcher=fetcher,
        rate_limiter=RateLimiter(0),
        retry_policy=RetryPolicy(attempts=1),
        sleep=lambda _s: None,
    )
    monkeypatch.setattr(bars_mod, "_build_gloomberb_client", lambda: client)
    return seen


@pytest.fixture
def unauth_client() -> TestClient:
    client = TestClient(app)
    assert "Authorization" not in client.headers
    return client


@pytest.fixture
def ten_bars(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    bars = _daily_bars(10)
    return _mock_client(monkeypatch, lambda _req: _history_response(bars))


class TestKeylessContract:
    def test_200_without_authorization_header(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        r = unauth_client.get("/bars", params={"symbol": "AAPL"})
        assert r.status_code == 200
        assert ten_bars["calls"] == 1

    def test_response_shape(self, unauth_client: TestClient, ten_bars: dict[str, Any]) -> None:
        data = unauth_client.get(
            "/bars", params={"symbol": "AAPL", "timeframe": "1d", "limit": 10}
        ).json()
        assert data["symbol"] == "AAPL"
        assert data["timeframe"] == "1d"
        assert data["limit"] == 10
        assert data["count"] == 10
        assert data["source"] == "gloomberb"
        assert isinstance(data["stale"], bool)
        assert data["delay_note"] is None or isinstance(data["delay_note"], str)
        assert len(data["bars"]) == 10
        bar = data["bars"][0]
        assert set(bar) == {"timestamp", "open", "high", "low", "close", "volume"}
        assert bar["close"] == pytest.approx(100.5)

    def test_carries_no_performance_claims(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        data = unauth_client.get("/bars", params={"symbol": "AAPL"}).json()
        for forbidden in ("sharpe", "sharpe_ratio", "pnl", "total_pnl", "drawdown"):
            assert forbidden not in data

    def test_limit_tail_slices_newest(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        data = unauth_client.get("/bars", params={"symbol": "AAPL", "limit": 3}).json()
        assert data["count"] == 3
        assert [b["close"] for b in data["bars"]] == pytest.approx([107.5, 108.5, 109.5])

    def test_default_limit_bounds_upstream(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(monkeypatch, lambda _req: _history_response(_daily_bars(200)))
        data = unauth_client.get("/bars", params={"symbol": "AAPL"}).json()
        assert data["limit"] == 120
        assert data["count"] == 120

    def test_intraday_timeframe_sends_contract_range(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _mock_client(
            monkeypatch,
            lambda _req: _history_response(_daily_bars(5), providerMeta={"provider": "yahoo"}),
        )
        r = unauth_client.get("/bars", params={"symbol": "AAPL", "timeframe": "1h", "limit": 5})
        assert r.status_code == 200
        assert r.json()["timeframe"] == "1h"
        url = seen["urls"][0]
        assert "interval=1h" in url
        assert f"rangeKey={DEFAULT_RANGE_BY_TIMEFRAME['1h']}" in url


class TestValidation:
    def test_missing_symbol_is_422(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        r = unauth_client.get("/bars")
        assert r.status_code == 422
        assert ten_bars["calls"] == 0

    def test_unknown_timeframe_is_422_without_request(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        r = unauth_client.get("/bars", params={"symbol": "AAPL", "timeframe": "5y"})
        assert r.status_code == 422
        assert ten_bars["calls"] == 0

    def test_limit_bounds_are_422_without_request(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        for bad in (0, 501):
            r = unauth_client.get("/bars", params={"symbol": "AAPL", "limit": bad})
            assert r.status_code == 422
        assert ten_bars["calls"] == 0

    def test_oversize_symbol_is_422_without_request(
        self, unauth_client: TestClient, ten_bars: dict[str, Any]
    ) -> None:
        r = unauth_client.get("/bars", params={"symbol": "X" * 33})
        assert r.status_code == 422
        assert ten_bars["calls"] == 0


class TestUpstreamMapping:
    def test_not_found_maps_to_404(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(
            monkeypatch,
            lambda _req: httpx.Response(200, json={"status": "empty", "data": None}),
        )
        r = unauth_client.get("/bars", params={"symbol": "NOPE"})
        assert r.status_code == 404

    def test_upstream_error_maps_to_502(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(
            monkeypatch,
            lambda _req: httpx.Response(200, json={"status": "fatal_error", "data": None}),
        )
        r = unauth_client.get("/bars", params={"symbol": "AAPL"})
        assert r.status_code == 502

    def test_rate_limited_maps_to_429(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_client(
            monkeypatch,
            lambda _req: httpx.Response(
                429, headers={"Retry-After": "999"}, json={"message": "slow down"}
            ),
        )
        r = unauth_client.get("/bars", params={"symbol": "AAPL"})
        assert r.status_code == 429

    def test_transport_failure_maps_to_502_without_crash(
        self, unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import digiquant.bars as bars_mod

        class _Boom:
            def price_history(self, _req: Any) -> Any:
                raise TimeoutError("upstream hung")

        monkeypatch.setattr(bars_mod, "_build_gloomberb_client", lambda: _Boom())
        r = unauth_client.get("/bars", params={"symbol": "AAPL"})
        assert r.status_code == 502


class TestFetchBarsUnit:
    def test_direct_call_returns_contract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_client(monkeypatch, lambda _req: _history_response(_daily_bars(4)))
        import digiquant.bars as bars_mod

        result = bars_mod.fetch_bars("aapl", "1d", 2)
        assert result.symbol == "AAPL"
        assert result.count == 2
        assert [b.close for b in result.bars] == pytest.approx([102.5, 103.5])

    def test_direct_call_rejects_bad_timeframe_without_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import digiquant.bars as bars_mod

        seen = _mock_client(monkeypatch, lambda _req: _history_response(_daily_bars(1)))
        with pytest.raises(bars_mod.BarsError) as exc:
            bars_mod.fetch_bars("AAPL", "9m", 10)
        assert exc.value.status_code == 422
        assert seen["calls"] == 0
