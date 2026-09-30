"""Gateway tests: fake MCP bridge + fake market upstream, no network."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))
import live_gateway as lg

ORIGIN = "http://localhost:3910"


class FakeBridge:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, args: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.calls.append((tool, args))
        r = self.responses[tool]
        if isinstance(r, Exception):
            raise r
        return r

    async def close(self) -> None:
        pass


def _client(responses: dict[str, Any], market: httpx.MockTransport | None = None):
    bridge = FakeBridge(responses)
    transport = market or httpx.MockTransport(lambda req: httpx.Response(200, json={"rows": []}))
    gw = lg.Gateway(bridge=bridge, http=httpx.AsyncClient(transport=transport))
    return TestClient(lg.build_app(gw)), bridge, gw


QUOTE = {
    "fetched_at": "2026-09-30T21:00:00Z",
    "data": {
        "quote": {"symbol": "AAPL", "price": 333.0, "change_percent": 1.1, "name": "Apple Inc."}
    },
    "attribution": "Sourced from Gloomberb",
    "delay_notice": "Data delayed up to 15 minutes",
}


def test_quote_envelope_and_cache() -> None:
    c, bridge, _ = _client({"digifetch_quote": QUOTE})
    r = c.get("/v1/probe/quote?symbol=aapl")
    body = r.json()
    assert r.status_code == 200 and body["ok"] and not body["cached"]
    assert body["args"] == {"symbol": "AAPL"} and body["tool"] == "digifetch_quote"
    assert body["attribution"] == ["Sourced from Gloomberb"]
    assert body["delayNote"] == "Data delayed up to 15 minutes"
    assert body["data"]["price"] == 333.0 and body["data"]["changePct"] == 1.1
    assert c.get("/v1/probe/quote?symbol=AAPL").json()["cached"] is True
    assert len(bridge.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "/v1/probe/quote?symbol=AA%20PL",
        "/v1/probe/quote?symbol=",
        "/v1/probe/quote?symbol=AAPL&extra=1",
        "/v1/probe/history?symbol=AAPL&range=1m",
        "/v1/probe/luxalgoTrackers?dataset=../x",
    ],
)
def test_invalid_params_never_reach_tool(url: str) -> None:
    c, bridge, _ = _client({})
    r = c.get(url)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_input"
    assert bridge.calls == []


def test_unknown_probe_and_no_passthrough() -> None:
    c, bridge, _ = _client({})
    assert c.get("/v1/probe/digifetch_holders").status_code == 404
    assert bridge.calls == []
    assert not any("holders" in p.tool or "backtest" in p.tool for p in lg.PROBES.values())


def test_limit_clamped() -> None:
    c, bridge, _ = _client({"digifetch_news": {"data": {"items": []}, "attribution": "x"}})
    c.get("/v1/probe/news?limit=9999")
    assert bridge.calls[0][1]["limit"] == 20


def test_data_code_error_is_not_ok() -> None:
    c, _, _ = _client(
        {
            "digifetch_quote": {
                "data": {"code": "auth_required", "message": "sign in", "retryable": False}
            }
        }
    )
    body = c.get("/v1/probe/quote?symbol=AAPL").json()
    assert body["ok"] is False and body["error"]["code"] == "auth_required" and body["data"] is None


def test_transport_error_502() -> None:
    c, _, _ = _client({"digifetch_quote": lg.ToolError("timeout", "slow")})
    r = c.get("/v1/probe/quote?symbol=AAPL")
    assert r.status_code == 502 and r.json()["error"]["code"] == "timeout"


def test_predictions_filter_and_honest_attribution() -> None:
    markets = [
        {"title": "old", "yes_prob": 0.5, "volume_24h": 9, "ends_at": "2020-01-01T00:00:00Z"},
        {"title": "zero", "yes_prob": 0.0, "volume_24h": 99, "ends_at": "2099-01-01T00:00:00Z"},
        {"title": "small", "yes_prob": 0.4, "volume_24h": 1, "ends_at": "2099-01-01T00:00:00Z"},
        {"title": "big", "yes_prob": 0.6, "volume_24h": 50, "ends_at": "2099-01-01T00:00:00Z"},
    ]
    c, _, _ = _client({"digifetch_prediction_markets": {"data": {"markets": markets}}})
    body = c.get("/v1/probe/predictions").json()
    assert [m["title"] for m in body["data"]["markets"]] == ["big", "small"]
    assert "Polymarket" in body["attribution"][0] and body["delayNote"]


def test_empty_is_honest() -> None:
    c, _, _ = _client({"digifetch_congress_trades": {"data": {"trades": []}, "attribution": "a"}})
    body = c.get("/v1/probe/congress").json()
    assert body["ok"] and body["empty"] and body["data"] == {"trades": []}


def test_luxalgo_keeps_license_note_and_drops_nothing_sensitive() -> None:
    lux = {
        "data": {
            "results": [
                {
                    "kind": "concept",
                    "slug": "rsi",
                    "name": "RSI",
                    "family": "momentum",
                    "source_code": "SECRET",
                }
            ]
        },
        "attribution": "Sourced from LuxAlgo Library",
        "license_note": "Research reference only",
    }
    c, _, _ = _client({"luxalgo_library_search": lux})
    r = c.get("/v1/probe/luxalgoSearch?query=rsi")
    assert r.json()["attribution"] == ["Sourced from LuxAlgo Library", "Research reference only"]
    assert "SECRET" not in r.text


def test_cors_allowlist_and_forbidden_origin() -> None:
    c, _, _ = _client({"digifetch_quote": QUOTE})
    ok = c.get("/v1/probe/quote?symbol=AAPL", headers={"Origin": ORIGIN})
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    bad = c.get("/v1/probe/quote?symbol=AAPL", headers={"Origin": "http://localhost:3005"})
    assert bad.status_code == 403


def test_rate_limit() -> None:
    c, _, _ = _client({"digifetch_quote": QUOTE})
    codes = [c.get("/v1/probe/quote?symbol=AAPL").status_code for _ in range(lg.RATE_LIMIT + 2)]
    assert codes.count(429) == 2


def test_market_proxy_passthrough_and_validation() -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "as_of": "2026-09-29",
                "rows": [{"date": "2026-09-29", "ticker": "SPY", "close": 1.0}],
            },
        )

    c, _, _ = _client({}, httpx.MockTransport(handler))
    r = c.get("/v1/market/closes?tickers=SPY,QQQ&from=2026-09-01")
    assert r.status_code == 200 and r.json()["rows"][0]["ticker"] == "SPY"
    assert seen[0].startswith("https://graph.digithings.ai/v1/market/closes?")
    c.get("/v1/market/closes?tickers=SPY,QQQ&from=2026-09-01")
    assert len(seen) == 1  # cached
    assert c.get("/v1/market/closes?tickers=bad%20one").status_code == 400
    assert c.get("/v1/market/closes?tickers=" + ",".join(["A"] * 26)).status_code == 400
    assert c.get("/v1/market/closes?tickers=SPY&from=2026-13-40").status_code == 400


def test_market_upstream_failure_502() -> None:
    c, _, _ = _client({}, httpx.MockTransport(lambda req: httpx.Response(500, text="boom")))
    assert c.get("/v1/market/tickers").status_code == 502


def test_scrubbed_env_has_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLOOMBERB_SESSION_COOKIE", "x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    assert set(lg.scrubbed_env()) <= {"PATH", "HOME", "LANG", "PYTHONPATH"}


def test_origins_from_env_accepts_loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DQ_GATEWAY_ORIGINS",
        "http://localhost:3910,http://127.0.0.1:3910,http://[::1]:3910",
    )
    assert lg.origins_from_env() == (
        "http://localhost:3910",
        "http://127.0.0.1:3910",
        "http://[::1]:3910",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost:3910",
        "http://0.0.0.0:3910",
        "http://192.168.1.10:3910",
        "http://digiquant.io",
        "http://localhost:3910/path",
        "http://user@localhost:3910",
    ],
)
def test_origins_from_env_rejects_nonlocal_or_malformed_values(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    monkeypatch.setenv("DQ_GATEWAY_ORIGINS", origin)
    with pytest.raises(ValueError, match="loopback HTTP origins"):
        lg.origins_from_env()


@pytest.mark.parametrize("raw", ["0", "65536", "abc"])
def test_port_from_env_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("DQ_GATEWAY_PORT", raw)
    with pytest.raises(ValueError, match="DQ_GATEWAY_PORT"):
        lg.port_from_env()


def test_catalog_lists_probes() -> None:
    c, _, _ = _client({})
    ids = {p["id"] for p in c.get("/v1/catalog").json()["probes"]}
    assert {"quote", "history", "market", "luxalgoSearch"} <= ids


def test_parse_result_unwraps_and_raises() -> None:
    class R:
        structuredContent = {"result": '{"a": 1}'}
        content: list[Any] = []
        isError = False

    assert lg._parse_result(R()) == {"a": 1}
    assert asyncio.iscoroutinefunction(lg.StdioBridge.call)
