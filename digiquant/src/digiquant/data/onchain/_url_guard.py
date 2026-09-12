"""Shared base-URL guard for on-chain HTTP clients (SSRF hardening, #3944).

The data-source MCP/orchestrator tools must never accept a caller-nominated
``base_url``: it is an SSRF primitive and, for BGeometrics, would send the
server-owned ``BGEOMETRICS_API_TOKEN`` to an attacker host. The caller-facing
schemas no longer expose ``base_url``; this module is the defence-in-depth
check for the code-only seam (client constructors / library fetch helpers).
"""

from __future__ import annotations

from urllib.parse import urlparse


def is_allowed_base_url(base_url: str, allowed_hosts: frozenset[str]) -> bool:
    """True only for an https URL on an allowlisted host with the default port.

    Rejects userinfo (``https://allowed@evil``), non-443 ports, and any
    non-https scheme. A caller-nominated base therefore cannot reach an
    internal host or a cloud metadata endpoint even via the code seam.
    """
    try:
        parsed = urlparse(base_url)
        port = parsed.port
    except ValueError:  # malformed port / scheme
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = (parsed.hostname or "").lower()
    if host not in allowed_hosts:
        return False
    if port not in (None, 443):
        return False
    return True


__all__ = ["is_allowed_base_url"]
