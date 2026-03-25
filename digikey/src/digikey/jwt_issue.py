"""Issue short-lived RS256 JWTs."""

from __future__ import annotations

import os
import uuid
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
) -> tuple[str, str]:
    """
    Returns (jwt, jti).
    """
    aud = audience or (os.environ.get("DIGIKEY_AUDIENCE") or DEFAULT_AUDIENCE).strip()
    ttl = ttl_sec if ttl_sec is not None else int(os.environ.get("DIGIKEY_JWT_TTL_SEC") or DEFAULT_TTL_SEC)
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
    claims["scope"] = " ".join(scopes)
    token = jwt.encode(claims, private_key_to_pem(private_key), algorithm="RS256", headers={"kid": kid})
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
