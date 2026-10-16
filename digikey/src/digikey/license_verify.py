"""Verify digichat customer license JWTs (heartbeat receiver + edge checks).

Licenses are RS256 JWTs minted by the owner-run CLI (slice 1) with the existing
digikey keypair and ``aud="digichat-license"``. This module is the single
verification path for both consumers:

* the heartbeat receiver (``digikey/server.py``) verifies against the server's
  own signing key with ``verify_exp=False``: the allowlist row's ``expires_at``
  is the expiry source of truth, so an expired-but-authentic license still
  identifies and answers 200 ``expired`` instead of a latch-inducing 401;
* the digigraph edge (``digikey/license_edge.py``) verifies against
  ``DIGIKEY_PUBLIC_KEY_PEM`` with ``verify_exp=True``: edge calls authorize
  hosted capabilities, so a lapsed license must refuse there.

Secret hygiene: the raw token is never logged, never returned, never written.
Safe to log: ``license_id``, customer slug, ``exp``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import jwt

LICENSE_AUDIENCE = "digichat-license"
LICENSE_KIND = "digichat-license"
CLOCK_SKEW_LEEWAY_SEC = 300
LICENSE_ISSUER_DEFAULT = "http://127.0.0.1:8005"


def license_issuer_default() -> str:
    """Expected ``iss`` — same source as access tokens (``jwt_issue._issuer``).

    Kept as a local one-liner instead of an import so slice-1 edits to
    ``jwt_issue.py`` cannot move this module's trust anchor.
    """
    return (os.environ.get("DIGIKEY_ISSUER") or LICENSE_ISSUER_DEFAULT).rstrip("/")


class LicenseVerificationError(Exception):
    """A license JWT failed verification. ``reason`` is a stable short code."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass
class LicenseInfo:
    """Verified license claims (subset needed by heartbeat + edge)."""

    license_id: str
    customer: str = ""
    tenant_slug: str = ""
    hosts: list[str] = field(default_factory=list)
    #: ``None`` = claim absent = entitled to the hosted services of the term.
    services: list[str] | None = None
    exp: int | None = None
    iat: int | None = None


def verify_license_token(
    token: str,
    *,
    public_key_pem: str,
    issuer: str | None = None,
    verify_exp: bool = True,
) -> LicenseInfo:
    """Verify a raw license JWT and return its claims.

    Enforces RS256-only (rejects ``none`` and every symmetric ``alg`` outright —
    the classic key-confusion hole), ``aud == "digichat-license"``, the server
    issuer, ``kind == "digichat-license"``, and a present ``license_id`` (or its
    ``jti`` mirror). ``exp`` is enforced only when ``verify_exp`` is true, with
    a 300s symmetric clock-skew leeway either way.
    """
    raw = (token or "").strip()
    if not raw:
        raise LicenseVerificationError("missing_token", "License token is missing")
    try:
        header = jwt.get_unverified_header(raw)
    except jwt.PyJWTError as exc:
        raise LicenseVerificationError(
            "malformed_token", f"Malformed license token: {exc}"
        ) from exc
    alg = str(header.get("alg") or "").upper()
    if alg != "RS256":
        raise LicenseVerificationError("bad_algorithm", "License token must be RS256")
    key = (public_key_pem or "").strip()
    if not key:
        raise LicenseVerificationError("no_public_key", "No license verification key configured")
    try:
        payload = jwt.decode(
            raw,
            key,
            algorithms=["RS256"],
            audience=LICENSE_AUDIENCE,
            issuer=issuer or license_issuer_default(),
            leeway=CLOCK_SKEW_LEEWAY_SEC,
            options={"verify_exp": verify_exp},
        )
    except jwt.ExpiredSignatureError as exc:
        raise LicenseVerificationError("expired", "License token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise LicenseVerificationError("aud_mismatch", "License token audience mismatch") from exc
    except jwt.InvalidIssuerError as exc:
        raise LicenseVerificationError("iss_mismatch", "License token issuer mismatch") from exc
    except jwt.PyJWTError as exc:
        raise LicenseVerificationError("bad_signature", f"License token invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise LicenseVerificationError("malformed_token", "License token payload invalid")
    if payload.get("kind") != LICENSE_KIND:
        raise LicenseVerificationError("kind_mismatch", "Not a digichat license token")
    license_id = payload.get("license_id") or payload.get("jti")
    if not license_id or not str(license_id).strip():
        raise LicenseVerificationError("claims_missing", "License token has no license_id")
    hosts: list[str] = []
    if isinstance(payload.get("hosts"), list):
        hosts = [str(h) for h in payload["hosts"] if str(h).strip()]
    services: list[str] | None = None
    if "services" in payload:
        if not isinstance(payload["services"], list):
            raise LicenseVerificationError("claims_missing", "License services malformed")
        services = [str(s) for s in payload["services"]]
    exp = payload.get("exp")
    iat = payload.get("iat")
    return LicenseInfo(
        license_id=str(license_id).strip(),
        customer=str(payload.get("sub") or ""),
        tenant_slug=str(payload.get("tenant_slug") or ""),
        hosts=hosts,
        services=services,
        exp=int(exp) if isinstance(exp, (int, float)) else None,
        iat=int(iat) if isinstance(iat, (int, float)) else None,
    )
