"""Issue short-lived RS256 JWTs."""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

DEFAULT_AUDIENCE = "digi-ecosystem"
DEFAULT_TTL_SEC = 900


def _issuer() -> str:
    return (os.environ.get("DIGIKEY_ISSUER") or "http://127.0.0.1:8005").rstrip("/")


def issue_access_token(
    private_key: RSAPrivateKey,
    *,
    kid: str,
    sub: str,
    tenant_slug: str,
    scopes: list[str],
    key_pub: str | None = None,
    project_id: str | None = None,
    project_config_ref: str | None = None,
    tenant_id: str | None = None,
    principal_kind: str = "api_key",
    legacy_static: bool = False,
    audience: str | None = None,
    ttl_sec: int | None = None,
    profile_id: str | None = None,
    profile_version: int | None = None,
) -> tuple[str, str]:
    """
    Returns (jwt, jti).

    ``profile_id`` / ``profile_version`` are optional profile pointers (#308).
    Both are omitted from the payload when absent so clients can treat missing
    claims as "no profile yet — route to intake." Never emit one without the other.
    """
    aud = audience or (os.environ.get("DIGIKEY_AUDIENCE") or DEFAULT_AUDIENCE).strip()
    ttl = (
        ttl_sec
        if ttl_sec is not None
        else int(os.environ.get("DIGIKEY_JWT_TTL_SEC") or DEFAULT_TTL_SEC)
    )
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": _issuer(),
        "aud": aud,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": jti,
        "tenant_slug": tenant_slug,
        "scopes": scopes,
        "principal_kind": principal_kind,
        "legacy_static": legacy_static,
    }
    if tenant_id:
        claims["tenant_id"] = tenant_id
    if project_id:
        claims["project_id"] = project_id
    if project_config_ref:
        claims["project_config_ref"] = project_config_ref
    if key_pub:
        claims["key_pub"] = key_pub
    # Pairwise: only emit when both are present and version is a positive int.
    if profile_id and profile_version is not None and int(profile_version) >= 1:
        claims["profile_id"] = str(profile_id).strip()
        claims["profile_version"] = int(profile_version)
    claims["scope"] = " ".join(scopes)
    token = jwt.encode(
        claims, private_key_to_pem(private_key), algorithm="RS256", headers={"kid": kid}
    )
    # PyJWT 2 returns str for str key
    return str(token), jti


def public_jwks(private_key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    """JWKS document with one RSA key."""
    from jwt.algorithms import RSAAlgorithm

    pub = private_key.public_key()
    pem = public_key_to_pem(pub)
    data = RSAAlgorithm.to_jwk(pub, as_dict=True)
    data["kid"] = kid
    data["use"] = "sig"
    data["alg"] = "RS256"
    _ = pem  # keep pem for debugging
    return {"keys": [data]}


LICENSE_AUDIENCE = "digichat-license"
LICENSE_KIND = "digichat-license"
LICENSE_DEFAULT_TERM_DAYS = 90
LICENSE_MAX_TERM_DAYS = 180
LICENSE_TERM_SEC = 86400


def build_license_claims(
    *,
    customer_slug: str,
    hosts: Sequence[str],
    services: Sequence[str] | None = None,
    term_days: int = LICENSE_DEFAULT_TERM_DAYS,
) -> tuple[dict[str, Any], str]:
    """Build customer-license JWT claims without signing.

    Returns ``(claims, license_id)`` where ``license_id`` mirrors the ``jti``.
    ``services`` is omitted from the claims entirely when not passed or empty
    (absent means entitled to the hosted services of the commercial term).
    Raises ``ValueError`` on blank customer/hosts or an out-of-range term.
    """
    customer = customer_slug.strip()
    if not customer:
        raise ValueError("customer_slug must not be blank")
    clean_hosts = [h.strip() for h in hosts if h.strip()]
    if not clean_hosts:
        raise ValueError("hosts must name at least one hostname")
    if term_days < 1 or term_days > LICENSE_MAX_TERM_DAYS:
        raise ValueError(f"term_days must be 1..{LICENSE_MAX_TERM_DAYS}")
    svc = list(services) if services else None  # [] behaves like absent (pairwise-omit)
    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    license_id = uuid.uuid4().hex
    claims: dict[str, Any] = {
        "sub": customer,
        "iss": _issuer(),
        "aud": LICENSE_AUDIENCE,
        "iat": iat,
        "exp": iat + term_days * LICENSE_TERM_SEC,
        "jti": license_id,
        "license_id": license_id,
        "tenant_slug": customer,
        "hosts": clean_hosts,
        "kind": LICENSE_KIND,
    }
    if svc is not None:
        claims["services"] = svc
        claims["scope"] = " ".join(svc)
    return claims, license_id


def sign_license_claims(
    private_key: RSAPrivateKey,
    *,
    kid: str,
    claims: dict[str, Any],
) -> str:
    """Sign pre-built license claims (RS256, ``kid`` header)."""
    token = jwt.encode(
        claims, private_key_to_pem(private_key), algorithm="RS256", headers={"kid": kid}
    )
    return str(token)


def issue_license_token(
    private_key: RSAPrivateKey,
    *,
    kid: str,
    customer_slug: str,
    hosts: Sequence[str],
    services: Sequence[str] | None = None,
    term_days: int = LICENSE_DEFAULT_TERM_DAYS,
) -> tuple[str, str, int]:
    """Mint a customer-license JWT with the digikey access-token keypair.

    Returns ``(token, license_id, exp)``. License values (``aud``,
    ``ttl``) are always passed explicitly here — the access-token defaults
    (``aud=digi-ecosystem``, 900s TTL) are untouched.
    """
    claims, license_id = build_license_claims(
        customer_slug=customer_slug,
        hosts=hosts,
        services=services,
        term_days=term_days,
    )
    return (
        sign_license_claims(private_key, kid=kid, claims=claims),
        license_id,
        int(claims["exp"]),
    )
