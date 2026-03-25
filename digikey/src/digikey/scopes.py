"""Scope matching for DigiKey (supports * and component:* wildcards)."""

from __future__ import annotations


def scope_grants_required(granted: list[str], required: list[str]) -> bool:
    """True if every *required* scope is satisfied by *granted*."""
    if any(g.strip() == "*" for g in granted if g):
        return True
    for req in required:
        if not req:
            continue
        if not _one_required(granted, req.strip()):
            return False
    return True


def _one_required(granted: list[str], required: str) -> bool:
    for g in granted:
        g = g.strip()
        if not g:
            continue
        if g == required:
            return True
        if g.endswith(":*"):
            prefix = g[:-2]
            if required == prefix or required.startswith(prefix + ":"):
                return True
        if required.endswith(":*") and g.startswith(required[:-2] + ":"):
            return True
    return False


# Default scopes issued for BFF session exchange (overridable via env)
DEFAULT_BFF_SESSION_SCOPES: list[str] = [
    "digigraph:workflow",
    "digigraph:chat",
    "digigraph:mcp",
    "digiquant:backtest",
    "digiquant:optimize",
    "digisearch:query",
    "digisearch:ingest",
]
