"""RSA key pair for JWT signing (RS256)."""

from __future__ import annotations

import os
import threading
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


#: The process's ephemeral signing key, once one has been generated. It lives
#: only in this module: it is never exported to os.environ, so child processes
#: and environment dumps cannot see it.
_ephemeral_key: RSAPrivateKey | None = None
_ephemeral_key_lock = threading.Lock()

#: Whether the most recent load_or_create_signing_key() call returned an
#: ephemeral key. Read it through ephemeral_key_in_use(); callers that hold a
#: key (digikey.server) should capture it right after their own load.
_ephemeral_used = False


def ephemeral_key_in_use() -> bool:
    """True when the last load_or_create_signing_key() generated an ephemeral key."""
    return _ephemeral_used


def load_or_create_signing_key() -> tuple[RSAPrivateKey, str]:
    """
    Load DIGIKEY_PRIVATE_KEY_PEM, or generate an ephemeral key only when
    the operator opts in with DIGIKEY_ALLOW_EPHEMERAL_KEY=1 (off by default;
    local dev only, never production).

    The ephemeral key is generated once per process and reused, so it stays
    stable for the life of the process; it is never written to the environment.
    Records which of the two it did; see ephemeral_key_in_use().
    """
    global _ephemeral_key, _ephemeral_used
    # Cleared first, so any path that raises (a bad PEM, a refusal, a failed
    # generate) never leaves an earlier ephemeral record behind.
    _ephemeral_used = False
    pem = (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip()
    kid = (os.environ.get("DIGIKEY_KEY_ID") or "digikey-1").strip() or "digikey-1"
    if pem:
        return load_private_key_from_pem(pem), kid
    allow = os.environ.get("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow:
        raise RuntimeError(
            "digikey requires DIGIKEY_PRIVATE_KEY_PEM, or set DIGIKEY_ALLOW_EPHEMERAL_KEY=1 "
            "for a non-persistent dev key (JWKS rotates on restart)."
        )
    # Parsed with int(), as uvicorn does; an unparseable value is refused too,
    # since it is not a clear single-process setting.
    workers = os.environ.get("WEB_CONCURRENCY") or ""
    try:
        many_workers = bool(workers) and int(workers) > 1
    except ValueError:
        many_workers = True
    if many_workers:
        raise RuntimeError(
            f"DIGIKEY_ALLOW_EPHEMERAL_KEY=1 needs a single digikey process, but "
            f"WEB_CONCURRENCY={workers!r}: each worker would sign with its own key and "
            "publish a different JWKS. Set DIGIKEY_PRIVATE_KEY_PEM or run one worker."
        )
    with _ephemeral_key_lock:
        if _ephemeral_key is None:
            _ephemeral_key = generate_rsa_private_key()
        _ephemeral_used = True
        return _ephemeral_key, kid
