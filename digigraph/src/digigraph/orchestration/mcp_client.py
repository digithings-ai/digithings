"""Remote MCP tool proxy for extra servers declared by a trusted BFF (#3736).

The BFF forwards allowlisted ``{id, url}`` pairs on ``X-Digi-Mcp-Servers``,
optionally with ``auth`` / ``token`` after a session overlay merge. This
module lists those tools (prefixed ``{id}_{name}``) and proxies calls.
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
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any  # score:allow untyped any — MCP JSON payloads / tool results
from urllib.parse import urlparse

import anyio
import httpcore
import httpx

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
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
_DNS_RESOLVE_TIMEOUT_S = 5.0
_MAX_MCP_JSON = 16384
_MAX_TOKEN = 4096
_AUTH_KINDS = frozenset({"bearer", "oauth"})
_AUTH_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,40}$")
# Raw remote tool name carried alongside a listed tool (DIG-284). The offered
# name `prefixed_tool_name` builds substitutes non-identifier characters and
# truncates at 64, so it cannot be matched back to the name an operator put in
# `allowedTools`. Stripped before the record reaches a model provider.
_RAW_TOOL_NAME_KEY = "x_digi_mcp_raw_tool_name"
# Opt-in hardening (#3879): when set, only these hostnames (comma-separated,
# typically dotless Docker service names) may resolve into private space.
_PRIVATE_HOST_ALLOWLIST_ENV = "DIGIGRAPH_MCP_PRIVATE_HOST_ALLOWLIST"

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
# The names the MCP servers actually advertise, captured at list time beside
# _cache under the same key. The offered name ``<server_id>_<safe>`` is lossy:
# every character outside [a-zA-Z0-9_-] collapses to "_" and the remainder is
# capped at 64 chars, so the advertised name cannot be recovered from it (the
# capture also keeps names longer than 64 chars callable). Written in
# _list_tools_async, the only place the advertised name exists, so it is always
# the same snapshot as _cache. Deliberately has no TTL of its own: expiring it
# while _cache still serves the same offered names would put the call path back
# on the broken behaviour with nothing to compensate (DIG-507).
_raw_names_cache: dict[str, list[str]] = {}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="digi-mcp")

# Which (catalog, allowlist) pairs have already been audited this run, keyed by the
# cache key plus the allowlist signature. One research turn reads the catalog twice
# — once for the policy path and once for the provider projection — so without this
# every refusal would be counted twice and "20 tools refused" would read as 40.
# The narrowing itself is never cached; only the duplicate audit is suppressed.
_audited: set[tuple[str, tuple[str, ...] | None]] = set()


def _ip_is_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool = False
) -> bool:
    """True when *ip* must never be dialed.

    Loopback, link-local (``169.254.0.0/16``), unspecified, multicast, reserved
    and the Alibaba metadata address are always blocked. Everything that is not
    globally routable is blocked too — that closes the CGNAT hole
    (``100.64.0.0/10`` is neither ``is_private`` nor globally reachable, #3879).

    ``allow_private`` is the dotless-Docker carve-out: it un-blocks only
    RFC1918 / ULA addresses (``is_private``) that are explicitly trusted; CGNAT
    and the always-blocked ranges stay refused.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_blocked(ip.ipv4_mapped, allow_private=allow_private)
    if ip == _ALIBABA_METADATA:
        return True
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
    if allow_private and ip.is_private:
        return False
    return not ip.is_global


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
    """https/http, no userinfo, no loopback / metadata / non-global IP literals.

    Literal-only pre-filter: it never resolves DNS. The connect-time guard
    (:func:`_resolve_and_validate`) is the authoritative SSRF check — a
    hostname accepted here can still be refused when it resolves to a blocked
    address (#3879). Docker DNS names such as ``http://datatap-mcp:8080/mcp``
    stay allowed. Literal RFC1918 / CGNAT / loopback / link-local /
    IPv4-mapped metadata hosts do not. Shorthand IPv4 (``127.1``) and loopback
    DNS (``localtest.me``) are refused here without live DNS.
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


def _private_host_allowlist() -> frozenset[str] | None:
    """Explicit hostnames allowed to resolve into private space, or ``None``.

    ``None`` means the env var is unset (dotless Docker carve-out active).
    An empty set means the operator set it to blank — nothing is allowed to
    resolve private, i.e. the strictest mode.
    """
    raw = os.environ.get(_PRIVATE_HOST_ALLOWLIST_ENV)
    if raw is None:
        return None
    return frozenset(
        part.strip().strip("[]").lower().rstrip(".") for part in raw.split(",") if part.strip()
    )


async def _resolve_and_validate(host: str, port: int) -> list[str]:
    """Resolve *host* and return **all** validated IPs, best first.

    Fails closed: a resolution error, timeout, empty answer, or **any** blocked
    A/AAAA record raises :class:`McpAddressRejected`. The returned addresses are
    the exact ones the caller may dial — re-resolving later would reopen the
    DNS-rebinding window this guard exists to close. Returning the whole list
    (not just the first) lets the caller fall back across a dual-stack answer
    without ever asking DNS again.

    A bare label with no dot (``datatap-mcp``) is container-internal service
    discovery rather than public DNS, so RFC1918 / ULA is expected and allowed;
    loopback, link-local, metadata and CGNAT stay blocked. Fully-qualified names
    must resolve entirely to public addresses. When
    ``DIGIGRAPH_MCP_PRIVATE_HOST_ALLOWLIST`` is set, the dotless carve-out is
    replaced by the explicit list: **only** those names may resolve private.
    """
    normalized = host.strip().strip("[]").lower().rstrip(".")
    literal = _parse_ip(normalized)
    if literal is not None:
        if _ip_is_blocked(literal):
            raise McpAddressRejected(f"MCP host {host!r} is a blocked address")
        return [str(literal)]
    allowlist = _private_host_allowlist()
    if allowlist is None:
        allow_private = "." not in normalized
    else:
        allow_private = normalized in allowlist
    try:
        with anyio.fail_after(_DNS_RESOLVE_TIMEOUT_S):
            ips = await anyio.to_thread.run_sync(
                _resolve_host_ips, host, port, abandon_on_cancel=True
            )
    except TimeoutError as exc:
        raise McpAddressRejected(f"MCP host {host!r} DNS resolution timed out") from exc
    except OSError as exc:
        raise McpAddressRejected(f"MCP host {host!r} did not resolve: {exc}") from exc
    if not ips:
        raise McpAddressRejected(f"MCP host {host!r} resolved to no address")
    validated: list[str] = []
    for ip_str in ips:
        ip = _parse_ip(str(ip_str).strip())
        if ip is None:
            raise McpAddressRejected(f"MCP host {host!r} resolved to invalid address {ip_str!r}")
        if _ip_is_blocked(ip, allow_private=allow_private):
            raise McpAddressRejected(f"MCP host {host!r} resolved to blocked address {ip_str}")
        validated.append(str(ip_str))
    return validated


class _SsrfSafeNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore backend that validates and pins DNS immediately before connect.

    ``connect_tcp`` resolves the host, refuses it if any resolved address is
    blocked, then dials the *validated* addresses in order (dual-stack
    Happy-Eyeballs without a second DNS lookup). The original hostname is still
    used by httpcore for the HTTP ``Host`` header and TLS SNI, so public HTTPS
    targets keep working.
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
        addresses = await _resolve_and_validate(host, port)
        last_exc: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_exc = exc
        if last_exc is None:  # pragma: no cover - _resolve_and_validate guarantees non-empty
            raise McpAddressRejected(f"MCP host {host!r} resolved to no usable address")
        raise last_exc

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
        setup = item.get("setup")
        if isinstance(setup, dict) and setup:
            clean = {
                str(k): str(v)
                for k, v in setup.items()
                if isinstance(k, str) and isinstance(v, (str, int, float, bool))
            }
            if clean:
                row["setup"] = json.dumps(clean, sort_keys=True)
        # Operator tool allowlists (DIG-284). Carried, not validated: the shape
        # check below is deliberate, because a non-list value must read as
        # absent (deny everything) rather than be coerced into something that
        # looks configured. An explicit [] is carried as "[]" so the empty list
        # survives to the model field, where rule 1 and rule 5 read it and its
        # absence as two different answers. Bounds live in digigraph.models and
        # are enforced there (and by `_mcp_tool_names`), so they cannot drift.
        for key in ("allowedTools", "mutatingTools"):
            names = item.get(key)
            if isinstance(names, list):
                row[key] = json.dumps(names)
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
    return f"{server_id}_{safe}"


def _tool_record(
    server_id: str,
    name: str,
    description: str | None = None,
    schema: Any = None,
) -> dict[str, Any]:
    """One listed tool: the offered name plus the raw name it came from.

    Keeping the raw name is the only way an allowlist written in real remote
    names can be matched at all (DIG-284) — the offered name is lossy. The
    sidecar is stripped in :func:`openai_tools_for_servers`, so what a model
    provider receives is byte-identical to before this key existed.
    """
    return {
        "type": "function",
        "function": {
            "name": prefixed_tool_name(server_id, name),
            "description": (description or "")[:2000],
            "parameters": (
                schema if isinstance(schema, dict) else {"type": "object", "properties": {}}
            ),
        },
        _RAW_TOOL_NAME_KEY: name,
    }


def raw_tool_names_for_server(server_id: str, tools: Iterable[Any] | None) -> list[str]:
    """Remote tool names for one server as advertised — pre-substitution, pre-truncation.

    ``prefixed_tool_name`` replaces every character outside ``[a-zA-Z0-9_-]`` and
    cuts the result at 64, so ``atlassian.executeWrite`` and a 76-character
    camelCase name both reach the gate wearing a name no operator wrote. An
    allowlist is written in real names, so the real name has to travel with the
    listed tool.

    Only records carrying a raw name *and* addressed to *server_id* are reported:
    a name is returned when it was observed, never reconstructed by reversing a
    lossy substitution. Order-preserving, de-duplicated.
    """
    prefix = f"{server_id}_"
    out: list[str] = []
    for td in tools or ():
        if not isinstance(td, dict):
            continue
        raw = td.get(_RAW_TOOL_NAME_KEY)
        fn = td.get("function")
        offered = fn.get("name") if isinstance(fn, dict) else None
        if not isinstance(raw, str) or not raw or not isinstance(offered, str):
            continue
        if not offered.startswith(prefix):
            continue
        if raw not in out:
            out.append(raw)
    return out


def _server_tool_names(server: Any, *keys: str) -> list[str] | None:
    """One tool-name list off a server row or ref; ``None`` means absent.

    Accepts an ``McpServerRef`` and the flat rows that reach graph state — wire
    spelling (``allowedTools``, from ``model_dump(by_alias=True)``) or the snake
    attribute name — so the gate reads the row it was handed instead of demanding
    a re-projection. A non-list value reads as absent.
    """
    for key in keys:
        value = server.get(key) if isinstance(server, dict) else getattr(server, key, None)
        if isinstance(value, (list, tuple)):
            return [name for name in value if isinstance(name, str)]
    return None


def mcp_server_allows_raw_tool(server: Any, raw_name: str) -> bool:
    """Rule 2: exact equality against the allowlist. No glob, no prefix, ever.

    Every near-miss denies, on purpose: a glob, a case-folded hit, or a longer
    name that merely starts with an allowed one each widen one approved tool
    into a family of unapproved ones. Absent and ``[]`` both deny everything
    (rule 1), so this is safe to call before the allowlist has been checked for
    presence.
    """
    allowed = _server_tool_names(server, "allowedTools", "allowed_tools")
    if not allowed:
        return False
    return isinstance(raw_name, str) and raw_name in allowed


def mcp_server_mutating_tools(server: Any) -> set[str]:
    """Rule 5: an absent ``mutatingTools`` means every allowed tool mutates.

    An explicit ``[]`` is the operator saying nothing mutates. The two are
    different answers, which is why the wire keeps them distinguishable — and why
    only a row that allows something can tell the difference. This set never
    grants: it is an advisory, and ``allowedTools`` is the only list that grants
    (review #5061 S2 — a stale name here is inert, not an accidental grant).
    """
    mutating = _server_tool_names(server, "mutatingTools", "mutating_tools")
    if mutating is not None:
        return set(mutating)
    return set(_server_tool_names(server, "allowedTools", "allowed_tools") or ())


# The four remote-control meta tools, refused before any allowlist is consulted.
# Held as normalised single segments rather than literal names: the brake keys on
# the raw name an operator writes, and ``atlassian.executeWrite`` is not
# byte-equal to ``executeWrite`` — a literal set would wave every namespaced
# spelling straight through (review #5074 S2).
_REFUSED_META_SEGMENTS = frozenset(
    {"discover", "executeread", "executewrite", "executedestructive"}
)


def _refused_meta_tool(raw_name: str) -> bool:
    """True when *raw_name* is one of the meta tools under any spelling.

    The normalisation is the same substitution ``prefixed_tool_name`` applies to
    build the offered name, then case-folded, so a check cannot drift from the
    name it is checking. The deny then tests whole segments: after substitution
    every run of ``.``/``:``/whitespace/``-``/``_`` is a segment boundary, so
    ``executeWrite``, ``executewrite``, ``atlassian.executeWrite`` and
    ``confluence-executeWrite`` all deny while ``getJiraIssue`` does not.

    This fails towards refusal, which is the cheap direction to fail in: the cost
    of denying a legitimate tool is that the operator notices a name they wrote
    is refused, and the cost of granting a meta tool is a server the operator did
    not choose decides which tools the model gets to call.
    """
    if not isinstance(raw_name, str):
        return False
    normalised = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name).casefold()
    return any(segment in _REFUSED_META_SEGMENTS for segment in re.split(r"[._-]", normalised))


def _tool_denied(tool: str, reason: str) -> None:
    """Record one refusal. Audit, not log: a denied tool is an answer, not a fault."""
    from digigraph.audit import audit_log

    audit_log(
        "tool_denied",
        agent_id="digigraph",
        payload={"tool": tool, "reason": reason, "source": "mcp"},
    )


def filter_tools_for_server(
    server: dict[str, str],
    tools: list[dict[str, Any]],
    *,
    audit_key: str | None = None,
) -> list[dict[str, Any]]:
    """Rule 1-4: narrow one server's listed tools to what its row allows.

    The offer is already prefixed, substituted and truncated by
    ``prefixed_tool_name``, so an allowlist entry can never be compared against it —
    the raw name is not recoverable from the offered one. The raw name travels
    beside each record in the ``_RAW_TOOL_NAME_KEY`` sidecar, which is why the
    filter reads the sidecar and not the function name.

    Four rules, in the order they can refuse:

    * the meta tools are refused first, before the allowlist is read, so an
      operator who allowlists one still does not get it;
    * everything else needs exact equality against ``allowedTools`` — absent and
      ``[]`` both deny, and a row with no usable allowlist has every tool denied;
    * a record without a sidecar cannot be matched to anything the operator
      wrote, so it is refused rather than offered unattributed;
    * two approved tools that collapse to one offered name offer neither, because
      picking either would let the server's listing order decide which approved
      tool the model actually runs.

    A row whose allowlist is missing fails loudly (id, host, count) as well as
    refusing: a silently dark row is indistinguishable from a server that offered
    nothing, and the config mistake that caused it goes unnoticed.

    *audit_key* suppresses a repeated audit for the same catalog under the same
    allowlist. The narrowing is always recomputed; only the duplicate refusal
    record is dropped, so a count read off the audit trail is a count of tools.
    """
    if not tools:
        return []

    declared = _server_tool_names(server, "allowedTools", "allowed_tools")
    # A missing key and an explicit ``[]`` are the same deny (rule 1) but they are
    # not the same config, so they must not share a dedup key: `if declared` would
    # collapse both to ``()`` and let whichever arrived first swallow the other's
    # refusals. The absent case would then be audited, the empty case would report
    # nothing, and "I wrote the key out and it still went dark" has no trace.
    signature = None if declared is None else tuple(sorted(declared))
    audit = audit_key is None or (audit_key, signature) not in _audited
    if audit and audit_key is not None:
        _audited.add((audit_key, signature))

    if not declared:
        # Loud on every turn, never deduplicated: the audit dedup exists to keep
        # a count of *tools* off the trail, but a dark row is a config mistake
        # the operator has to see, and suppressing the second occurrence would
        # read as "already told them" for a row they never saw a warning about.
        _warn_allowlist_missing(server, tools)
    # Absent and empty both deny everything, so the membership test below needs
    # no None branch — only the *record* of which spelling was used, kept above.
    allowed: frozenset[str] = frozenset(declared or ())

    kept: list[dict[str, Any]] = []
    # Offered name -> the raw name that produced it. Two approved tools that
    # collapse to one offered name are a conflict the gate cannot resolve: the
    # model's choice of name would decide which approved tool runs.
    owner: dict[str, str] = {}
    collided: set[str] = set()

    for td in tools:
        if not isinstance(td, dict):
            continue
        fn = (td.get("function") or {}).get("name")
        raw = td.get(_RAW_TOOL_NAME_KEY)
        if not fn or not isinstance(raw, str):
            if audit:
                _tool_denied(str(fn or raw or "?"), "unattributed")
            continue
        if _refused_meta_tool(raw):
            if audit:
                _tool_denied(raw, "meta_tool")
            continue
        if raw not in allowed:
            if audit:
                _tool_denied(raw, "not_allowlisted")
            continue
        if str(fn) in collided:
            if audit:
                _tool_denied(raw, "offered_name_collision")
            continue
        if str(fn) in owner and owner[str(fn)] != raw:
            collided.add(str(fn))
            first_raw = owner[str(fn)]
            for dropped in list(kept):
                if (dropped.get("function") or {}).get("name") == fn:
                    kept.remove(dropped)
            if audit:
                # Both approved tools lose the name, so both are recorded. The
                # operator wrote two rows and must see two refusals; recording
                # only the later arrival also makes the trail depend on the
                # order the server happened to list them in.
                _tool_denied(first_raw, "offered_name_collision")
                _tool_denied(raw, "offered_name_collision")
            continue
        owner[str(fn)] = raw
        kept.append(td)

    return kept


def _warn_allowlist_missing(server: Any, tools: list[dict[str, Any]]) -> None:
    """Name the row, its host and how much it just lost."""
    server_id = str(server.get("id") if isinstance(server, dict) else getattr(server, "id", "?"))
    raw_url = str(
        server.get("url") if isinstance(server, dict) else getattr(server, "url", "") or ""
    )
    host = urlparse(raw_url).netloc or raw_url or "?"
    log.warning(
        "MCP server %s (%s) has no allowedTools: refusing all %d advertised tools. "
        "Add an explicit allowedTools list to the server row to enable any of them.",
        server_id,
        host,
        len(tools),
    )


def resolve_mcp_force_id(raw: str | None, servers: list[dict[str, str]]) -> str | None:
    """Return the MCP server id when *raw* names an operator server, else None."""
    token = (raw or "").strip().lstrip("/").lower()
    if not token or not _ID_RE.match(token):
        return None
    return token if any(s.get("id") == token for s in servers) else None


def split_prefixed_tool_name(name: str) -> tuple[str, str] | None:
    if "_" not in name:
        return None
    sid, rest = name.split("_", 1)
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
    """Disable ``id`` and ``id_*`` tools when the catalog MCP id is off."""
    if not tokens:
        return frozenset()
    extra = set(extra_names)
    out: set[str] = set()
    for raw in tokens:
        key = str(raw).strip().lower()
        if not key:
            continue
        prefix = f"{key}_"
        out |= {n for n in extra if n == key or n.startswith(prefix)}
    return frozenset(out)


def list_tools_cached(server: dict[str, str]) -> list[dict[str, Any]]:
    """Listed tools for one server, narrowed to what that row allows.

    The cache holds the full advertised catalog and the narrowing happens on
    every call. That split is deliberate: ``mcp_list_cache_key`` keys on id, URL,
    token and header name — not on the allowlist — so baking the filter into the
    cache entry would let one row's allowlist answer another row's, or let a
    tightened row keep serving the wider answer for the rest of the 60s TTL. The
    allowlist is a property of the row, so it is read per call.
    """
    key = mcp_list_cache_key(server)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        tools = hit[1]
    else:
        tools = _list_tools_blocking(server)
        _cache[key] = (now, tools)
    return filter_tools_for_server(server, tools, audit_key=key)


def openai_tools_for_servers(servers: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Listed tools for a model provider: raw-name sidecars removed.

    The only path from the cache to a provider, so it is where the sidecar has to
    go. A copy is returned rather than the cached dict mutated, or the raw name
    would be gone for the next caller inside the 60s TTL.
    """
    out: list[dict[str, Any]] = []
    for s in servers:
        for td in list_tools_cached(s):
            if isinstance(td, dict) and _RAW_TOOL_NAME_KEY in td:
                out.append({k: v for k, v in td.items() if k != _RAW_TOOL_NAME_KEY})
            else:
                out.append(td)
    return out


def raw_tool_names_for_server(server: dict[str, str]) -> list[str] | None:
    """Advertised tool names captured for ``server`` at list time.

    ``None`` means no ``list_tools`` snapshot has been captured for this server
    key. That is not the same as "the server advertises no tools": a caller must
    not guess a remote name when the capture is absent.
    """
    return _raw_names_cache.get(mcp_list_cache_key(server))


def resolve_remote_tool_name(server_id: str, offered: str, raw_names: list[str]) -> str | None:
    """Recover the advertised name behind ``offered``; ``None`` when not unique.

    ``offered`` is the whole name the model chose, server prefix included --
    what ``prefixed_tool_name`` produced at list time.

    ``prefixed_tool_name`` is lossy, so several advertised names can collapse
    onto one offered name -- any two sharing their first 64 safe characters.
    Refusing on ambiguity is deliberate: picking either one would call a tool
    the model did not ask for (DIG-507).
    """
    match: str | None = None
    for raw in raw_names:
        if prefixed_tool_name(server_id, raw) != offered:
            continue
        if match is not None:
            return None
        match = raw
    return match


def call_prefixed_tool(
    name: str,
    args: dict[str, Any],
    servers: list[dict[str, str]],
) -> dict[str, Any]:
    split = split_prefixed_tool_name(name)
    if not split:
        return {"error": "unknown_mcp_tool", "tool": name}
    sid, offered = split
    server = next((s for s in servers if s["id"] == sid), None)
    if not server or not server.get("url"):
        return {"error": "unknown_mcp_server", "tool": name}
    # Call the name the server advertised, not the lossy offered name we handed
    # the model (DIG-507). ``name`` is the whole prefixed name, which is what
    # prefixed_tool_name() rebuilds; ``offered`` is only its prefix-stripped tail.
    raw_names = raw_tool_names_for_server(server)
    if raw_names is None:
        tool = offered
    else:
        tool = resolve_remote_tool_name(sid, name, raw_names)
        if tool is None:
            log.error(
                "offered MCP tool %s for server %s matches no unique advertised name; refusing",
                name,
                sid,
            )
            return {
                "error": "mcp_tool_name_unresolved",
                "tool": name,
                "server": sid,
                "message": (
                    f"Offered tool {name!r} does not map to exactly one tool advertised by "
                    f"server {sid!r}; refusing to call rather than guess a remote tool name."
                ),
            }
    setup_raw = server.get("setup")
    # State carries the decoded mapping (workflow.py dumps McpServerRef.setup);
    # a raw parsed-header row carries the JSON-encoded form.
    setup: dict[str, Any] = {}
    if isinstance(setup_raw, dict):
        setup = setup_raw
    elif setup_raw:
        try:
            decoded = json.loads(setup_raw)
        except (TypeError, json.JSONDecodeError):
            decoded = {}
        if isinstance(decoded, dict):
            setup = decoded
    if setup:
        args = {**args, **{str(k): v for k, v in setup.items()}}
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
        detail = str(exc)
        if isinstance(exc, BaseExceptionGroup):
            detail = "; ".join(f"{type(e).__name__}: {e}" for e in exc.exceptions)
        log.warning("remote MCP call failed for %s: %s", tool, detail)
        return {"error": "mcp_call_failed", "tool": tool, "message": detail}


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
    # Capture the advertised names before prefixed_tool_name() discards them
    # (DIG-507). De-duplicated, order preserved, so resolve_remote_tool_name()
    # reads ambiguity as ambiguity and not as a repeated entry.
    advertised: list[str] = []
    seen: set[str] = set()
    for t in listed.tools:
        if t.name not in seen:
            seen.add(t.name)
            advertised.append(t.name)
        out.append(_tool_record(server_id, t.name, t.description, t.inputSchema))
    _raw_names_cache[mcp_list_cache_key(server)] = advertised
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
