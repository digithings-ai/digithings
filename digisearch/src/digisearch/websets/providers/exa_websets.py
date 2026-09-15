"""EXA Websets Pro shim — dormant without ``EXA_API_KEY`` (#4066, Task 7).

EXA's websets verify + enrich API is paywalled on the operator's current key
tier: a live probe of the same key returned ``401: Upgrade to a Pro plan`` while
plain ``/search`` worked (the provider capability matrix in
``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``).
The OSS websets path ships first and is what the HTTP/MCP/orchestrator surfaces
call; this module is the *drop-in paid alternative*: it translates OSS webset
requests into EXA Websets calls and normalizes responses back into the OSS
object shapes from :mod:`digisearch.websets.models`, so a caller holding a Pro
key can select it explicitly without changing the object contract.

Dormant-by-default (same fail-closed pattern as :mod:`digisearch.web_exa`):
every entry point reads ``EXA_API_KEY`` at call time and raises
:class:`~digisearch.web_exa.ExaNotConfiguredError` when it is unset; no import
side effects, no key stored on a client object.

Typed paywall distinction
-------------------------
``ExaNotConfiguredError`` means "no key"; EXA's Pro-plan 401 is mapped to
:class:`ExaWebsetsProRequiredError` — declared as a **subclass** of the landed
``digisearch.web_exa.ExaError`` (never a sibling), so every existing
``except ExaError`` handler (``server.py``, ``mcp_server.py``) keeps catching it
with unchanged meaning while callers can distinguish "tier paywalled" from
"key missing". The landed Phase C monitor adapter maps the same paywall to
``ExaAdapterError("exa_tier_gated")``; this is the websets-side equivalent.

Request/response shapes (recorded from the published EXA Websets OpenAPI — the
translation ships blind until a Pro key is exercised; live re-validation is
tracked by the #4123 live-pin precedent and the Task 8 record):

- Base path: ``https://api.exa.ai/websets/v0``; auth via ``x-api-key`` header
  (``Authorization: Bearer`` also accepted by EXA; the shim sends ``x-api-key``
  like the landed ``web_exa`` transport).
- Create: ``POST /websets`` body
  ``{"search": {"query": str, "count": int,
  "criteria": [{"description": str}]}, "enrichments":
  [{"description": str, "format": enum, "options": [{"label": str}]}],
  "externalId": str}`` → 201 ``Webset``.
- Read: ``GET /websets/{id}`` → 200 ``Webset``.
- Add search: ``POST /websets/{id}/searches`` body
  ``{"query": str, "count": int, "criteria": [{"description": str}]}`` →
  ``WebsetSearch``.
- 401/403 bodies observed on the free-tier key are the vendored fixture
  ``tests/ds/fixtures/websets/exa_401_pro_required.json``
  (``{"error": "Upgrade to a Pro plan"}``; request id
  ``97792aab5a5323b7e4c74a5381d9ce7e`` for the s5 sample at
  ``tests/ds/fixtures/websets/s5_category_company.json``).
- ``Webset.status`` enum (EXA): ``idle | pending | running | paused`` — there is
  no EXA webset-level failure/cancel; the shim maps ``pending`` → OSS
  ``running`` and ``paused`` → OSS ``idle`` (no OSS pause state).
- ``WebsetSearch.status`` enum (EXA): ``created | pending | running | completed
  | canceled`` — mapped to OSS ``running`` / ``idle`` / ``cancelled``.

Recorded normalization decisions (v1):
- EXA ids are kept when they already match the OSS id patterns
  (``ws_<32 hex>`` / ``wss_<32 hex>``); any other vendor id is mapped
  deterministically through ``uuid5`` so repeated reads of the same EXA object
  yield the same OSS id. Wire-format round-tripping of the raw vendor id needs
  an external-id field on the OSS models — deferred until a Pro key exists.
- OSS ``company_profile`` enrichments are sent as EXA ``format: "text"`` (EXA
  has no company-profile enum member); everything else maps 1:1.
- Criteria map by their natural-language ``rule`` (OSS) ↔ ``description`` (EXA);
  a search response with no criteria raises ``ExaError`` rather than inventing
  an admission rule the OSS model could not represent.
- Item/event/webhook normalization is **not** implemented in v1: the shim covers
  the create/read/refresh request path only, and the HTTP/MCP surfaces keep
  serving items/events from the OSS store. Enabling the shim end-to-end is a
  follow-up after Pro-key validation.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import ValidationError

from digisearch.web_exa import EXA_ENV_VAR, ExaError, ExaNotConfiguredError
from digisearch.websets.models import (
    EnrichmentDef,
    VerificationCriterion,
    Webset,
    WebsetSearch,
)

__all__ = [
    "EXA_WEBSETS_API_BASE",
    "ExaWebsetsProRequiredError",
    "add_search",
    "create_webset",
    "get_webset",
    "is_exa_websets_configured",
]

EXA_WEBSETS_API_BASE = "https://api.exa.ai/websets/v0"
EXA_WEBSETS_TIMEOUT_S = 30.0

_WEBSET_ID_RE = re.compile(r"^ws_[0-9a-f]{32}$")
_SEARCH_ID_RE = re.compile(r"^wss_[0-9a-f]{32}$")

#: EXA webset status → OSS webset status (no OSS pause state: paused → idle).
_WEBSET_STATUS: dict[str, str] = {
    "idle": "idle",
    "pending": "running",
    "running": "running",
    "paused": "idle",
}

#: EXA search status → OSS search status.
_SEARCH_STATUS: dict[str, str] = {
    "created": "running",
    "pending": "running",
    "running": "running",
    "completed": "idle",
    "canceled": "cancelled",
}

#: EXA enrichment status → OSS enrichment status.
_ENRICHMENT_STATUS: dict[str, str] = {
    "pending": "running",
    "completed": "idle",
    "canceled": "failed",
}

#: OSS enrichment types with no EXA enum member (sent as ``text``).
_EXA_ENRICHMENT_FORMATS = frozenset({"text", "date", "number", "options", "email", "phone", "url"})
_TEXT_FALLBACK_TYPES = frozenset({"company_profile"})


class ExaWebsetsProRequiredError(ExaError):
    """EXA answered 401/403 with the Pro-plan paywall (``Upgrade to a Pro plan``).

    A subclass of :class:`digisearch.web_exa.ExaError`, so existing
    ``except ExaError`` handlers keep catching it; callers that need to tell
    "tier paywalled" from "key missing" (``ExaNotConfiguredError``) can catch
    this class first.
    """


def is_exa_websets_configured() -> bool:
    """True when ``EXA_API_KEY`` is present (non-empty after strip)."""
    return bool(os.environ.get(EXA_ENV_VAR, "").strip())


def _api_key(explicit: str | None = None) -> str:
    key = (explicit or os.environ.get(EXA_ENV_VAR, "")).strip()
    if not key:
        raise ExaNotConfiguredError(
            f"{EXA_ENV_VAR} is not set — the EXA Websets shim is disabled. "
            f"Set {EXA_ENV_VAR} (Pro tier) to enable it."
        )
    return key


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    *,
    api_key: str,
) -> dict[str, Any]:
    """Send one EXA Websets request, mapping the fail-closed error vocabulary.

    Transport failures and non-JSON/too-short bodies raise
    :class:`~digisearch.web_exa.ExaError`; the Pro-plan 401/403 body raises
    :class:`ExaWebsetsProRequiredError`.
    """
    url = f"{EXA_WEBSETS_API_BASE}{path}"
    try:
        response = httpx.request(
            method,
            url,
            json=payload,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            timeout=EXA_WEBSETS_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ExaError(f"EXA websets request failed: {exc}") from exc
    if response.status_code in (401, 403):
        body = response.text.strip()
        if "pro plan" in body.lower():
            raise ExaWebsetsProRequiredError(
                f"EXA Websets requires a Pro plan (HTTP {response.status_code}): {body[:200]}"
            )
        raise ExaError("EXA rejected the API key (401/403) — check EXA_API_KEY.")
    if response.status_code == 429:
        raise ExaError("EXA websets rate limited this key (429) — back off and retry.")
    if response.status_code >= 400:
        raise ExaError(f"EXA websets {path} failed ({response.status_code}): {response.text[:500]}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ExaError(f"EXA websets {path} returned non-JSON") from exc
    if not isinstance(data, dict):
        raise ExaError(f"EXA websets {path} returned unexpected shape")
    return data


# ── translation helpers ───────────────────────────────────────────────────────


def _rules(
    criteria: Sequence[VerificationCriterion | Mapping[str, Any]] | None,
) -> list[VerificationCriterion]:
    parsed: list[VerificationCriterion] = []
    for criterion in criteria or ():
        if isinstance(criterion, VerificationCriterion):
            parsed.append(criterion)
        else:
            parsed.append(VerificationCriterion.model_validate(dict(criterion)))
    return parsed


def _exa_criteria(rules: Sequence[VerificationCriterion]) -> list[dict[str, str]]:
    return [{"description": rule.rule} for rule in rules]


def _exa_enrichments(
    enrichments: Sequence[EnrichmentDef | Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    body: list[dict[str, Any]] = []
    for enrichment in enrichments or ():
        definition = (
            enrichment
            if isinstance(enrichment, EnrichmentDef)
            else EnrichmentDef.model_validate(dict(enrichment))
        )
        fmt = definition.type if definition.type in _EXA_ENRICHMENT_FORMATS else "text"
        entry: dict[str, Any] = {
            "description": definition.description or definition.name,
            "format": fmt,
        }
        if definition.options:
            entry["options"] = [{"label": option} for option in definition.options]
        body.append(entry)
    return body


def _derive_id(prefix: str, raw: object, *, pattern: re.Pattern[str]) -> str:
    """Keep a vendor id matching the OSS pattern, else derive a stable uuid5 id.

    The OSS id patterns are strict (``{prefix}_<32 hex>``); EXA ids are not
    guaranteed to match. Deriving through ``uuid5`` keeps repeated reads of the
    same EXA object stable. See the module docstring for the deferred
    external-id round-trip.
    """
    candidate = str(raw or "").strip()
    if pattern.fullmatch(candidate):
        return candidate
    if not candidate:
        return f"{prefix}_{uuid.uuid4().hex}"
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, f'exa-websets:{candidate}').hex}"


def _webset_status(raw: object) -> str:
    """Map an EXA webset status; an unknown value stays ``running`` (never idle)."""
    return _WEBSET_STATUS.get(str(raw or "").strip().lower(), "running")


def _search_status(raw: object) -> str:
    """Map an EXA search status; an unknown value stays ``running``."""
    return _SEARCH_STATUS.get(str(raw or "").strip().lower(), "running")


def _criteria_from_payload(payload: Mapping[str, Any]) -> list[VerificationCriterion]:
    """Mirror EXA ``criteria[].description`` findings onto OSS criteria."""
    entries = payload.get("criteria")
    rules: list[VerificationCriterion] = []
    if isinstance(entries, list):
        for entry in entries:
            description = ""
            if isinstance(entry, Mapping):
                description = str(entry.get("description") or "").strip()
            if description:
                rules.append(VerificationCriterion(name=description[:120], rule=description[:500]))
    return rules


def _normalize_search(
    payload: Mapping[str, Any],
    *,
    webset_id: str,
    fallback_criteria: Sequence[VerificationCriterion] | None = None,
) -> WebsetSearch:
    """Normalize one EXA ``WebsetSearch`` payload into the OSS shape."""
    rules = list(fallback_criteria or ()) or _criteria_from_payload(payload)
    if not rules:
        raise ExaError(
            "EXA webset search carries no criteria to mirror; refusing to invent an admission rule"
        )
    count = payload.get("count")
    try:
        normalized_count = min(max(int(count), 1), 100) if count is not None else 10
    except (TypeError, ValueError):
        normalized_count = 10
    return WebsetSearch(
        id=_derive_id("wss", payload.get("id"), pattern=_SEARCH_ID_RE),
        webset_id=webset_id,
        query=str(payload.get("query") or "").strip() or "unspecified",
        count=normalized_count,
        status=_search_status(payload.get("status")),  # type: ignore[arg-type]
        criteria=rules[:5],
        verification_mode="llm",
        backend="exa",
    )


def _normalize_enrichment(payload: Mapping[str, Any]) -> EnrichmentDef | None:
    """Normalize one EXA ``WebsetEnrichment`` payload; ``None`` when unusable."""
    description = str(payload.get("description") or "").strip()
    name = str(payload.get("title") or description).strip()
    if not name:
        return None
    fmt = str(payload.get("format") or "text").strip().lower()
    if fmt not in _EXA_ENRICHMENT_FORMATS:
        fmt = "text"
    options: list[str] = []
    raw_options = payload.get("options")
    if isinstance(raw_options, list):
        for option in raw_options:
            if isinstance(option, Mapping) and option.get("label") is not None:
                options.append(str(option["label"]))
    if fmt != "options":
        options = []
    elif not options:
        return None
    try:
        return EnrichmentDef(
            name=name[:120],
            type=fmt,  # type: ignore[arg-type]
            description=description,
            options=options,
            status=_ENRICHMENT_STATUS.get(  # type: ignore[arg-type]
                str(payload.get("status") or "").strip().lower(), "running"
            ),
        )
    except ValidationError:
        return None


def _normalize_webset(
    payload: Mapping[str, Any],
    *,
    criteria: Sequence[VerificationCriterion] | None = None,
) -> Webset:
    """Normalize an EXA ``Webset`` payload into the OSS ``Webset`` shape."""
    webset_id = _derive_id("ws", payload.get("id"), pattern=_WEBSET_ID_RE)
    searches: list[WebsetSearch] = []
    raw_searches = payload.get("searches")
    if isinstance(raw_searches, list):
        for index, entry in enumerate(raw_searches):
            if not isinstance(entry, Mapping):
                continue
            searches.append(
                _normalize_search(
                    entry,
                    webset_id=webset_id,
                    fallback_criteria=criteria if index == 0 else None,
                )
            )
    enrichments: list[EnrichmentDef] = []
    raw_enrichments = payload.get("enrichments")
    if isinstance(raw_enrichments, list):
        for entry in raw_enrichments:
            if not isinstance(entry, Mapping):
                continue
            definition = _normalize_enrichment(entry)
            if definition is not None:
                enrichments.append(definition)
    fallback = list(criteria or ()) or (searches[0].criteria if searches else [])
    if not fallback:
        raise ExaError(
            "EXA webset carries no criteria to mirror; refusing to invent an admission rule"
        )
    return Webset(
        id=webset_id,
        status=_webset_status(payload.get("status")),  # type: ignore[arg-type]
        criteria=fallback[:5],
        searches=searches,
        enrichments=enrichments[:10],
        backend="exa",
        verification_mode="llm",
    )


# ── public entry points ───────────────────────────────────────────────────────


def create_webset(
    query: str,
    *,
    count: int = 10,
    criteria: Sequence[VerificationCriterion | Mapping[str, Any]] | None = None,
    enrichments: Sequence[EnrichmentDef | Mapping[str, Any]] | None = None,
    external_id: str | None = None,
    api_key: str | None = None,
) -> Webset:
    """Translate an OSS create into ``POST /websets`` and normalize the response."""
    text = (query or "").strip()
    if not text:
        raise ValueError("query is required")
    rules = _rules(criteria)
    if not rules:
        raise ValueError("criteria is required (1-5 rules)")
    body: dict[str, Any] = {
        "search": {
            "query": text,
            "count": min(max(int(count), 1), 100),
            "criteria": _exa_criteria(rules),
        }
    }
    enrichment_body = _exa_enrichments(enrichments)
    if enrichment_body:
        body["enrichments"] = enrichment_body
    if external_id:
        body["externalId"] = external_id
    payload = _request("POST", "/websets", body, api_key=_api_key(api_key))
    return _normalize_webset(payload, criteria=rules)


def get_webset(webset_id: str, *, api_key: str | None = None) -> Webset:
    """Read one EXA webset (``GET /websets/{id}``) and normalize it.

    ``webset_id`` is the EXA-side id (or an OSS id that already matches).
    """
    clean = (webset_id or "").strip()
    if not clean:
        raise ValueError("webset_id is required")
    payload = _request("GET", f"/websets/{clean}", None, api_key=_api_key(api_key))
    return _normalize_webset(payload)


def add_search(
    webset_id: str,
    *,
    query: str,
    count: int = 10,
    criteria: Sequence[VerificationCriterion | Mapping[str, Any]] | None = None,
    api_key: str | None = None,
) -> WebsetSearch:
    """Translate an OSS refresh into ``POST /websets/{id}/searches`` and normalize."""
    clean = (webset_id or "").strip()
    if not clean:
        raise ValueError("webset_id is required")
    text = (query or "").strip()
    if not text:
        raise ValueError("query is required")
    rules = _rules(criteria)
    body: dict[str, Any] = {"query": text, "count": min(max(int(count), 1), 100)}
    if rules:
        body["criteria"] = _exa_criteria(rules)
    payload = _request("POST", f"/websets/{clean}/searches", body, api_key=_api_key(api_key))
    return _normalize_search(
        payload,
        webset_id=_derive_id("ws", webset_id, pattern=_WEBSET_ID_RE),
        fallback_criteria=rules or None,
    )
