"""Verify DigiKey JWTs via local PEM or JWKS URL."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from jwt.types import Options as JwtOptions  # noqa: F401

from digikey.models import PrincipalKind, TokenClaims

logger = logging.getLogger(__name__)


class JwtVerificationError(Exception):
    """JWT signature, claims, or JWKS retrieval failed."""

_DEFAULT_JWKS_CACHE_SEC = 300
_jwks_client: PyJWKClient | None = None
_jwks_client_url: str | None = None


def _audience_list() -> list[str]:
    raw = (os.environ.get("DIGIKEY_AUDIENCE") or "digi-ecosystem").strip()
    return [raw]


def _issuer() -> str:
    return (os.environ.get("DIGIKEY_ISSUER") or "http://127.0.0.1:8005").rstrip("/")


def _get_jwks_client(url: str) -> PyJWKClient:
    global _jwks_client, _jwks_client_url
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = PyJWKClient(
            url,
            cache_keys=True,
            max_cached_keys=5,
            lifespan=int(os.environ.get("DIGIKEY_JWKS_CACHE_SEC") or _DEFAULT_JWKS_CACHE_SEC),
        )
        _jwks_client_url = url
    return _jwks_client


def decode_token(token: str, *, options: dict[str, Any] | None = None) -> TokenClaims:
    """
    Verify signature and return TokenClaims.
    Uses DIGIKEY_JWKS_URL if set, else DIGIKEY_PUBLIC_KEY_PEM (required for verify).
    """
    opts: dict[str, Any] = {"verify_aud": True, "verify_exp": True}
    if options:
        opts.update(options)

    jwks_url = (os.environ.get("DIGIKEY_JWKS_URL") or "").strip()
    pem = (os.environ.get("DIGIKEY_PUBLIC_KEY_PEM") or "").strip()

    if jwks_url:
        try:
            signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=_audience_list(),
                issuer=_issuer(),
                options=opts,  # type: ignore[arg-type]
            )
        except (jwt.PyJWTError, httpx.HTTPError, OSError, ValueError, TypeError) as e:
            raise JwtVerificationError(str(e)) from e
    elif pem:
        try:
            payload = jwt.decode(
                token,
                pem,
                algorithms=["RS256"],
                audience=_audience_list(),
                issuer=_issuer(),
                options=opts,  # type: ignore[arg-type]
            )
        except jwt.PyJWTError as e:
            raise JwtVerificationError(str(e)) from e
    else:
        raise jwt.InvalidKeyError(
            "Set DIGIKEY_JWKS_URL or DIGIKEY_PUBLIC_KEY_PEM for JWT verification",
        )

    return _payload_to_claims(dict(payload))


def _payload_to_claims(payload: dict[str, Any]) -> TokenClaims:
    scopes: list[str] = []
    if isinstance(payload.get("scopes"), list):
        scopes = [str(s) for s in payload["scopes"]]
    elif isinstance(payload.get("scope"), str) and payload["scope"].strip():
        scopes = [s for s in payload["scope"].split() if s]
    pk: PrincipalKind = "api_key"
    raw_kind = payload.get("principal_kind")
    if raw_kind in ("api_key", "bff_session", "legacy_static"):
        pk = raw_kind
    return TokenClaims(
        sub=str(payload.get("sub", "")),
        iss=str(payload.get("iss", "")),
        aud=payload.get("aud", ""),
        exp=int(payload["exp"]) if payload.get("exp") is not None else None,
        jti=str(payload["jti"]) if payload.get("jti") else None,
        tenant_slug=str(payload.get("tenant_slug", "") or ""),
        tenant_id=str(payload["tenant_id"]) if payload.get("tenant_id") else None,
        project_id=str(payload["project_id"]) if payload.get("project_id") else None,
        project_config_ref=str(payload["project_config_ref"])
        if payload.get("project_config_ref")
        else None,
        scopes=scopes,
        key_pub=str(payload["key_pub"]) if payload.get("key_pub") else None,
        principal_kind=pk,
        legacy_static=bool(payload.get("legacy_static", False)),
        raw=dict(payload),
    )


def fetch_jwks_raw(url: str) -> dict[str, Any] | None:
    """HTTP fetch JWKS (for tests or tooling)."""
    try:
        r = httpx.get(url, timeout=5.0)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError):
        return None


def decode_token_local(token: str, private_key_pem: str) -> TokenClaims:
    """Decode using public half of *private_key_pem* (tests)."""
    from cryptography.hazmat.primitives import serialization

    priv = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    pub = priv.public_key()
    pem = (
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
        .strip()
    )
    payload = jwt.decode(
        token,
        pem,
        algorithms=["RS256"],
        audience=_audience_list(),
        issuer=_issuer(),
    )
    return _payload_to_claims(dict(payload))
