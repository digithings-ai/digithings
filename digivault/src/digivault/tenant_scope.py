"""Binds digivault's ``path_prefix`` to the caller's authenticated tenant.

``digivault:read``/``digivault:write`` (``path_scopes.py``) prove only that a
caller may use these routes at all — the scope carries no tenant identity.
Without this module, ``path_prefix`` is whatever the request body or
orchestrator-tool arguments say, so any caller holding a valid scope can pick
*any* prefix present in ``D1_DATABASE_MAP``, not just the corpus their own
token was issued for. digigraph's own #2265 fix (``orchestration/builtin.py``)
now overwrites a model-supplied ``path_prefix`` unconditionally before it ever
reaches this service — but that only protects the model -> digigraph ->
digivault leg. A caller that talks to digivault directly (any holder of a
``digivault:read``-scoped JWT hitting ``/v1/orchestrator_invoke`` or
``/v1/notes/by-path`` itself, bypassing digigraph entirely) is unaffected by
digigraph's fix. This module closes exactly that residual gap, server-side.

``DIGI_TENANT_CORPUS_MAP`` is the same env var digigraph's own
``corpus_routing.py`` already reads (mapping ``tenant_slug`` to
``vaultPathPrefix``/``digisearchIndex``), already deployed today for the
digithings/occ split (see ``frontend/digithings-stack-cloudflare/wrangler.toml``).
It is parsed independently here rather than imported from the digigraph
package, so digivault stays installable and runnable on its own — no service
in this repo imports another service's package as a runtime dependency.

When the map is unset entirely, tenant binding is a no-op: single-tenant
deployments (local dev, a self-hosted single-vault install, most of this
service's own test suite) never set it and see no behavior change. Once it
*is* set, enforcement fails closed — see ``enforce_tenant_path_prefix``.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"


def _load_tenant_prefix_map(raw: str | None = None) -> dict[str, str]:
    """Parse ``DIGI_TENANT_CORPUS_MAP`` down to ``{tenant_slug: vault_path_prefix}``.

    Tolerant of the sibling keys (``digisearchIndex``, ``researchSystemPrompt``)
    digigraph's own copy of this map also carries — only the vault prefix
    matters here. Malformed JSON, a non-object entry, or an entry with no
    prefix are each dropped with a warning rather than raised: a config typo
    for one tenant must not take down every other tenant's requests, and this
    must never be able to crash a request or service startup.
    """
    text = (raw if raw is not None else os.environ.get(_ENV_VAR) or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("%s is not valid JSON: %s", _ENV_VAR, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s must be a JSON object keyed by tenant slug", _ENV_VAR)
        return {}
    out: dict[str, str] = {}
    for slug, value in data.items():
        if not isinstance(slug, str) or not isinstance(value, dict):
            continue
        prefix = value.get("vaultPathPrefix") or value.get("vault_path_prefix")
        if prefix:
            out[slug.strip().lower()] = str(prefix).strip().strip("/")
    return out


def enforce_tenant_path_prefix(
    tenant_slug: str | None, requested_prefix: str | None, *, raw_map: str | None = None
) -> None:
    """Raise ``HTTPException(403)`` if ``requested_prefix`` is not the prefix
    ``DIGI_TENANT_CORPUS_MAP`` binds to ``tenant_slug``.

    A no-op in two cases that must stay cheap and side-effect-free:

    - no prefix was requested yet (``None`` or empty) — the existing
      "path_prefix is required" handling downstream still owns that case;
      this function only judges a prefix that is actually present.
    - the map itself is unset — single-tenant deployments are unaffected.

    Once the map *is* set, this fails closed:

    - ``tenant_slug`` has no entry in the map — refused; there is no basis to
      authorize any prefix for a tenant this deployment doesn't recognize.
    - the map's prefix for ``tenant_slug`` differs from ``requested_prefix`` —
      refused.

    Comparison is on each side's normalized form (``strip().strip("/")``) so
    ``"clients/digithings/"`` and ``"clients/digithings"`` count as the same
    prefix, matching ``resolve_path_prefix``'s own normalization elsewhere in
    this service.
    """
    if not requested_prefix:
        return
    table = _load_tenant_prefix_map(raw_map)
    if not table:
        return
    authorized = table.get((tenant_slug or "").strip().lower())
    if authorized is None or authorized != requested_prefix.strip().strip("/"):
        raise HTTPException(
            status_code=403,
            detail="path_prefix does not match the authenticated tenant's corpus",
        )
