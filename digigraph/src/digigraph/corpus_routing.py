"""Per-tenant corpus routing for digisearch index + digivault path prefix.

Also the per-tenant **skill document** set (``skills``): a skill pack is tenant
content, so the map — not the filesystem and not a client header — decides which
documents a tenant may read (``tenant_skill_ids``). Unmapped means none.

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

**A known key carrying a bad value fails closed.** ``lockSessionControls``
hides the session model / MCP / tool controls, so a non-boolean value (a
JSON string ``"true"``, ``1``, ``null``) is a safety problem, not a
forward-compatibility problem: the entry is kept and the flag is forced to
**locked**, with a warning naming the tenant slug, the field and the JSON
type (never the value). Dropping the entry is forbidden — a missing entry
defaults to unlocked *and* loses the tenant's corpus routing, which would
re-point the corpus. The digichat registry validator
(``apps/digichat/src/lib/embed-tenants.ts``) rejects the same field with
"lockSessionControls must be a boolean"; both surfaces accept only a real
boolean and differ only in failure model (one registry document versus
per-tenant map entries). See ADR-0035.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from digigraph.skill_library.loader import SKILL_NAME_RE, known_skill_names
from digigraph.web_search_sites import has_web_search_site_graph

logger = logging.getLogger(__name__)

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# One index name, or a comma-separated fan-out list (e.g. "occ_help,occ_tickets",
# #4756): each element follows the single-index shape; empty elements rejected.
_INDEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}(,[a-zA-Z0-9][a-zA-Z0-9._-]{0,127})*$")
# Dedicated per-index digisearch tools (DIG-3269): name -> {index, description}.
_TOOL_NAME = re.compile(r"^digisearch_[a-z0-9_]{1,48}$")
_RESERVED_TOOL_NAMES = frozenset(
    {"digisearch_fetch_all", "digisearch_research_delegate", "digisearch_semantic"}
)
_HEADER_CORPUS_INDEX = "x-digi-corpus-index"
_HEADER_VAULT_PREFIX = "x-digi-vault-prefix"
# Every entry key this parser understands — the camelCase and the snake_case
# spelling of each known field. An entry key outside this set is *ignored*
# (forward compatibility: a newer map may carry fields this build predates),
# but it is never ignored silently. The map is read key by key and the override
# is built from explicit keyword arguments, so an unknown key would otherwise
# vanish with no log line and no error — a renamed or misspelled field would
# look exactly like a working map. DIG-4459 decision note D2 requires a warning
# that names the key; the VALUE of an unknown key is never logged.
_KNOWN_ENTRY_KEYS = frozenset(
    {
        "digisearchIndex",
        "digisearch_index",
        "vaultPathPrefix",
        "vault_path_prefix",
        "researchSystemPrompt",
        "research_system_prompt",
        "lockSessionControls",
        "lock_session_controls",
        # DIG-3269 dedicated per-index digisearch tools. The parser honours
        # both spellings, so both are known keys - an OCC map that carries
        # digisearchTools must not be warned about as unknown.
        "digisearchTools",
        "digisearch_tools",
        # Per-tenant skill documents (DIG-2637). ``skills`` is a list of skill
        # ids this tenant may read; absent, the tenant's own pack
        # (``skill_library/<slug>/``) is the set. An unmapped tenant gets none.
        "skills",
        "skill_ids",
        # Domains this tenant's web_search may reach. Absent: unpinned.
        "webSearchDomains",
        "web_search_domains",
    }
)

# One pin: a hostname, optionally followed by a path prefix. Lowercase labels,
# at least one dot, no scheme, port, query or wildcard. ``example.com`` also
# admits its subdomains; ``example.com/company/acme`` admits only URLs on that
# host (or a subdomain) whose path sits under ``/company/acme``.
_DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_PIN_PATH = re.compile(r"^(/[a-z0-9._~%!$&'()*+,;=:@-]+)+$")
# digisearch's WebSearchRequest takes at most five include_domains.
_MAX_PIN_HOSTS = 5


def _normalize_web_search_pin(value: Any) -> str | None:
    """``host`` or ``host/path`` in canonical form, or ``None`` when invalid."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if not candidate or "://" in candidate or "?" in candidate or "#" in candidate:
        return None
    host, sep, path = candidate.partition("/")
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not _DOMAIN.match(host):
        return None
    path = ("/" + path).rstrip("/") if sep else ""
    if path and not _PIN_PATH.match(path):
        return None
    return host + path


def _parse_web_search_domains(raw: Any, slug: str) -> list[str] | None:
    """Validate ``webSearchDomains``: a list of ``host`` / ``host/path`` pins, or nothing.

    ``None`` (key absent) leaves web_search unpinned. A key that is present but
    unusable fails *closed* to an empty list, which refuses web_search for the
    tenant: widening to the open web after an operator tried to pin it would be
    the one outcome they set the key to prevent. More than five distinct hosts
    also fails closed: digisearch accepts at most five ``include_domains``.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        logger.warning("%s[%s]: webSearchDomains must be a list of hostnames", _ENV_VAR, slug)
        return []
    out: list[str] = []
    for value in raw:
        pin = _normalize_web_search_pin(value)
        if pin is None:
            logger.warning("%s[%s]: skip invalid webSearchDomains entry", _ENV_VAR, slug)
            continue
        if pin not in out:
            out.append(pin)
    if len({p.split("/", 1)[0] for p in out}) > _MAX_PIN_HOSTS:
        logger.warning(
            "%s[%s]: webSearchDomains names more than %d hosts; web_search refused",
            _ENV_VAR,
            slug,
            _MAX_PIN_HOSTS,
        )
        return []
    return out


def _parse_skill_ids(raw: Any, slug: str) -> list[str] | None:
    """Validate the ``skills`` key: a list of kebab-case ids, or nothing.

    ``None`` (key absent) means "the tenant's own pack", which is what lets the
    ``occ`` map entry keep its four documents without restating them. A key that
    is present but unusable fails *closed* to an empty list: falling back to the
    pack after an operator tried to narrow the set would serve exactly the ids
    they meant to remove.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        # A bare string is read as a one-id shorthand; anything with a slash,
        # dot or space in it is a mistake, not an id.
        raw = [raw]
    if not isinstance(raw, list):
        logger.warning("%s[%s]: skills must be a list of skill ids", _ENV_VAR, slug)
        return []
    out: list[str] = []
    for value in raw:
        candidate = value.strip().lower() if isinstance(value, str) else ""
        if not candidate or not SKILL_NAME_RE.match(candidate):
            logger.warning("%s[%s]: skip invalid skill id %r", _ENV_VAR, slug, value)
            continue
        if candidate not in out:
            out.append(candidate)
    return out


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
    digisearch_tools: dict[str, dict[str, str]] | None = Field(
        default=None,
        description="Dedicated digisearch tools for this tenant: tool name -> "
        "{index, description}. When set, the generic digisearch tools are hidden and "
        "each named tool queries only its own index (the model picks the tool).",
    )
    lock_session_controls: bool = Field(
        default=False,
        description="Hide model/MCP/tool session controls (session_set_model, "
        "session_upsert_mcp, session_remove_mcp, session_toggle_tool) from this tenant",
    )
    skills: list[str] | None = Field(
        default=None,
        description="Skill document ids this tenant may read (DIG-2637). None means "
        "the tenant's own pack (skill_library/<slug>/); a list narrows that pack, "
        "and an empty list means no skills at all.",
    )
    web_search_domains: list[str] | None = Field(
        default=None,
        description="Pins this tenant's web_search is held to: ``host`` (admits its "
        "subdomains) or ``host/path`` (only URLs under that path). None leaves "
        "web_search unpinned; an empty list refuses it.",
    )
    web_search_site: str | None = Field(
        default=None,
        description="Id of the repo-shipped site graph appended to this tenant's "
        "web_search tool description (web_search_sites/<id>.md). Set "
        "only for a pinned tenant whose slug has a file there; never from the client.",
    )


def _parse_digisearch_tools(raw: Any, slug: str) -> dict[str, dict[str, str]] | None:
    """Validate ``digisearchTools``; invalid entries are dropped with a warning."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        logger.warning("%s[%s]: digisearchTools must be an object", _ENV_VAR, slug)
        return None
    out: dict[str, dict[str, str]] = {}
    for name, spec in raw.items():
        if (
            not isinstance(name, str)
            or not _TOOL_NAME.match(name)
            or name in _RESERVED_TOOL_NAMES
            or not isinstance(spec, dict)
        ):
            logger.warning("%s[%s]: skip invalid digisearch tool %r", _ENV_VAR, slug, name)
            continue
        index = str(spec.get("index") or "").strip()
        description = str(spec.get("description") or "").strip()
        if not index or "," in index or not _INDEX.match(index) or not description:
            logger.warning(
                "%s[%s]: skip digisearch tool %r (index/description)", _ENV_VAR, slug, name
            )
            continue
        out[name] = {"index": index, "description": description}
    return out or None


def _normalize_prefix(raw: str) -> str:
    return raw.strip().strip("/")


def _parse_map(raw: str | None) -> dict[str, TenantCorpusOverride]:
    """Parse the corpus map JSON.

    Genuinely unset / empty → ``{}`` (single-tenant; headers may select corpus).
    Set but unusable (bad JSON, non-object, or every entry dropped) →
    ``TenantCorpusMapError`` — same discipline as digivault ``tenant_scope``.

    An entry key this build does not know is ignored, but it is warned about
    (tenant slug + key names, never values) rather than dropped in silence.
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
        unknown_keys = sorted(str(key) for key in value if key not in _KNOWN_ENTRY_KEYS)
        if unknown_keys:
            # Key names only, never values (DIG-4569 / DIG-4459 note D2).
            logger.warning(
                "%s[%s]: ignoring unknown key(s): %s",
                _ENV_VAR,
                normalized_slug,
                ", ".join(unknown_keys),
            )
        idx = value.get("digisearchIndex") or value.get("digisearch_index")
        prefix = value.get("vaultPathPrefix") or value.get("vault_path_prefix")
        prompt = value.get("researchSystemPrompt") or value.get("research_system_prompt")
        lock = value.get("lockSessionControls", value.get("lock_session_controls", False))
        tools = _parse_digisearch_tools(
            value.get("digisearchTools") or value.get("digisearch_tools"), normalized_slug
        )
        skills = _parse_skill_ids(value.get("skills", value.get("skill_ids")), normalized_slug)
        web_domains = _parse_web_search_domains(
            value.get("webSearchDomains", value.get("web_search_domains")), normalized_slug
        )
        if not isinstance(lock, bool):
            # A known key carrying a bad value is a safety problem, not a
            # forward-compatibility problem: fail closed to LOCKED for this
            # entry and say so loudly. The offending VALUE is never logged.
            logger.warning(
                "%s[%s]: lockSessionControls must be a boolean, got %s - failing closed to locked",
                _ENV_VAR,
                normalized_slug,
                type(lock).__name__,
            )
            lock = True
        try:
            out[normalized_slug] = TenantCorpusOverride(
                digisearch_index=str(idx).strip() if idx else None,
                vault_path_prefix=_normalize_prefix(str(prefix)) if prefix else None,
                research_system_prompt=str(prompt).strip() if prompt else None,
                lock_session_controls=lock,
                digisearch_tools=tools,
                skills=skills,
                web_search_domains=web_domains,
                web_search_site=(
                    normalized_slug
                    if web_domains and has_web_search_site_graph(normalized_slug)
                    else None
                ),
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


def tenant_skill_ids(
    tenant_slug: str | None,
    corpus_map: dict[str, TenantCorpusOverride] | None = None,
) -> tuple[str, ...]:
    """The skill document ids one tenant may read — and nothing for anyone else.

    Skills are tenant content (DIG-2637): the ``occ`` documents are the ``occ``
    tenant's, and the house chat must not receive them. So the set comes from
    the tenant's own map entry only:

    * the slug is unmapped, absent, or not a slug → ``()``. Unmapped is empty,
      never "every document in the tree"; a single-tenant deployment with no map
      gets no skills at all until someone maps one.
    * the entry names ``skills`` → exactly those ids, narrowed to the ones that
      actually exist in the pack (a stale id is drift, not a crash).
    * the entry names no ``skills`` → the tenant's own pack
      (``skill_library/<slug>/``), which for ``occ`` is the four documents and
      for every other tenant is nothing.

    The map is authoritative here for the same reason it is for the corpus: a
    client cannot pick its own skill set.
    """
    slug = (tenant_slug or "").strip().lower()
    if not slug or not _SLUG.match(slug):
        return ()
    table = corpus_map if corpus_map is not None else load_tenant_corpus_map()
    if not table:
        return ()
    entry = table.get(slug)
    if entry is None:
        return ()
    available = known_skill_names(slug)
    if entry.skills is None:
        return tuple(available)
    return tuple(name for name in entry.skills if name in available)


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
    # The tenant is the verified auth tenant only (the caller passes
    # tenant_from_auth). The unsigned X-Digi-Tenant header is never read: with
    # a map set, a token with no tenant claim gets no tenant corpus instead of
    # whichever tenant the header names (#2303, DIG-3585).
    slug = (tenant_slug or "").strip().lower() or None

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
            lock_session_controls=mapped.lock_session_controls,
            digisearch_tools=mapped.digisearch_tools,
            skills=mapped.skills,
            web_search_domains=mapped.web_search_domains,
            web_search_site=mapped.web_search_site,
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
