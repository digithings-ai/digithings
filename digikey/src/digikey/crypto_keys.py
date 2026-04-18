"""RSA key pair for JWT signing (RS256)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


def generate_rsa_private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def private_key_to_pem(key: RSAPrivateKey) -> str:
    return (
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("utf-8")
        .strip()
    )


def public_key_to_pem(key: RSAPublicKey) -> str:
    return (
        key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
        .strip()
    )


def load_private_key_from_pem(pem: str) -> RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("Expected RSA private key")
    return key


def load_public_key_from_pem(pem: str) -> RSAPublicKey:
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("Expected RSA public key")
    return key


def load_or_create_signing_key() -> tuple[RSAPrivateKey, str]:
    """
    Load DIGIKEY_PRIVATE_KEY_PEM, or generate an ephemeral key only when
    DIGIKEY_ALLOW_EPHEMERAL_KEY=1 (local Docker default; not for production).
    """
    pem = (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip()
    kid = (os.environ.get("DIGIKEY_KEY_ID") or "digikey-1").strip() or "digikey-1"
    if pem:
        return load_private_key_from_pem(pem), kid
    allow = os.environ.get("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0").strip().lower() in ("1", "true", "yes")
    if not allow:
        raise RuntimeError(
            "DigiKey requires DIGIKEY_PRIVATE_KEY_PEM, or set DIGIKEY_ALLOW_EPHEMERAL_KEY=1 "
            "for a non-persistent dev key (JWKS rotates on restart)."
        )
    key = generate_rsa_private_key()
    os.environ.setdefault("_DIGIKEY_EPHEMERAL_PEM", private_key_to_pem(key))
    return key, kid
