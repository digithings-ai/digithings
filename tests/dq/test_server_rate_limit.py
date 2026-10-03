"""digiquant HTTP rate limit: trusted-proxy XFF, per-path budgets, request args."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from digiquant import server

pytestmark = pytest.mark.unit


def _request(
    client_host: str = "203.0.113.9",
    *,
    xff: str | None = None,
    xff_lines: list[str] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff_lines is not None:
        headers.extend((b"x-forwarded-for", line.encode()) for line in xff_lines)
    elif xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/run_backtest",
        "headers": headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clean_limiter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DIGI_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    server._trusted_proxy_cache.clear()
    yield
    server._rl_windows.clear()


def test_untrusted_peer_ignores_xff_and_a_spoofed_testclient_hop() -> None:
    req = _request("203.0.113.9", xff="testclient, 198.51.100.8")
    assert server._client_ip(req) == "203.0.113.9"
    assert server._rl_check(req, max_req=1, window=60, path="/bars") is None
    blocked = server._rl_check(req, max_req=1, window=60, path="/bars")
    assert blocked is not None
    assert blocked.status_code == 429


def test_trusted_proxy_uses_the_rightmost_untrusted_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
    req = _request("10.0.0.1", xff="203.0.113.250, 198.51.100.42")
    assert server._client_ip(req) == "198.51.100.42"


def test_unparseable_hop_does_not_walk_into_the_spoofed_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
    req = _request("10.0.0.1", xff="198.51.100.42, testclient")
    assert server._client_ip(req) == "10.0.0.1"


def test_socket_testclient_stays_exempt() -> None:
    req = _request("testclient", xff="203.0.113.9")
    assert server._rl_check(req, max_req=1, window=60, path="/bars") is None
    assert server._rl_check(req, max_req=1, window=60, path="/bars") is None


def test_path_budgets_are_independent() -> None:
    req = _request("203.0.113.9")
    assert server._rl_check(req, max_req=1, window=60, path="/bars") is None
    assert server._rl_check(req, max_req=1, window=60, path="/bars") is not None
    assert server._rl_check(req, max_req=1, window=60, path="/run_backtest") is None


def test_ipv6_clients_share_a_64_prefix_bucket() -> None:
    first = _request("2001:db8:1:2::1")
    second = _request("2001:db8:1:2::abcd")
    other = _request("2001:db8:9:9::1")
    assert server._rl_check(first, max_req=1, window=60, path="/bars") is None
    assert server._rl_check(second, max_req=1, window=60, path="/bars") is not None
    assert server._rl_check(other, max_req=1, window=60, path="/bars") is None


def test_ipv4_mapped_ipv6_buckets_as_ipv4() -> None:
    mapped = _request("::ffff:203.0.113.5")
    plain = _request("203.0.113.5")
    assert server._rl_check(mapped, max_req=1, window=60, path="/bars") is None
    assert server._rl_check(plain, max_req=1, window=60, path="/bars") is not None


def test_optimize_rejects_non_positive_trials() -> None:
    with pytest.raises(ValidationError):
        server.OptimizeRequest(strategy_name="ema", symbols=["SPY"], n_trials=0)


def test_explicit_zero_trials_is_not_replaced_with_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(**kwargs: object) -> None:
        raise AssertionError(kwargs)

    monkeypatch.setattr(server, "service_run_optimize", _boom)
    out = server.v1_orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digiquant_run_optimize",
            arguments={
                "strategy_name": "ema",
                "symbols": ["SPY"],
                "data_path": "x.csv",
                "n_trials": 0,
            },
        )
    )
    assert out["ok"] is False
    assert "n_trials" in out["error"]


def test_string_false_does_not_enable_pipeline_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _capture(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {}

    monkeypatch.setattr(server, "run_quant_workflow", _capture)
    out = server.v1_orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digiquant_run_pipeline",
            arguments={
                "strategy_name": "ema",
                "symbols": ["SPY"],
                "data_path": "x.csv",
                "run_optimize": "false",
                "run_export": "false",
                "full_tearsheet": "false",
            },
        )
    )
    assert out["ok"] is True
    assert captured["run_optimize"] is False
    assert captured["run_export"] is False


def test_string_false_disables_full_tearsheet(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> object:
        captured.update(kwargs)
        return server.BacktestResult(
            run_id="r",
            strategy_name="ema",
            start_time="2024-01-01T00:00:00",
            end_time="2024-02-01T00:00:00",
        )

    monkeypatch.setattr(server, "service_run_backtest", _capture)
    out = server.v1_orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digiquant_run_backtest",
            arguments={
                "strategy_name": "ema",
                "symbols": ["SPY"],
                "data_path": "x.csv",
                "full_tearsheet": "false",
            },
        )
    )
    assert out["ok"] is True
    assert captured["full_tearsheet"] is False
