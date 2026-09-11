"""Remote MCP tool proxy for extra servers declared by a trusted BFF (#3736).

The BFF forwards allowlisted ``{id, url}`` pairs on ``X-Digi-Mcp-Servers``,
optionally with ``auth`` / ``token`` after a session overlay merge. This
module lists those tools (prefixed ``{id}__{name}``) and proxies calls.
Visitor URLs never come from an untrusted JSON body — only the BFF header
(and ``DIGI_MCP_SERVERS``). Tokens are never logged.

``DIGI_MCP_SERVERS`` (``id=https://…,id2=https://…``) is the process-wide
fallback from the remote-MCP backlog item.

The literal allowlist in :func:`is_allowed_mcp_url` is not sufficient on its
own: an attacker-controlled hostname can pass it and then resolve to an
internal address (SSRF / DNS rebinding, #3879). Every Streamable HTTP connect
therefore goes through :class:`_SsrfSafeNetworkBackend`, which resolves the
host immediately before connecting, refuses the connection unless **every**
A/AAAA record passes the blocklist, and pins the socket to the validated IP.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any  # score:allow untyped any — MCP JSON payloads / tool results
from urllib.parse import urlparse

import anyio
import httpcore
import httpx

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "100.100.100.200",
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "localhost",
        "localtest.me",
        "lvh.me",
        "vcap.me",
    }
)
_LOOPBACK_DNS_SUFFIXES = (".localtest.me", ".lvh.me", ".vcap.me")
_REBIND_SUFFIXES = (".nip.io", ".sslip.io", ".xip.io")
_EMBEDDED_IPV4 = re.compile(r"(?:^|\.)((?:\d{1,3}\.){3}\d{1,3})(?:\.|$)")
_ALIBABA_METADATA = ipaddress.IPv4Address("100.100.100.200")
_CACHE_TTL_S = 60.0
_CALL_TIMEOUT_S = 30.0
_MAX_MCP_JSON = 16384
_MAX_TOKEN = 4096
_AUTH_KINDS = frozenset({"bearer", "oauth"})
_AUTH_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,40}$")

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="digi-mcp")


def _ip_is_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool = False
) -> bool:
    """True when *ip* must never be dialed.

    ``allow_private`` relaxes only RFC1918 / ULA. Loopback, link-local
    (``169.254.0.0/16``), unspecified, multicast, reserved and the Alibaba
    metadata address stay blocked either way.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_blocked(ip.ipv4_mapped, allow_private=allow_private)
    if ip == _ALIBABA_METADATA:
        return True
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
    return ip.is_private and not allow_private


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        if host.startswith("0x"):
            return ipaddress.IPv4Address(int(host, 16))
        if host.isdigit():
            return ipaddress.IPv4Address(int(host, 10))
    except (ValueError, OverflowError):
        return None
    return None


def _octet(part: str) -> int | None:
    try:
        if part.startswith("0x"):
            n = int(part, 16)
        elif part.isdigit():
            n = int(part, 10)
        else:
            return None
    except ValueError:
        return None
    return n if n >= 0 else None


def _coerce_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """WHATWG-style IPv4 (127.1, 0x7f.0x0.0x0.0x1) — ipaddress rejects these."""
    parsed = _parse_ip(host)
    if isinstance(parsed, ipaddress.IPv4Address):
        return parsed
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    nums: list[int] = []
    for part in parts:
        n = _octet(part)
        if n is None:
            return None
        nums.append(n)
    try:
        if len(nums) == 1:
            if nums[0] > 0xFFFFFFFF:
                return None
            return ipaddress.IPv4Address(nums[0])
        if len(nums) == 2:
            if nums[0] > 255 or nums[1] > 0xFFFFFF:
                return None
            return ipaddress.IPv4Address((nums[0] << 24) | nums[1])
        if len(nums) == 3:
            if nums[0] > 255 or nums[1] > 255 or nums[2] > 0xFFFF:
                return None
            return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | nums[2])
        if any(n > 255 for n in nums):
            return None
        return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3])
    except (ValueError, OverflowError):
        return None


def _hostname_is_blocked(host: str) -> bool:
    h = host.strip("[]").lower().rstrip(".")
    if not h or h in _METADATA_HOSTS:
        return True
    if h.endswith(".internal") or h.endswith(".localhost"):
        return True
    if any(h.endswith(suf) for suf in _LOOPBACK_DNS_SUFFIXES):
        return True
    if any(h.endswith(suf) for suf in _REBIND_SUFFIXES):
        return True
    parsed = _parse_ip(h)
    if parsed is not None:
        return _ip_is_blocked(parsed)
    coerced = _coerce_ipv4(h)
    if coerced is not None:
        return _ip_is_blocked(coerced)
    embedded = _EMBEDDED_IPV4.search(h)
    if embedded is not None:
        inner = _parse_ip(embedded.group(1))
        if inner is not None and _ip_is_blocked(inner):
            return True
    return False


def is_allowed_mcp_url(raw: str) -> bool:
    """https/http, no userinfo, no loopback / metadata / private-IP literals.

    Literal-only pre-filter: it never resolves DNS. The connect-time guard
    (:func:`_resolve_and_validate`) is the authoritative SSRF check — a
    hostname accepted here can still be refused when it resolves to a blocked
    address (#3879). Docker DNS names such as ``http://datatap-mcp:8080/mcp``
    stay allowed. Literal RFC1918 / loopback / link-local / IPv4-mapped
    metadata hosts do not. Shorthand IPv4 (``127.1``) and loopback DNS
    (``localtest.me``) are refused here without live DNS.
    """
    try:
        u = urlparse(raw.strip())
    except ValueError:
        return False
    if u.scheme not in ("http", "https"):
        return False
    if u.username or u.password:
        return False
    host = (u.hostname or "").lower()
    if _hostname_is_blocked(host):
        return False
    return True


class McpAddressRejected(Exception):
    """Refused to connect: the MCP host resolved to a blocked address.

    Deliberately not an ``OSError``/``httpx`` error so it is never mistaken for
    a transient network blip by retry logic; it surfaces in the existing
    warning logs from :func:`_list_tools_blocking` / :func:`_call_tool_blocking`.
    """


def _resolve_host_ips(host: str, port: int) -> list[str]:
    """Return every A/AAAA address for *host* (deduped). Raises ``OSError``."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips: list[str] = []
    seen: set[str] = set()
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]
        if addr and addr not in seen:
            seen.add(addr)
            ips.append(addr)
    return ips


async def _resolve_and_validate(host: str, port: int) -> str:
    """Resolve *host* and return the single validated IP to connect to.

    Fails closed: a resolution error, an empty answer, or **any** blocked
    A/AAAA record raises :class:`McpAddressRejected`. The returned IP is the
    exact address the caller must dial — re-resolving later would reopen the
    DNS-rebinding window this guard exists to close.

    A bare label with no dot (``datatap-mcp``) is container-internal service
    discovery rather than public DNS, so RFC1918 / ULA is expected and allowed;
    loopback, link-local and metadata addresses stay blocked. Fully-qualified
    names must resolve entirely to public addresses.
    """
    normalized = host.strip().strip("[]").lower().rstrip(".")
    literal = _parse_ip(normalized)
    if literal is not None:
        if _ip_is_blocked(literal):
            raise McpAddressRejected(f"MCP host {host!r} is a blocked address")
        return str(literal)
    allow_private = "." not in normalized
    try:
        ips = await anyio.to_thread.run_sync(_resolve_host_ips, host, port)
    except OSError as exc:
        raise McpAddressRejected(f"MCP host {host!r} did not resolve: {exc}") from exc
    if not ips:
        raise McpAddressRejected(f"MCP host {host!r} resolved to no address")
    for ip_str in ips:
        ip = _parse_ip(str(ip_str).strip())
        if ip is None:
            raise McpAddressRejected(f"MCP host {host!r} resolved to invalid address {ip_str!r}")
        if _ip_is_blocked(ip, allow_private=allow_private):
            raise McpAddressRejected(f"MCP host {host!r} resolved to blocked address {ip_str}")
    return str(ips[0])


class _SsrfSafeNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore backend that validates and pins DNS immediately before connect.

    ``connect_tcp`` resolves the host, refuses it if any resolved address is
    blocked, and hands the *validated* IP to the wrapped backend. The original
    hostname is still used by httpcore for the HTTP ``Host`` header and TLS
    SNI, so public HTTPS targets keep working.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._inner = inner if inner is not None else httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: httpcore.SOCKET_OPTION | None = None,
    ) -> httpcore.AsyncNetworkStream:
        pinned = await _resolve_and_validate(host, port)
        return await self._inner.connect_tcp(
            pinned,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: httpcore.SOCKET_OPTION | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._inner.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _SsrfSafeAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose connection pool uses :class:`_SsrfSafeNetworkBackend`.

    The response/stream handling is inherited from httpx; only the pool's
    network backend is swapped, before the pool is entered, so no connection
    can be created with the default resolver.
    """

    def __init__(self) -> None:
        super().__init__(verify=True, trust_env=True, retries=0)
        self._network_backend = _SsrfSafeNetworkBackend()
        self._pool._network_backend = self._network_backend


def _mcp_http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """MCP Streamable HTTP client that validates DNS at connect time (#3879)."""
    kwargs: dict[str, Any] = {
        "transport": _SsrfSafeAsyncHTTPTransport(),
        "follow_redirects": True,
        "timeout": timeout if timeout is not None else httpx.Timeout(30.0, read=300.0),
    }
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


def _auth_fields(item: dict[str, Any]) -> dict[str, str]:
    extra: dict[str, str] = {}
    auth = str(item.get("auth") or "").strip().lower()
    if auth in _AUTH_KINDS:
        extra["auth"] = auth
    token = str(item.get("token") or "").strip()
    if token and len(token) <= _MAX_TOKEN:
        extra["token"] = token
    # Operator-only (#3841) — the BFF never lets a session overlay set this.
    auth_header = str(item.get("authHeader") or "").strip()
    if auth_header and _AUTH_HEADER_RE.match(auth_header):
        extra["authHeader"] = auth_header
    return extra


def mcp_http_headers(server: dict[str, str]) -> dict[str, str] | None:
    """Auth header for Streamable HTTP. Never log the token.

    Defaults to ``Authorization: Bearer <token>``. An operator-declared
    ``authHeader`` (#3841) sends the raw token under that header name
    instead — e.g. DataTap's MCP server expects ``X-API-Key``.
    """
    token = (server.get("token") or "").strip()
    if not token:
        return None
    auth_header = (server.get("authHeader") or "").strip()
    if auth_header and _AUTH_HEADER_RE.match(auth_header):
        return {auth_header: token}
    return {"Authorization": f"Bearer {token}"}


def mcp_list_cache_key(server: dict[str, str]) -> str:
    """Cache identity includes a token fingerprint so auth changes miss."""
    token = (server.get("token") or "").strip()
    ident = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16] if token else "-"
    auth_header = (server.get("authHeader") or "").strip()
    return f"{server.get('id', '')}|{server.get('url', '')}|{ident}|{auth_header}"


def parse_mcp_servers_json(raw: str | None) -> list[dict[str, str]]:
    """Parse the BFF header. Unknown / malformed / oversize → empty."""
    if not raw or not raw.strip() or len(raw) > _MAX_MCP_JSON:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        if not _ID_RE.match(sid) or sid in seen:
            continue
        if not is_allowed_mcp_url(url):
            continue
        seen.add(sid)
        row: dict[str, str] = {"id": sid, "url": url}
        extra = _auth_fields(item)
        if extra:
            row.update(extra)
        out.append(row)
    return out


def parse_mcp_servers_env(raw: str | None = None) -> list[dict[str, str]]:
    """``DIGI_MCP_SERVERS=id=https://host/mcp,other=https://…``."""
    text = (raw if raw is not None else os.environ.get("DIGI_MCP_SERVERS", "")).strip()
    if not text:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in text.split(","):
        piece = part.strip()
        if not piece or "=" not in piece:
            continue
        sid, url = piece.split("=", 1)
        sid = sid.strip().lower()
        url = url.strip()
        if not _ID_RE.match(sid) or sid in seen or not is_allowed_mcp_url(url):
            continue
        seen.add(sid)
        out.append({"id": sid, "url": url})
    return out


def merge_mcp_servers(
    header_servers: list[dict[str, str]],
    env_servers: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Header wins on id collision; env fills the rest."""
    env = env_servers if env_servers is not None else parse_mcp_servers_env()
    by_id = {s["id"]: s for s in env}
    for s in header_servers:
        by_id[s["id"]] = s
    return list(by_id.values())


def prefixed_tool_name(server_id: str, tool_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)[:64]
    return f"{server_id}__{safe}"


def resolve_mcp_force_id(raw: str | None, servers: list[dict[str, str]]) -> str | None:
    """Return the MCP server id when *raw* names an operator server, else None."""
    token = (raw or "").strip().lstrip("/").lower()
    if not token or not _ID_RE.match(token):
        return None
    return token if any(s.get("id") == token for s in servers) else None


def split_prefixed_tool_name(name: str) -> tuple[str, str] | None:
    if "__" not in name:
        return None
    sid, rest = name.split("__", 1)
    if not _ID_RE.match(sid) or not rest:
        return None
    return sid, rest


def extra_tool_names_for_servers(servers: list[dict[str, str]]) -> list[str]:
    names: list[str] = []
    for s in servers:
        for td in list_tools_cached(s):
            fn = (td.get("function") or {}).get("name")
            if fn:
                names.append(str(fn))
    return names


def expand_mcp_disabled_tokens(
    tokens: list[str] | tuple[str, ...] | None,
    extra_names: list[str],
) -> frozenset[str]:
    """Disable ``id`` and ``id__*`` tools when the catalog MCP id is off."""
    if not tokens:
        return frozenset()
    extra = set(extra_names)
    out: set[str] = set()
    for raw in tokens:
        key = str(raw).strip().lower()
        if not key:
            continue
        prefix = f"{key}__"
        out |= {n for n in extra if n == key or n.startswith(prefix)}
    return frozenset(out)


def list_tools_cached(server: dict[str, str]) -> list[dict[str, Any]]:
    key = mcp_list_cache_key(server)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    tools = _list_tools_blocking(server)
    _cache[key] = (now, tools)
    return tools


def openai_tools_for_servers(servers: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in servers:
        out.extend(list_tools_cached(s))
    return out


def call_prefixed_tool(
    name: str,
    args: dict[str, Any],
    servers: list[dict[str, str]],
) -> dict[str, Any]:
    split = split_prefixed_tool_name(name)
    if not split:
        return {"error": "unknown_mcp_tool", "tool": name}
    sid, tool = split
    server = next((s for s in servers if s["id"] == sid), None)
    if not server or not server.get("url"):
        return {"error": "unknown_mcp_server", "tool": name}
    return _call_tool_blocking(server, tool, args)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    fut = _pool.submit(asyncio.run, coro)
    return fut.result(timeout=_CALL_TIMEOUT_S + 5)


def _list_tools_blocking(server: dict[str, str]) -> list[dict[str, Any]]:
    try:
        return _run_async(_list_tools_async(server))
    except Exception as exc:
        log.warning("remote MCP list_tools failed for %s: %s", server.get("id"), exc)
        return []


def _call_tool_blocking(server: dict[str, str], tool: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return _run_async(_call_tool_async(server, tool, args))
    except Exception as exc:
        log.warning("remote MCP call failed for %s: %s", tool, exc)
        return {"error": "mcp_call_failed", "tool": tool, "message": str(exc)}


async def _list_tools_async(server: dict[str, str]) -> list[dict[str, Any]]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = server["url"]
    server_id = server["id"]
    headers = mcp_http_headers(server)
    async with streamablehttp_client(
        url, headers=headers, httpx_client_factory=_mcp_http_client_factory
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    out: list[dict[str, Any]] = []
    for t in listed.tools:
        if isinstance(t.inputSchema, dict):
            schema = t.inputSchema
        else:
            schema = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": prefixed_tool_name(server_id, t.name),
                    "description": (t.description or "")[:2000],
                    "parameters": schema,
                },
            }
        )
    return out


async def _call_tool_async(
    server: dict[str, str], tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = server["url"]
    headers = mcp_http_headers(server)
    async with streamablehttp_client(
        url, headers=headers, httpx_client_factory=_mcp_http_client_factory
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
    text_parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            text_parts.append(str(text))
    if result.isError:
        return {
            "error": "mcp_tool_error",
            "tool": tool,
            "message": "\n".join(text_parts) or "error",
        }
    if text_parts:
        return {"ok": True, "text": "\n".join(text_parts)}
    return {"ok": True, "result": str(result)}
