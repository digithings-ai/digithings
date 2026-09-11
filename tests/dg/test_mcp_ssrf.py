"""Connect-time DNS validation for remote MCP servers (#3879).

``is_allowed_mcp_url`` only inspects the literal hostname. These tests pin the
new behaviour: the hostname is resolved at connect time, every A/AAAA record is
validated against the private/loopback/link-local/metadata blocklist, the
validated IP is the one actually connected to, and DNS failure fails closed.

The resolver is always monkeypatched — no live DNS in unit tests.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import pytest
from digigraph.orchestration import mcp_client
from digigraph.orchestration.mcp_client import (
    McpAddressRejected,
    _mcp_http_client_factory,
    _resolve_and_validate,
    _SsrfSafeAsyncHTTPTransport,
    _SsrfSafeNetworkBackend,
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _resolver_returns(*ips: str):
    def _fake(host: str, port: int) -> list[str]:
        return list(ips)

    return _fake


class _RecordingBackend:
    """Inner httpcore backend that records the host it was asked to connect to."""

    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> object:
        self.hosts.append(host)
        return object()

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Any = None
    ) -> object:  # pragma: no cover - not exercised
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:  # pragma: no cover - not exercised
        raise NotImplementedError


@pytest.mark.unit
@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.10",
        "172.16.0.9",
        "169.254.169.254",
        "100.100.100.200",
        "::1",
        "fd12:3456::1",
    ],
)
def test_fqdn_resolving_to_blocked_address_is_refused(
    monkeypatch: pytest.MonkeyPatch, ip: str
) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns(ip))
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("evil.example.com", 443))


@pytest.mark.unit
def test_multi_a_record_with_one_private_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_resolve_host_ips",
        _resolver_returns("93.184.216.34", "10.0.0.5"),
    )
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("mixed.example.com", 443))


@pytest.mark.unit
def test_public_fqdn_is_allowed_and_returns_resolved_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("93.184.216.34"))
    assert _run(_resolve_and_validate("mcp.datatap.example", 443)) == "93.184.216.34"


@pytest.mark.unit
def test_dns_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(host: str, port: int) -> list[str]:
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _boom)
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("evil.example.com", 443))


@pytest.mark.unit
def test_empty_resolution_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns())
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("empty.example.com", 443))


@pytest.mark.unit
def test_literal_blocked_ip_is_refused_without_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(host: str, port: int) -> list[str]:  # pragma: no cover - must not run
        raise AssertionError("resolver must not be called for a literal IP")

    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _boom)
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("169.254.169.254", 80))


@pytest.mark.unit
def test_docker_service_name_may_resolve_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bare label (no dot) is container-internal service discovery, not public
    # DNS, so Docker's RFC1918 network is expected and stays allowed.
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("172.18.0.5"))
    assert _run(_resolve_and_validate("datatap-mcp", 8080)) == "172.18.0.5"


@pytest.mark.unit
def test_docker_service_name_still_blocks_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("127.0.0.1"))
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("datatap-mcp", 8080))


@pytest.mark.unit
def test_connect_pins_the_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("93.184.216.34"))
    inner = _RecordingBackend()
    backend = _SsrfSafeNetworkBackend(inner=inner)
    _run(backend.connect_tcp("evil.example.com", 443))
    assert inner.hosts == ["93.184.216.34"]


@pytest.mark.unit
def test_connect_never_reaches_inner_backend_when_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("10.0.0.5"))
    inner = _RecordingBackend()
    backend = _SsrfSafeNetworkBackend(inner=inner)
    with pytest.raises(McpAddressRejected):
        _run(backend.connect_tcp("evil.example.com", 443))
    assert inner.hosts == []


@pytest.mark.unit
def test_rebinding_second_answer_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _flip(host: str, port: int) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["127.0.0.1"]

    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _flip)
    inner = _RecordingBackend()
    backend = _SsrfSafeNetworkBackend(inner=inner)
    _run(backend.connect_tcp("rebind.example.com", 443))
    # Resolved exactly once, and the socket went to the validated public IP —
    # a later DNS answer cannot redirect the connection.
    assert calls == ["rebind.example.com"]
    assert inner.hosts == ["93.184.216.34"]


@pytest.mark.unit
def test_http_client_factory_wires_ssrf_safe_transport() -> None:
    client = _mcp_http_client_factory()
    try:
        assert isinstance(client._transport, _SsrfSafeAsyncHTTPTransport)
        assert isinstance(client._transport._network_backend, _SsrfSafeNetworkBackend)
    finally:
        _run(client.aclose())


@pytest.mark.unit
def test_list_tools_blocking_surfaces_rejection(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _boom(server: dict[str, str]) -> list[dict[str, Any]]:
        raise McpAddressRejected("MCP host 'evil.example.com' resolved to blocked address")

    monkeypatch.setattr(mcp_client, "_list_tools_async", _boom)
    with caplog.at_level("WARNING", logger=mcp_client.__name__):
        out = mcp_client._list_tools_blocking({"id": "evil", "url": "https://evil.example.com/mcp"})
    assert out == []
    assert any("blocked address" in rec.message for rec in caplog.records)
