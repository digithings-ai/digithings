"""Binds tenant-scoped indexes to the caller's verified tenant (DIG-3585).

``digisearch:query`` proves only that a caller may search at all; the scope
carries no tenant. Without this module ``index_name`` is whatever the request
body, the orchestrator-tool arguments or the MCP tool arguments say, so any
holder of a query-scoped token could read another tenant's corpus by naming
its index.

The ownership comes from ``DIGI_TENANT_CORPUS_MAP``, the same env var
digigraph's ``corpus_routing.py`` and digivault's ``tenant_scope.py`` read. An
index is **claimed** by a tenant when that tenant's entry names it in
``digisearchIndex`` (a comma list) or in ``digisearchTools[*].index``. A claimed
index is **tenant-scoped** unless a public tenant also claims it: the house
tenant's docs corpus is public product documentation and stays open to every
query-scoped caller (``DIGISEARCH_PUBLIC_TENANTS``, default ``digithings``).

A tenant-scoped index is served only when the caller's tenant was verified —
the ``tenant_slug`` claim of a signature-checked digikey JWT — and that tenant
claims the index. An unsigned ``X-Digi-Tenant`` header never counts (#2303).

Like digivault's module, the map is parsed here rather than imported from
digigraph, so digisearch stays installable on its own. Unset map: no-op
(single-tenant installs, local dev). Set but unusable: fail closed with 503,
never silently treated as unset.

Every index name a request carries must match ``^[a-z0-9][a-z0-9_-]{0,63}$``
once normalized (:func:`validate_index_name`). Anything else -- a path segment
such as ``x/../name``, a ``?`` or ``#``, a percent escape, an empty entry in a
comma list -- is refused before any backend sees it, so a name can never steer
a backend URL to another index or action.

Index names compare case-insensitively and with ``-`` and ``_`` treated alike,
so ``tenant-a-tickets`` and ``tenant_a_tickets`` are the same index for this check: a
spelling variant must not be a way around it.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

_MAP_ENV = "DIGI_TENANT_CORPUS_MAP"
_PUBLIC_ENV = "DIGISEARCH_PUBLIC_TENANTS"
_DEFAULT_PUBLIC_TENANTS = "digithings"
#: Required scope for an MCP bearer's tenant claim to count (the MCP edge scope).
_MCP_SCOPE = "mcp:digisearch"
#: The only shape an index name may take once normalized.
INDEX_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class TenantIndexMapError(RuntimeError):
    """``DIGI_TENANT_CORPUS_MAP`` is set but unusable; never treated as unset."""


class IndexNotPermitted(Exception):
    """The caller's verified tenant does not own a tenant-scoped index."""

    def __init__(self, index_name: str) -> None:
        super().__init__(index_name)
        self.index_name = index_name


class InvalidIndexName(ValueError):
    """An index name (or one entry of a comma list) is not a plain index name."""

    def __init__(self, index_name: str) -> None:
        super().__init__(f"invalid index name {index_name!r}")
        self.index_name = index_name


def normalize_index(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def validate_index_name(name: str) -> str:
    """Return ``name`` stripped, or raise :class:`InvalidIndexName`.

    The check runs on the normalized form, so ``Tenant-A`` passes and
    ``x/../name``, ``./name``, ``name/query?``, ``name#`` and ``%2D`` do not.
    """
    if not isinstance(name, str) or not INDEX_NAME_RE.fullmatch(normalize_index(name)):
        raise InvalidIndexName(str(name))
    return name.strip()


def split_indexes(index_name: str | None) -> list[str]:
    """The indexes one request names. A comma list fans out over several."""
    return [part.strip() for part in (index_name or "").split(",") if part.strip()]


def parse_index_list(index_name: str) -> list[str]:
    """The validated indexes of a request's ``index_name`` (a comma list).

    Empty entries are dropped, as :func:`split_indexes` does (``"a,,b"`` is
    ``a`` and ``b``), but a value with no name at all (``""``, ``" , "``) is
    refused rather than left for a caller to replace with a default index.
    Every remaining entry must pass :func:`validate_index_name`.
    """
    if not isinstance(index_name, str):
        raise InvalidIndexName(str(index_name))
    parts = [validate_index_name(part) for part in split_indexes(index_name)]
    if not parts:
        raise InvalidIndexName(index_name)
    return parts


def _claimed_indexes(entry: dict) -> set[str]:
    out: set[str] = set()
    raw = entry.get("digisearchIndex") or entry.get("digisearch_index")
    if isinstance(raw, str):
        out.update(normalize_index(p) for p in split_indexes(raw))
    tools = entry.get("digisearchTools") or entry.get("digisearch_tools")
    if isinstance(tools, dict):
        for spec in tools.values():
            if isinstance(spec, dict) and isinstance(spec.get("index"), str):
                out.update(normalize_index(p) for p in split_indexes(spec["index"]))
    return out


def public_tenants() -> frozenset[str]:
    raw = os.environ.get(_PUBLIC_ENV)
    text = _DEFAULT_PUBLIC_TENANTS if raw is None else raw
    return frozenset(s.strip().lower() for s in text.split(",") if s.strip())


def load_scoped_indexes(raw: str | None = None) -> dict[str, frozenset[str]]:
    """``{normalized index: tenants that own it}`` for every tenant-scoped index.

    Empty when the map is unset. Raises :class:`TenantIndexMapError` when the
    map is set but is not a JSON object with at least one tenant entry.
    """
    text = (raw if raw is not None else os.environ.get(_MAP_ENV) or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TenantIndexMapError(f"{_MAP_ENV} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TenantIndexMapError(f"{_MAP_ENV} must be a JSON object keyed by tenant slug")
    owners: dict[str, set[str]] = {}
    entries = 0
    for slug, value in data.items():
        if not isinstance(slug, str) or not slug.strip() or not isinstance(value, dict):
            logger.warning("%s: skipping invalid entry for slug %r", _MAP_ENV, slug)
            continue
        entries += 1
        for idx in _claimed_indexes(value):
            owners.setdefault(idx, set()).add(slug.strip().lower())
    if not entries:
        raise TenantIndexMapError(f"{_MAP_ENV} is set but has no usable tenant entries")
    public = public_tenants()
    return {idx: frozenset(slugs) for idx, slugs in owners.items() if not slugs & public}


def check_indexes(
    index_names: Iterable[str],
    verified_tenant: str | None,
    *,
    raw_map: str | None = None,
) -> None:
    """Raise :class:`IndexNotPermitted` for the first index the caller may not read.

    ``verified_tenant`` must come from a signature-checked claim, never from a
    header. ``None`` means the caller has no verified tenant. Raises
    :class:`InvalidIndexName` for a malformed name, whether or not a map is set.
    """
    parts = [part for name in index_names for part in parse_index_list(name)]
    scoped = load_scoped_indexes(raw_map)
    if not scoped:
        return
    tenant = (verified_tenant or "").strip().lower()
    for part in parts:
        owners = scoped.get(normalize_index(part))
        if owners is not None and tenant not in owners:
            raise IndexNotPermitted(part)


def verified_tenant_from_request(request: Request) -> str | None:
    """The tenant of the request's verified JWT, or ``None``."""
    ctx = getattr(request.state, "digi_auth", None)
    if ctx is None or not getattr(ctx, "tenant_slug_verified", False):
        return None
    slug = (getattr(ctx, "tenant_slug", "") or "").strip()
    return slug or None


def enforce_request_indexes(request: Request, *index_names: str | None) -> None:
    """HTTP guard: 400 for a malformed name, 403 for an index the caller's tenant
    does not own, 503 for a broken map. ``None`` (no index named) is skipped; an
    empty or blank string is a malformed name, never a default."""
    names = [n for n in index_names if n is not None]
    try:
        check_indexes(names, verified_tenant_from_request(request))
    except InvalidIndexName as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TenantIndexMapError as exc:
        logger.error("tenant index scope unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="tenant index scope is misconfigured") from exc
    except IndexNotPermitted as exc:
        logger.warning(
            "tenant index refused",
            extra={
                "operation": "tenant_index_scope",
                "outcome": "refused",
                "index_name": exc.index_name,
            },
        )
        raise HTTPException(
            status_code=403, detail=f"index {exc.index_name!r} is not available to this caller"
        ) from exc


def verified_tenant_from_bearer(authorization: str | None) -> str | None:
    """Verify a ``Bearer`` digikey JWT and return its ``tenant_slug`` claim.

    Used by the MCP server, which has no auth middleware of its own: the stack
    edge verifies the token and forwards the request with the header intact, and
    the claim is re-read from the signature-checked token here rather than from
    any header the edge or the caller could set.

    The token gets the same checks ``DigiAuthMiddleware.jwt_context`` applies:
    signature, revocation (the ``jti`` blocklist, failing closed when it is
    required but unreachable) and scope (``mcp:digisearch``, the MCP edge scope).
    Any failure is ``None``: the caller then has no verified tenant and every
    tenant-scoped index stays closed.
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
                logger.info("tenant index scope: MCP bearer is revoked")
                return None
        if not scope_grants_required(claims.scopes, [_MCP_SCOPE]):
            logger.info("tenant index scope: MCP bearer lacks %s", _MCP_SCOPE)
            return None
    except Exception:
        logger.info("tenant index scope: MCP bearer did not verify")
        return None
    slug = (claims.tenant_slug or "").strip()
    return slug or None
