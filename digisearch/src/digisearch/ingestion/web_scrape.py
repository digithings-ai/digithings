"""SSRF-safe URL filtering for web-scrape ingestion (REM-064)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_SCHEMES = frozenset({"file", "ftp", "gopher", "data", "javascript"})


def is_allowed_scrape_url(url: str) -> bool:
    """Return True when *url* is safe to fetch during web-scrape ingestion."""
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if not scheme or scheme in _BLOCKED_SCHEMES:
        return False
    if scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host == "localhost":
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
    except OSError:
        return False
    return True


def filter_scrape_hrefs(hrefs: list[str]) -> list[str]:
    """Keep only hrefs that pass :func:`is_allowed_scrape_url`."""
    out: list[str] = []
    for href in hrefs:
        if is_allowed_scrape_url(href):
            out.append(href.strip())
    return out
