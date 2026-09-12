"""SSRF-safe URL validation for the non-browser fetch path.

The fetch seam (:class:`digifetch.http.HttpFetcher`) is reachable from
user-influenced URLs (search results, scraped links). A URL that looks benign
can name, or redirect to, an internal address — cloud metadata
(``169.254.169.254`` / ``100.100.100.200``), loopback, link-local, RFC1918,
CGNAT (``100.64.0.0/10``) or ``0.0.0.0`` — and an auto-following HTTP client
will happily dial it. This module is the single guard for that path.

Policy:

* Only ``http`` / ``https`` URLs with a host are accepted.
* The host is resolved and **every** resolved address must be globally
  routable. Loopback, link-local, private, CGNAT, unspecified, reserved,
  multicast, and the known metadata addresses are refused.
* An operator-supplied ``allowed_hosts`` set (exact hostnames) is the explicit
  escape hatch for a trusted internal host; it bypasses the private-address
  refusal for that host only. ``digifetch`` reads no environment variables —
  consumers (e.g. ``digisearch`` via ``DIGISEARCH_FETCH_ALLOWED_HOSTS``) read
  the env and pass the value in.

Residual limitation (documented, not a regression): validation resolves DNS,
then ``httpx`` resolves again when it connects, so a hostile resolver that
changes its answer between the two lookups can still win the race. This guard
closes the practical SSRF vectors — literal internal addresses, internal
hostnames, and redirects into either — without pinning sockets.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

__all__ = ["SsrfBlockedError", "is_blocked_ip", "validate_fetch_url"]

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Always refused, even though the ranges they live in are already non-global.
_METADATA_IPS = frozenset(
    {
        ipaddress.IPv4Address("169.254.169.254"),  # AWS / GCP / Azure IMDS
        ipaddress.IPv4Address("100.100.100.200"),  # Alibaba IMDS
    }
)
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "100.100.100.200",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "localhost",
    }
)
# Suffixes that resolve to loopback / a container's own netns.
_LOCAL_SUFFIXES = (".local", ".internal", ".localhost")
# Wildcard-DNS services that echo an embedded IP back as the answer.
_REBIND_SUFFIXES = (".nip.io", ".sslip.io", ".xip.io", ".localtest.me", ".lvh.me", ".vcap.me")


class SsrfBlockedError(RuntimeError):
    """Raised when a URL is refused by the SSRF guard (scheme, host, or IP)."""


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when *ip* must never be dialled by the fetch path.

    Loopback, link-local, unspecified, multicast, reserved and the known
    metadata addresses are always refused; so is anything not globally
    routable, which closes the CGNAT hole (``100.64.0.0/10`` is neither
    ``is_private`` nor globally reachable). IPv4-mapped IPv6 is unwrapped.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_blocked_ip(ip.ipv4_mapped)
    if ip in _METADATA_IPS:
        return True
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
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
            return int(part, 16)
        if part.isdigit():
            return int(part, 10)
    except ValueError:
        return None
    return None


def _coerce_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """WHATWG-style IPv4 shorthand (``127.1``, ``0x7f.0.0.1``) — ipaddress rejects these."""
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
            return ipaddress.IPv4Address(nums[0]) if nums[0] <= 0xFFFFFFFF else None
        if len(nums) == 2:
            return (
                ipaddress.IPv4Address((nums[0] << 24) | nums[1])
                if nums[0] <= 255 and nums[1] <= 0xFFFFFF
                else None
            )
        if len(nums) == 3:
            return (
                ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | nums[2])
                if nums[0] <= 255 and nums[1] <= 255 and nums[2] <= 0xFFFF
                else None
            )
        if any(n > 255 for n in nums):
            return None
        return ipaddress.IPv4Address((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3])
    except (ValueError, OverflowError):
        return None


def _hostname_is_blocked(host: str) -> bool:
    """Literal / metadata / rebind hostnames — checked before any DNS lookup."""
    h = host.strip("[]").lower().rstrip(".")
    if not h or h in _METADATA_HOSTS:
        return True
    if any(h.endswith(suffix) for suffix in _LOCAL_SUFFIXES):
        return True
    if any(h.endswith(suffix) for suffix in _REBIND_SUFFIXES):
        return True
    literal = _parse_ip(h)
    if literal is not None:
        return is_blocked_ip(literal)
    coerced = _coerce_ipv4(h)
    if coerced is not None:
        return is_blocked_ip(coerced)
    return False


def _resolve(host: str, port: int | None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* to addresses, deduplicated.

    A resolution failure returns ``[]``: no address was reachable to block, and
    the subsequent ``httpx`` connection uses the same resolver, so it will fail
    too. Blocking *successfully* resolved internal addresses is what matters.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if addr not in out:
            out.append(addr)
    return out


def validate_fetch_url(url: str, *, allowed_hosts: Iterable[str] = ()) -> str:
    """Validate *url* for the fetch path, returning it unchanged on success.

    Raises :class:`SsrfBlockedError` on a non-http(s) scheme, a missing host, a
    blocked literal/internal hostname, or a host that resolves to a blocked
    address. A host listed in *allowed_hosts* (exact, case-insensitive) bypasses
    the address refusal — the operator's explicit trusted-host escape hatch.
    """
    raw = (url or "").strip()
    if not raw:
        raise SsrfBlockedError("empty URL")
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise SsrfBlockedError(f"unparseable URL {raw!r}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SsrfBlockedError(f"scheme {scheme!r} not allowed (http/https only)")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SsrfBlockedError(f"URL {raw!r} has no host")

    allowed = {h.strip().lower() for h in allowed_hosts if h and h.strip()}
    if host in allowed:
        return raw

    if _hostname_is_blocked(host):
        raise SsrfBlockedError(f"host {host!r} is blocked (SSRF guard)")

    for addr in _resolve(host, parsed.port):
        if is_blocked_ip(addr):
            raise SsrfBlockedError(f"host {host!r} resolves to blocked address {addr}")

    return raw
