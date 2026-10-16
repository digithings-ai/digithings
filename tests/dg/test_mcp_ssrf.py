"""Connect-time DNS validation for remote MCP servers (#3879).

``is_allowed_mcp_url`` only inspects the literal hostname. These tests pin the
new behaviour: the hostname is resolved at connect time, every A/AAAA record is
validated against the private/loopback/link-local/metadata blocklist, the
validated IP is the one actually connected to, and DNS failure fails closed.

The resolver is always monkeypatched — no live DNS in unit tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import time
from typing import Any

import httpcore
import pytest
from digigraph.orchestration import mcp_client
from digigraph.orchestration.mcp_client import (
    McpAddressRejected,
    _mcp_http_client_factory,
    _resolve_and_validate,
    _SsrfSafeAsyncHTTPTransport,
    _SsrfSafeNetworkBackend,
)

_ALLOWLIST_ENV = "DIGIGRAPH_MCP_PRIVATE_HOST_ALLOWLIST"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _resolver_returns(*ips: str):
    def _fake(host: str, port: int) -> list[str]:
        return list(ips)

    return _fake


class _RecordingBackend:
    """Inner httpcore backend that records hosts and can fail selected ones."""

    def __init__(
        self, fail_hosts: tuple[str, ...] = (), timeout_hosts: tuple[str, ...] = ()
    ) -> None:
        self.hosts: list[str] = []
        self._fail = set(fail_hosts)
        self._timeout = set(timeout_hosts)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> object:
        self.hosts.append(host)
        if host in self._fail:
            raise httpcore.ConnectError(f"cannot reach {host}")
        if host in self._timeout:
            raise httpcore.ConnectTimeout(f"timeout reaching {host}")
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
@pytest.mark.parametrize("ip", ["100.64.0.1", "100.127.255.255", "::ffff:100.64.0.1"])
def test_cgnat_resolved_address_is_refused(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    # 100.64.0.0/10 is neither private nor global (is_global False) — a literal
    # or resolved CGNAT address must still be refused (F1).
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns(ip))
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("cgnat.example.com", 443))


@pytest.mark.unit
def test_cgnat_literal_url_is_refused() -> None:
    assert mcp_client.is_allowed_mcp_url("http://100.64.0.1/") is False
    assert mcp_client.is_allowed_mcp_url("http://[::ffff:100.64.0.1]/") is False


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
    assert _run(_resolve_and_validate("mcp.datatap.example", 443)) == ["93.184.216.34"]


@pytest.mark.unit
def test_dns_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(host: str, port: int) -> list[str]:
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _boom)
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("evil.example.com", 443))


@pytest.mark.unit
def test_dns_resolution_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow(host: str, port: int) -> list[str]:
        time.sleep(0.5)
        return ["93.184.216.34"]

    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _slow)
    monkeypatch.setattr(mcp_client, "_DNS_RESOLVE_TIMEOUT_S", 0.05)
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("slow.example.com", 443))


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
    monkeypatch.delenv(_ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("172.18.0.5"))
    assert _run(_resolve_and_validate("datatap-mcp", 8080)) == ["172.18.0.5"]


@pytest.mark.unit
def test_private_host_allowlist_restricts_dotless_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("172.18.0.5"))
    monkeypatch.setenv(_ALLOWLIST_ENV, "other-svc")
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("datatap-mcp", 8080))
    assert _run(_resolve_and_validate("other-svc", 8080)) == ["172.18.0.5"]


@pytest.mark.unit
def test_private_host_allowlist_does_not_readmit_cgnat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("100.64.0.1"))
    monkeypatch.setenv(_ALLOWLIST_ENV, "datatap-mcp")
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("datatap-mcp", 8080))


@pytest.mark.unit
def test_docker_service_name_still_blocks_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("127.0.0.1"))
    with pytest.raises(McpAddressRejected):
        _run(_resolve_and_validate("datatap-mcp", 8080))


@pytest.mark.unit
def test_allowlisted_docker_name_still_blocks_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("127.0.0.1"))
    monkeypatch.setenv(_ALLOWLIST_ENV, "datatap-mcp")
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
def test_dual_stack_falls_back_to_next_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_resolve_host_ips",
        _resolver_returns("2606:4700:4700::1111", "93.184.216.34"),
    )
    inner = _RecordingBackend(fail_hosts=("2606:4700:4700::1111",))
    backend = _SsrfSafeNetworkBackend(inner=inner)
    _run(backend.connect_tcp("dual.example.com", 443))
    assert inner.hosts == ["2606:4700:4700::1111", "93.184.216.34"]


@pytest.mark.unit
def test_dual_stack_falls_back_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_resolve_host_ips",
        _resolver_returns("2606:4700:4700::1111", "93.184.216.34"),
    )
    inner = _RecordingBackend(timeout_hosts=("2606:4700:4700::1111",))
    backend = _SsrfSafeNetworkBackend(inner=inner)
    _run(backend.connect_tcp("dual.example.com", 443))
    assert inner.hosts == ["2606:4700:4700::1111", "93.184.216.34"]


@pytest.mark.unit
def test_dual_stack_all_fail_raises_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_resolve_host_ips",
        _resolver_returns("2606:4700:4700::1111", "93.184.216.34"),
    )
    inner = _RecordingBackend(fail_hosts=("2606:4700:4700::1111", "93.184.216.34"))
    backend = _SsrfSafeNetworkBackend(inner=inner)
    with pytest.raises(httpcore.ConnectError):
        _run(backend.connect_tcp("dual.example.com", 443))


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
def test_factory_client_refuses_loopback_resolution_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_client, "_resolve_host_ips", _resolver_returns("127.0.0.1"))

    async def _attempt() -> None:
        client = _mcp_http_client_factory()
        try:
            with pytest.raises(McpAddressRejected):
                await client.get("http://evil.example.com/mcp")
        finally:
            await client.aclose()

    _run(_attempt())


class _WireProbe(Exception):
    """Raised by the fake streamable client after recording its kwargs."""


def _fake_streamable(calls: list[dict[str, Any]]):
    @contextlib.asynccontextmanager
    async def _client(url: str, **kwargs: Any):
        calls.append({"url": url, **kwargs})
        raise _WireProbe
        yield  # pragma: no cover - unreachable

    return _client


@pytest.mark.unit
def test_list_tools_async_passes_ssrf_http_client_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", _fake_streamable(calls))
    with pytest.raises(_WireProbe):
        _run(mcp_client._list_tools_async({"id": "s", "url": "https://mcp.example/mcp"}))
    assert calls[0]["httpx_client_factory"] is mcp_client._mcp_http_client_factory


@pytest.mark.unit
def test_call_tool_async_passes_ssrf_http_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", _fake_streamable(calls))
    with pytest.raises(_WireProbe):
        _run(mcp_client._call_tool_async({"id": "s", "url": "https://mcp.example/mcp"}, "echo", {}))
    assert calls[0]["httpx_client_factory"] is mcp_client._mcp_http_client_factory


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
