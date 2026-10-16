"""Edge license scope checks for hosted digigraph capabilities (slice 3 §7).

Normative scope map (design decision 3, adopted exactly):

| Requested hosted capability                | Required ``services`` scope |
|--------------------------------------------|-----------------------------|
| digisearch corpus / digivault prefix       | ``digisearch-corpus``       |
| hosted web search                          | ``hosted-web-search``       |
| plain inference (none of the hosted headers) | — (open, no check)        |

Validation per call: signature against the digikey public key, ``exp``
(enforced here — edge calls authorize), ``sub``/``tenant_slug``, and the
``services`` scope. ``services``-absent means entitled, not unentitled. No
per-call allowlist read: revocation freshness comes from the heartbeat latch
plus the ``exp`` backstop. Refusals are 403 ``insufficient_license_scope``
naming the missing scope; the hosted portion refuses, plain inference stays
byte-identical with and without a license.

Unwired (slice 3 scope): ``evaluate_hosted_license`` ships tested-but-unwired
— no digigraph enforcement point calls it yet. The spec §7 wiring
(corpus_routing / context / chat_resolve / workflow) is a named follow-up
per spec §0 item 2 (one PR per component: receiver first, edge second).
"""

from __future__ import annotations

from typing import Any

from digikey.license_verify import LicenseInfo, LicenseVerificationError, verify_license_token

LICENSE_HEADER = "X-Digi-License"
LICENSE_CORPUS_SCOPE = "digisearch-corpus"
LICENSE_WEB_SEARCH_SCOPE = "hosted-web-search"
HEADER_CORPUS_INDEX = "X-Digi-Corpus-Index"
HEADER_VAULT_PREFIX = "X-Digi-Vault-Prefix"
HEADER_WEB_SEARCH = "X-Digi-Enable-Web-Search"
INSUFFICIENT_LICENSE_SCOPE = "insufficient_license_scope"


def _header_get(headers: Any, name: str) -> str:
    """Case-insensitive header read for Starlette Headers and plain dicts."""
    get = getattr(headers, "get", None)
    if not callable(get):
        return ""
    for candidate in (name, name.lower(), name.upper(), name.title()):
        try:
            raw = get(candidate)
        except Exception:
            continue
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return ""


def license_token_from_headers(headers: Any) -> str:
    """Raw license JWT from ``X-Digi-License`` (``""`` when absent)."""
    return _header_get(headers, LICENSE_HEADER)


def corpus_headers_requested(headers: Any) -> bool:
    """True when the request carries corpus/vault hosted headers."""
    return bool(
        _header_get(headers, HEADER_CORPUS_INDEX) or _header_get(headers, HEADER_VAULT_PREFIX)
    )


def web_search_header_requested(headers: Any) -> bool:
    """True when the web-search header opts in (body flags are checked by callers)."""
    return _header_get(headers, HEADER_WEB_SEARCH).lower() in ("1", "true", "yes")


def services_entitles(services: list[str] | None, required: str) -> bool:
    """``services``-absent (None) means entitled; otherwise exact membership."""
    if services is None:
        return True
    return required in services


def evaluate_hosted_license(
    headers: Any,
    *,
    needs_corpus: bool,
    needs_web_search: bool,
    public_key_pem: str | None,
    issuer: str | None = None,
) -> str | None:
    """Return the missing scope name, or ``None`` when authorized/open.

    Plain requests (neither capability needed) never touch license code and
    return ``None``. Otherwise the ``X-Digi-License`` JWT must verify (with
    ``exp`` enforcement), carry a ``sub``/``tenant_slug`` identity, and entitle
    every needed scope; the first missing scope is returned so the refusal
    names it.
    """
    wanted: list[str] = []
    if needs_corpus:
        wanted.append(LICENSE_CORPUS_SCOPE)
    if needs_web_search:
        wanted.append(LICENSE_WEB_SEARCH_SCOPE)
    if not wanted:
        return None
    info: LicenseInfo | None = None
    token = license_token_from_headers(headers)
    if token and (public_key_pem or "").strip():
        try:
            candidate = verify_license_token(
                token,
                public_key_pem=(public_key_pem or "").strip(),
                issuer=issuer,
                verify_exp=True,
            )
        except LicenseVerificationError:
            candidate = None
        else:
            # §7.2 validates sub/tenant_slug per call: an identity-free license
            # authorizes no hosted capability.
            if candidate is not None and (
                candidate.customer.strip() or candidate.tenant_slug.strip()
            ):
                info = candidate
    if info is None:
        return wanted[0]
    for scope in wanted:
        if not services_entitles(info.services, scope):
            return scope
    return None


def denial_body(missing_scope: str) -> dict[str, str]:
    """403 body naming the missing scope (operator-facing, secret-free)."""
    return {
        "error": INSUFFICIENT_LICENSE_SCOPE,
        "message": (
            f"Hosted capability requires license scope '{missing_scope}'. "
            "Serve plain inference without the hosted headers, or provision a "
            "license that entitles this capability."
        ),
    }
