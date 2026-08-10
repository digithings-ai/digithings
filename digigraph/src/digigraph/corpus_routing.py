"""Per-tenant corpus routing for digisearch index + digivault path prefix.

Resolves overrides from request headers (preferred) or ``DIGI_TENANT_CORPUS_MAP``
JSON keyed by tenant slug. Used so digithings.ai/chat and /chat/occ share one
digigraph process without corpus bleed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_INDEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_HEADER_CORPUS_INDEX = "x-digi-corpus-index"
_HEADER_VAULT_PREFIX = "x-digi-vault-prefix"
_HEADER_TENANT = "x-digi-tenant"


class TenantCorpusOverride(BaseModel):
    """Optional digisearch index and/or digivault path prefix for one tenant."""

    model_config = ConfigDict(extra="forbid")

    digisearch_index: str | None = Field(
        default=None, description="digisearch index_name override"
    )
    vault_path_prefix: str | None = Field(
        default=None, description="digivault vault_path prefix (no leading/trailing slash)"
    )
    research_system_prompt: str | None = Field(
        default=None, description="Optional research system prompt override"
    )


def _normalize_prefix(raw: str) -> str:
    return raw.strip().strip("/")


def _parse_map(raw: str | None) -> dict[str, TenantCorpusOverride]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("DIGI_TENANT_CORPUS_MAP is not valid JSON: %s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("DIGI_TENANT_CORPUS_MAP must be a JSON object keyed by tenant slug")
        return {}
    out: dict[str, TenantCorpusOverride] = {}
    for slug, value in data.items():
        if not isinstance(slug, str) or not _SLUG.match(slug):
            logger.warning("DIGI_TENANT_CORPUS_MAP: skip invalid slug %r", slug)
            continue
        if not isinstance(value, dict):
            logger.warning("DIGI_TENANT_CORPUS_MAP[%s]: entry must be an object", slug)
            continue
        idx = value.get("digisearchIndex") or value.get("digisearch_index")
        prefix = value.get("vaultPathPrefix") or value.get("vault_path_prefix")
        prompt = value.get("researchSystemPrompt") or value.get("research_system_prompt")
        try:
            out[slug] = TenantCorpusOverride(
                digisearch_index=str(idx).strip() if idx else None,
                vault_path_prefix=_normalize_prefix(str(prefix)) if prefix else None,
                research_system_prompt=str(prompt).strip() if prompt else None,
            )
        except Exception as exc:
            logger.warning("DIGI_TENANT_CORPUS_MAP[%s]: %s", slug, exc)
    return out


def load_tenant_corpus_map(
    raw: str | None = None,
) -> dict[str, TenantCorpusOverride]:
    """Parse ``DIGI_TENANT_CORPUS_MAP`` (or provided raw JSON)."""
    return _parse_map(raw if raw is not None else os.environ.get("DIGI_TENANT_CORPUS_MAP"))


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
    """Resolve corpus overrides: headers win, then map entry for tenant slug."""
    hdr_index = _header(headers, _HEADER_CORPUS_INDEX)
    hdr_prefix = _header(headers, _HEADER_VAULT_PREFIX)
    hdr_tenant = _header(headers, _HEADER_TENANT)
    slug = (tenant_slug or hdr_tenant or "").strip().lower() or None

    mapped = TenantCorpusOverride()
    if slug:
        table = corpus_map if corpus_map is not None else load_tenant_corpus_map()
        mapped = table.get(slug) or TenantCorpusOverride()

    index = hdr_index or mapped.digisearch_index
    prefix = _normalize_prefix(hdr_prefix) if hdr_prefix else mapped.vault_path_prefix
    if index and not _INDEX.match(index):
        logger.warning("ignoring invalid corpus index %r", index)
        index = None
    return TenantCorpusOverride(
        digisearch_index=index,
        vault_path_prefix=prefix or None,
        research_system_prompt=mapped.research_system_prompt,
    )
