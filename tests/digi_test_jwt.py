"""Mint RS256 test JWTs for DigiAuth middleware (pytest configures DIGIKEY_PUBLIC_KEY_PEM)."""

from __future__ import annotations

import os

from digikey.crypto_keys import load_private_key_from_pem
from digikey.jwt_issue import issue_access_token


def mint_test_jwt(*, scopes: list[str] | None = None) -> str:
    pem = os.environ.get("_PYTEST_DIGIKEY_PRIVATE_PEM", "").strip()
    if not pem:
        raise RuntimeError("_PYTEST_DIGIKEY_PRIVATE_PEM must be set by tests/conftest.py pytest_configure")
    priv = load_private_key_from_pem(pem)
    token, _ = issue_access_token(
        priv,
        kid="pytest-kid",
        sub="pytest-sub",
        tenant_slug="pytest-tenant",
        scopes=scopes if scopes is not None else ["*"],
    )
    return token


def auth_headers(*, scopes: list[str] | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_test_jwt(scopes=scopes)}"}
