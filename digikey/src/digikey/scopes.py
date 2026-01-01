"""Scope matching for digikey (supports * and component:* wildcards)."""

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
        # A granted component:* covers that component's children. The reverse
        # is not a grant: a narrower scope must not satisfy a requested prefix:*.
        if g.endswith(":*"):
            prefix = g[:-2]
            if required == prefix or required.startswith(prefix + ":"):
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
    # DIG-1177: screening call from digichat. Callers that send no
    # requested_scopes inherit this list, so it must stay here.
    "digisearch:screen",
    "digivault:read",
]

#: Scopes a ``bff_session`` caller may *request*: the default set plus the MCP
#: edge scopes (DIG-5635). digichat mints its MCP-edge token with
#: ``requested_scopes: ["mcp:digisearch", "mcp:digivault"]``, so the exchange has
#: to grant them.
#:
#: They are deliberately NOT in :data:`DEFAULT_BFF_SESSION_SCOPES`: a token
#: minted with no ``requested_scopes`` inherits the defaults, and it must not
#: silently gain edge access. Requesting is the only way in.
BFF_SESSION_GRANTABLE_SCOPES: list[str] = [
    *DEFAULT_BFF_SESSION_SCOPES,
    "mcp:digisearch",
    "mcp:digivault",
]

#: Scope the MCP edge requires for a digivault *write* tool (`create_note`;
#: ``MCP_EDGE_WRITE_SCOPES`` in ``apps/digithings-stack-cloudflare``). It is
#: deliberately **not** in :data:`BFF_SESSION_GRANTABLE_SCOPES`: ``mcp:digivault``
#: is read-only, so a BFF session can never mint a write-capable edge token.
#: Only an admin-issued API key that already carries it can write (DIG-5723).
MCP_DIGIVAULT_WRITE_SCOPE = "mcp:digivault:write"
