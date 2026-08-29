"""Per-tenant corpus routing for digisearch index + digivault path prefix.

Resolves overrides from ``DIGI_TENANT_CORPUS_MAP`` (keyed by tenant slug) and,
only when that map is unset, from request headers / body-driven callers.

When the map is configured (multi-tenant isolation mode), it is **authoritative**:
client headers ``X-Digi-Corpus-Index`` / ``X-Digi-Vault-Prefix`` must not select
another tenant's corpus. digivault already enforces the vault half server-side
(``enforce_tenant_path_prefix``); digisearch has no equivalent bind, so digigraph
must not forward an attacker-chosen index. Used so digithings.ai/chat and
/chat/occ share one digigraph process without corpus bleed.

**Unset is not the same as broken.** digivault's ``tenant_scope`` already fails
closed (``TenantCorpusMapError`` → HTTP 503) when the env var is set but
unusable. digigraph must do the same: a broken map used to parse to ``{}`` and
re-enable client corpus selection — the exact CWE-639 bypass ``#2366`` closed
for a *valid* map. Invalid JSON, a non-object top level, or a map whose every
entry is individually dropped therefore raises ``TenantCorpusMapError`` here
too, never silently "map unset."
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_INDEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_HEADER_CORPUS_INDEX = "x-digi-corpus-index"
_HEADER_VAULT_PREFIX = "x-digi-vault-prefix"
_HEADER_TENANT = "x-digi-tenant"


class TenantCorpusMapError(RuntimeError):
    """``DIGI_TENANT_CORPUS_MAP`` is set but unusable — never silently treated as
    "unset" (which would re-enable client corpus headers without telling anyone)."""


class TenantCorpusOverride(BaseModel):
    """Optional digisearch index and/or digivault path prefix for one tenant."""

    model_config = ConfigDict(extra="forbid")

    digisearch_index: str | None = Field(default=None, description="digisearch index_name override")
    vault_path_prefix: str | None = Field(
        default=None, description="digivault vault_path prefix (no leading/trailing slash)"
    )
    research_system_prompt: str | None = Field(
        default=None, description="Optional research system prompt override"
    )


def _normalize_prefix(raw: str) -> str:
    return raw.strip().strip("/")


def _parse_map(raw: str | None) -> dict[str, TenantCorpusOverride]:
    """Parse the corpus map JSON.

    Genuinely unset / empty → ``{}`` (single-tenant; headers may select corpus).
    Set but unusable (bad JSON, non-object, or every entry dropped) →
    ``TenantCorpusMapError`` — same discipline as digivault ``tenant_scope``.
    """
    text = (raw if raw is not None else "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TenantCorpusMapError(f"{_ENV_VAR} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TenantCorpusMapError(f"{_ENV_VAR} must be a JSON object keyed by tenant slug")
    out: dict[str, TenantCorpusOverride] = {}
    for slug, value in data.items():
        # Lowercase before the slug regex so ``OCC`` matches digivault's
        # ``slug.strip().lower()`` keys and does not empty the whole map.
        if not isinstance(slug, str):
            logger.warning("%s: skip invalid slug %r", _ENV_VAR, slug)
            continue
        normalized_slug = slug.strip().lower()
        if not _SLUG.match(normalized_slug):
            logger.warning("%s: skip invalid slug %r", _ENV_VAR, slug)
            continue
        if not isinstance(value, dict):
            logger.warning("%s[%s]: entry must be an object", _ENV_VAR, normalized_slug)
            continue
        idx = value.get("digisearchIndex") or value.get("digisearch_index")
        prefix = value.get("vaultPathPrefix") or value.get("vault_path_prefix")
        prompt = value.get("researchSystemPrompt") or value.get("research_system_prompt")
        try:
            out[normalized_slug] = TenantCorpusOverride(
                digisearch_index=str(idx).strip() if idx else None,
                vault_path_prefix=_normalize_prefix(str(prefix)) if prefix else None,
                research_system_prompt=str(prompt).strip() if prompt else None,
            )
        except Exception as exc:
            logger.warning("%s[%s]: %s", _ENV_VAR, normalized_slug, exc)
    if not out:
        raise TenantCorpusMapError(
            f"{_ENV_VAR} is set but produced no usable tenant corpus mappings"
        )
    return out


def load_tenant_corpus_map(
    raw: str | None = None,
) -> dict[str, TenantCorpusOverride]:
    """Parse ``DIGI_TENANT_CORPUS_MAP`` (or provided raw JSON).

    Returns ``{}`` only when the map is genuinely unset/empty. A set-but-broken
    value raises ``TenantCorpusMapError`` (callers surface HTTP 503).
    """
    return _parse_map(raw if raw is not None else os.environ.get(_ENV_VAR))


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    get = getattr(headers, "get", None)
    if not callable(get):
        return None
    val = get(name) or get(name.title()) or get(name.upper())
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def resolve_corpus_override(
    *,
    headers: Any = None,
    tenant_slug: str | None = None,
    corpus_map: dict[str, TenantCorpusOverride] | None = None,
) -> TenantCorpusOverride:
    """Resolve corpus overrides for one request.

    * When ``DIGI_TENANT_CORPUS_MAP`` (or *corpus_map*) is non-empty, the map is
      authoritative for the authenticated tenant slug. Client corpus headers are
      ignored so a digithings principal cannot select ``occ_help`` via
      ``X-Digi-Corpus-Index`` (CWE-639). Unknown / empty tenant → no corpus
      override (callers must not fall through to a client-supplied index).
    * When the map is unset (single-tenant), headers may still select index /
      prefix — the historical digichat embed path for deployments without a map.
    * A set-but-broken env map raises ``TenantCorpusMapError`` from
      ``load_tenant_corpus_map`` (never treated as unset). Callers that pass an
      explicit *corpus_map* own that contract themselves.
    """
    hdr_index = _header(headers, _HEADER_CORPUS_INDEX)
    hdr_prefix = _header(headers, _HEADER_VAULT_PREFIX)
    hdr_tenant = _header(headers, _HEADER_TENANT)
    # Prefer the verified auth tenant (caller passes tenant_from_auth). The
    # unsigned X-Digi-Tenant header is only a routing hint when auth did not
    # supply a slug — never used to *authorize* a mapped corpus when auth
    # already named a different tenant (see digivault tenant_scope / #2303).
    slug = (tenant_slug or hdr_tenant or "").strip().lower() or None

    table = corpus_map if corpus_map is not None else load_tenant_corpus_map()
    if table:
        if not slug:
            if hdr_index or hdr_prefix:
                logger.warning(
                    "ignoring corpus headers without a tenant slug while "
                    "DIGI_TENANT_CORPUS_MAP is set"
                )
            return TenantCorpusOverride()
        mapped = table.get(slug)
        if mapped is None:
            if hdr_index or hdr_prefix:
                logger.warning(
                    "ignoring corpus headers for unmapped tenant %r while "
                    "DIGI_TENANT_CORPUS_MAP is set",
                    slug,
                )
            return TenantCorpusOverride()
        index = mapped.digisearch_index
        if index and not _INDEX.match(index):
            logger.warning("ignoring invalid corpus index %r from tenant map", index)
            index = None
        if (hdr_index and hdr_index != index) or (
            hdr_prefix and _normalize_prefix(hdr_prefix) != (mapped.vault_path_prefix or "")
        ):
            logger.warning(
                "ignoring client corpus headers for tenant %r; map is authoritative",
                slug,
            )
        return TenantCorpusOverride(
            digisearch_index=index,
            vault_path_prefix=mapped.vault_path_prefix,
            research_system_prompt=mapped.research_system_prompt,
        )

    # Single-tenant (map unset): headers may select corpus.
    index = hdr_index
    prefix = _normalize_prefix(hdr_prefix) if hdr_prefix else None
    if index and not _INDEX.match(index):
        logger.warning("ignoring invalid corpus index %r", index)
        index = None
    return TenantCorpusOverride(
        digisearch_index=index,
        vault_path_prefix=prefix or None,
        research_system_prompt=None,
    )
