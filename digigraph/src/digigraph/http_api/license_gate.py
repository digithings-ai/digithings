"""Hosted license scope enforcement at the digigraph edge (spec §7).

Thin HTTP-layer wrapper over ``digikey.license_edge.evaluate_hosted_license``:
verifies the ``X-Digi-License`` JWT against the digikey public key
(``DIGIKEY_PUBLIC_KEY_PEM``) and raises ``LicenseScopeDenied`` — mapped to a
403 ``insufficient_license_scope`` refusal by the server's exception handler —
when a requested hosted capability is absent, invalid, expired, or out of
scope.

Plain inference never reaches a check: ``enforce_corpus_license`` returns
early without corpus headers, and ``enforce_web_search_license`` returns early
unless the caller resolved opt-in — and the helper itself stays open for
plain requests.

No per-call allowlist read: revocation freshness comes from the container
heartbeat latch plus the ``exp`` backstop (spec §7.2). The raw license JWT is
never logged here — only the missing scope name, which is safe to log.
"""

from __future__ import annotations

import logging
import os
from typing import Any  # score:allow untyped any — Starlette headers / plain dicts

from digikey.license_edge import (
    corpus_headers_requested,
    denial_body,
    evaluate_hosted_license,
)
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PUBLIC_KEY_ENV = "DIGIKEY_PUBLIC_KEY_PEM"


class LicenseScopeDenied(Exception):
    """A hosted capability was requested without an authorizing license scope."""

    def __init__(self, missing_scope: str) -> None:
        super().__init__(missing_scope)
        self.missing_scope = missing_scope


def license_public_key_pem() -> str:
    """digikey public key PEM for license verification ("" when unconfigured)."""
    return (os.environ.get(PUBLIC_KEY_ENV) or "").strip()


def denial_response(missing_scope: str) -> JSONResponse:
    """Spec §7.3 refusal: 403 naming the missing scope (secret-free body)."""
    return JSONResponse(status_code=403, content=denial_body(missing_scope))


def enforce_corpus_license(headers: Any, *, headers_effective: bool = True) -> None:
    """Refuse corpus/vault-routed turns without the ``digisearch-corpus`` scope.

    Returns silently when no corpus headers are present, so plain-inference
    callers never touch license code — and when ``headers_effective`` is
    false, so map-authoritative deployments (``DIGI_TENANT_CORPUS_MAP`` set,
    client headers ignored) keep map behavior unchanged: the gate sits after
    map resolution and can only narrow header-driven selection, never widen
    or disturb mapped selection. Otherwise the ``X-Digi-License`` JWT must
    verify and entitle the corpus scope, or ``LicenseScopeDenied`` names the
    missing scope.
    """
    if not headers_effective or not corpus_headers_requested(headers):
        return
    missing = evaluate_hosted_license(
        headers,
        needs_corpus=True,
        needs_web_search=False,
        public_key_pem=license_public_key_pem(),
    )
    if missing is not None:
        logger.warning("license scope denied: missing=%s capability=corpus", missing)
        raise LicenseScopeDenied(missing)


def enforce_web_search_license(headers: Any, *, enabled: bool) -> None:
    """Refuse web-search-gated turns without the ``hosted-web-search`` scope.

    *enabled* is the caller-resolved opt-in (body-or-header on the chat path,
    body flag on ``/workflow``) — this gate never re-resolves it, so endpoint
    semantics cannot drift. Returns silently unless opted in.
    """
    if not enabled:
        return
    missing = evaluate_hosted_license(
        headers,
        needs_corpus=False,
        needs_web_search=True,
        public_key_pem=license_public_key_pem(),
    )
    if missing is not None:
        logger.warning("license scope denied: missing=%s capability=web_search", missing)
        raise LicenseScopeDenied(missing)
