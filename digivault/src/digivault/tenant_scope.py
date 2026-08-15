"""Binds digivault's ``path_prefix`` to the caller's authenticated tenant.

``digivault:read``/``digivault:write`` (``path_scopes.py``) prove only that a
caller may use these routes at all — the scope carries no tenant identity.
Without this module, ``path_prefix`` is whatever the request body or
orchestrator-tool arguments say, so any caller holding a valid scope can pick
*any* prefix present in ``D1_DATABASE_MAP``, not just the corpus their own
token was issued for.

A parallel fix for #2265 exists in digigraph's own ``orchestration/builtin.py``
(on a separate, not-yet-merged branch as of this module's own PR #2298) that
will overwrite a model-supplied ``path_prefix`` unconditionally before it ever
reaches this service. Even once merged, that only protects the model ->
digigraph -> digivault leg — a caller that talks to digivault directly (any
holder of a ``digivault:read``-scoped JWT hitting ``/v1/orchestrator_invoke``
or ``/v1/notes/by-path`` itself, bypassing digigraph entirely) is unaffected
by it, regardless of which fix lands first. This module closes that leg,
server-side, independent of digigraph's own state. (On ``develop`` today,
digigraph's own handler is still the older, conditional-default version — see
that module's own ``_handle_digivault_search`` — so this module is currently
the *only* enforcement for a caller going through digigraph too, not just a
defense-in-depth backstop; verify digigraph's actual merged state before
treating its half as done.)

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

**Unset is not the same as broken.** CodeRabbit's review of PR #2298 (this
module's own PR) found the first version conflated the two: invalid JSON, a
non-object top level, or a map whose every entry was individually malformed
all fell back to the *same* empty ``{}`` a genuinely-unset env var produces —
silently treating "an operator turned multi-tenant enforcement on and typo'd
it" as "multi-tenant enforcement was never requested." That is exactly the
failure this deployment's own ``D1_DATABASE_MAP``/``_d1_configured()`` already
guards against for the credential trio (see ``server.py``'s docstring there:
"*some* set and *not all* has no legitimate reading"). The same discipline
applies here: a non-empty ``DIGI_TENANT_CORPUS_MAP`` that fails to produce at
least one usable tenant -> prefix mapping raises ``TenantCorpusMapError``,
which ``enforce_tenant_path_prefix`` turns into a loud ``503`` rather than a
silent pass-through.

**Known residual dependency, not closed by this module.** ``tenant_slug`` is
only as trustworthy as ``request.state.digi_auth`` makes it. Today, digikey's
``DigiAuthMiddleware`` (``service_middleware.py``) falls back to the
caller-supplied, unsigned ``X-Digi-Tenant``/``X-Digichat-Tenant`` header
whenever the JWT's own ``tenant_slug`` claim is empty, with no signal on
``DigiAuthContext`` distinguishing a verified claim from a header override —
a caller holding *any* credential with an empty ``tenant_slug`` and
``digivault:read`` could set that header and defeat this module's check
entirely. Verified this is not reachable through digikey's own issuance API
today (both ``/v1/oauth/token`` grant types require a non-empty
``tenant_slug`` to mint a token at all — see ``digikey/src/digikey/server.py``
lines ~213-234 and ~127) — the one path found is an operator issuing a CLI key
with an empty ``--tenant`` (``digikey/src/digikey/cli.py``), not something an
external caller can trigger. So this is a latent single point of failure, not
an active bypass of any normally-issued credential, but it means digivault's
enforcement is only as strong as an invariant digivault itself cannot see or
verify. Found in the in-session review of this module's own PR #2298; tracked
as #2303 rather than fixed here, since a JWT/auth-trust change is its own
Human Gate item (see CLAUDE.md) independent of this PR's scope.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import HTTPException

from digivault.d1_store import normalize_vault_path

logger = logging.getLogger(__name__)

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"


class TenantCorpusMapError(RuntimeError):
    """``DIGI_TENANT_CORPUS_MAP`` is set but unusable — never silently treated as
    "unset" (which would disable tenant-prefix enforcement without telling anyone)."""


def _load_tenant_prefix_map(raw: str | None = None) -> dict[str, str]:
    """Parse ``DIGI_TENANT_CORPUS_MAP`` down to ``{tenant_slug: vault_path_prefix}``.

    Tolerant of the sibling keys (``digisearchIndex``, ``researchSystemPrompt``)
    digigraph's own copy of this map also carries — only the vault prefix
    matters here. An individual entry with no usable prefix (wrong type, no
    ``vaultPathPrefix``/``vault_path_prefix`` key) is dropped with a warning —
    a typo for one tenant must not by itself take down every other tenant's
    requests. But the env var as a whole is a different story: unset (empty
    string) returns ``{}``, the genuine "tenant binding is off" case; anything
    *set* that ends up producing zero usable entries — invalid JSON, a
    non-object top level, or a dict where every single entry was individually
    dropped — raises ``TenantCorpusMapError`` instead of also returning ``{}``,
    so a broken multi-tenant config can never be mistaken for "no multi-tenant
    config was ever requested" (see this module's docstring).
    """
    text = (raw if raw is not None else os.environ.get(_ENV_VAR) or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TenantCorpusMapError(f"{_ENV_VAR} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TenantCorpusMapError(f"{_ENV_VAR} must be a JSON object keyed by tenant slug")
    out: dict[str, str] = {}
    for slug, value in data.items():
        if not isinstance(slug, str) or not isinstance(value, dict):
            logger.warning("%s: skipping invalid entry for slug %r", _ENV_VAR, slug)
            continue
        prefix = value.get("vaultPathPrefix") or value.get("vault_path_prefix")
        if not prefix:
            logger.warning("%s: entry %r has no vaultPathPrefix", _ENV_VAR, slug)
            continue
        out[slug.strip().lower()] = normalize_vault_path(str(prefix))
    if not out:
        raise TenantCorpusMapError(
            f"{_ENV_VAR} is set but produced no usable tenant -> prefix mappings"
        )
    return out


def mapped_tenant_path_prefix(tenant_slug: str | None, *, raw_map: str | None = None) -> str | None:
    """Return this tenant's vault prefix when ``DIGI_TENANT_CORPUS_MAP`` is set.

    Used to fill an omitted ``path_prefix`` before local-vault / Supabase search so
    a multi-tenant deployment never falls through to an unfiltered corpus read.

    - Map unset → ``None`` (single-tenant; caller keeps omitted-prefix behavior).
    - Map set, tenant known → that tenant's normalized prefix.
    - Map set, tenant unknown / empty → ``HTTPException(403)``.
    - Map set but unusable → ``HTTPException(503)``.
    """
    try:
        table = _load_tenant_prefix_map(raw_map)
    except TenantCorpusMapError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not table:
        return None
    authorized = table.get((tenant_slug or "").strip().lower())
    if authorized is None:
        raise HTTPException(
            status_code=403,
            detail="path_prefix does not match the authenticated tenant's corpus",
        )
    return authorized


def enforce_tenant_path_prefix(
    tenant_slug: str | None, requested_prefix: str | None, *, raw_map: str | None = None
) -> None:
    """Raise ``HTTPException`` if ``requested_prefix`` is not the prefix
    ``DIGI_TENANT_CORPUS_MAP`` binds to ``tenant_slug`` — ``403`` for a real
    mismatch, ``503`` if the map itself is set but unusable.

    A no-op in two cases that must stay cheap and side-effect-free:

    - no prefix was requested yet (``None`` or empty) — the existing
      "path_prefix is required" handling downstream still owns that case;
      this function only judges a prefix that is actually present.
    - the map itself is genuinely unset — single-tenant deployments are
      unaffected.

    Once the map *is* set (and parses to at least one usable entry — see
    ``_load_tenant_prefix_map``), this fails closed:

    - ``tenant_slug`` has no entry in the map — refused; there is no basis to
      authorize any prefix for a tenant this deployment doesn't recognize.
    - the map's prefix for ``tenant_slug`` differs from ``requested_prefix`` —
      refused.

    Comparison is on each side's ``normalize_vault_path`` form (trimmed, no
    leading/trailing slash, at most one trailing ``.md`` stripped) so
    ``"clients/digithings/"`` and ``"clients/digithings"`` count as the same
    prefix. This must be the *same* normalization `resolve_path_prefix` (used
    downstream on the caller's own value) applies — a review of PR #2298 found
    an earlier version of this function used only ``strip().strip("/")`` here,
    which would 403 a legitimate caller whose *stored* map entry carried a
    stray trailing ``.md`` (an operator typo) even though the caller's own,
    correctly-formed request would already have had that same ``.md`` stripped
    by `resolve_path_prefix` before ever reaching this comparison — a
    confusing false refusal, not a bypass, but avoidable by normalizing both
    sides identically.
    """
    if not requested_prefix:
        return
    try:
        table = _load_tenant_prefix_map(raw_map)
    except TenantCorpusMapError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not table:
        return
    authorized = table.get((tenant_slug or "").strip().lower())
    if authorized is None or authorized != normalize_vault_path(requested_prefix):
        raise HTTPException(
            status_code=403,
            detail="path_prefix does not match the authenticated tenant's corpus",
        )
