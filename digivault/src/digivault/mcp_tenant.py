"""Binds the digivault MCP surface's ``path_prefix`` to the caller's verified tenant.

The HTTP API already refuses a ``path_prefix`` that is not the caller's own
corpus (``enforce_tenant_path_prefix`` in ``server.py``). The MCP transport did
not: every tool took the prefix straight from its arguments, so any holder of a
digikey JWT that opened the edge (``mcp:digivault``, ``mcp:*`` or ``*``) could
read, and with the write scope create, notes under any other tenant's prefix
(#6648). The digichat path was only safe because digigraph merges the operator
``setup.path_prefix`` over model arguments.

The MCP server has no auth middleware. The stack edge verifies the caller and
forwards the request with its headers intact, so the tenant is re-read here
from the signature-checked bearer itself, never from any header the edge or the
caller could set. Rules:

- **Bearer present.** It must verify (signature, revocation, the
  ``mcp:digivault`` scope) and carry a tenant claim, or the call is refused:
  a claimless token has no tenant and gets no prefix (fail closed). With
  ``DIGI_TENANT_CORPUS_MAP`` set, a blank prefix resolves to the token
  tenant's own prefix and any other prefix is refused. With the map unset the
  deployment is single-tenant and the requested prefix is kept.
- **No ``Authorization`` header.** The caller came through the static edge key
  (compose/self-host compat, an operator credential the edge already checked)
  or from inside the container network. Behaviour is unchanged.
- **Any other ``Authorization`` scheme** is refused rather than guessed at.

Refusals carry a fixed reason and never the token or any part of it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

# FastAPI (via ``tenant_scope``) is imported inside the functions below, not
# here: ``tool_dispatch`` imports this module, and the core library must stay
# importable without the ``[service]`` extra.

logger = logging.getLogger(__name__)

#: The MCP edge scope for this server (``MCP_EDGE_SCOPES`` in
#: ``apps/digithings-stack-cloudflare/src/mcp-edge-auth.ts``).
MCP_SCOPE = "mcp:digivault"


class McpTenantRefused(Exception):
    """The MCP call may not run. ``str(exc)`` is a fixed, token-free reason."""


def verified_tenant_from_bearer(authorization: str | None) -> str | None:
    """Verify a ``Bearer`` digikey JWT and return its ``tenant_slug`` claim.

    Same checks as digisearch's MCP guard (``tenant_index_scope``): signature,
    revocation (the ``jti`` blocklist, failing closed when it is required but
    unreachable) and the ``mcp:digivault`` scope. Any failure is ``None``.
    """
    text = (authorization or "").strip()
    if not text.lower().startswith("bearer "):
        return None
    token = text[7:].strip()
    if not token:
        return None
    try:
        from digikey import blocklist
        from digikey.integrations.service_middleware import digikey_auth_active
        from digikey.jwt_verify import decode_token
        from digikey.scopes import scope_grants_required

        if not digikey_auth_active():
            return None
        claims = decode_token(token)
        if claims.jti:
            blocklist.assert_blocklist_ready()
            if blocklist.is_configured() and blocklist.is_blocked(claims.jti):
                logger.info("digivault MCP: bearer is revoked")
                return None
        if not scope_grants_required(claims.scopes, [MCP_SCOPE]):
            logger.info("digivault MCP: bearer lacks %s", MCP_SCOPE)
            return None
    except Exception:
        logger.info("digivault MCP: bearer did not verify")
        return None
    slug = (claims.tenant_slug or "").strip()
    return slug or None


def resolve_mcp_path_prefix(
    authorization: str | None,
    requested: str | None,
    *,
    verify: Callable[[str | None], str | None] | None = None,
    raw_map: str | None = None,
) -> str | None:
    """The ``path_prefix`` an MCP tool call may use, or :class:`McpTenantRefused`.

    ``verify`` defaults to :func:`verified_tenant_from_bearer`; ``raw_map``
    defaults to the ``DIGI_TENANT_CORPUS_MAP`` env var.
    """
    header = (authorization or "").strip()
    if not header:
        return requested
    from fastapi import HTTPException

    from digivault.tenant_scope import enforce_tenant_path_prefix, mapped_tenant_path_prefix

    if not header.lower().startswith("bearer "):
        logger.info("digivault MCP: refused a non-bearer Authorization header")
        raise McpTenantRefused("unsupported authorization")
    tenant = (verify or verified_tenant_from_bearer)(header)
    if not tenant:
        logger.info("digivault MCP: refused a bearer with no verified tenant")
        raise McpTenantRefused("caller has no verified tenant")
    try:
        mapped = mapped_tenant_path_prefix(tenant, raw_map=raw_map)
        if mapped is None:
            return requested
        if not (requested or "").strip():
            return mapped
        enforce_tenant_path_prefix(tenant, requested, raw_map=raw_map)
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("digivault MCP: tenant corpus map is misconfigured")
            raise McpTenantRefused("tenant corpus map is misconfigured") from exc
        logger.warning(
            "digivault MCP: path_prefix refused",
            extra={"operation": "mcp_tenant_scope", "outcome": "refused"},
        )
        raise McpTenantRefused("path_prefix is not available to this caller") from exc
    return mapped
