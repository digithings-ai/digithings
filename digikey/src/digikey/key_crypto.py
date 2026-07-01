"""API key material: generate, hash, verify (bcrypt)."""

from __future__ import annotations

import bcrypt
import secrets

from digikey.settings import KEY_PREFIX_LEN, RAW_KEY_PREFIX


def generate_raw_key() -> tuple[str, str]:
    """Return (full_secret, key_prefix for lookup)."""
    tail = secrets.token_urlsafe(24).replace("-", "")[:32]
    full = f"{RAW_KEY_PREFIX}{tail}"
    prefix = full[:KEY_PREFIX_LEN]
    return full, prefix


def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(raw: str, key_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), key_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
