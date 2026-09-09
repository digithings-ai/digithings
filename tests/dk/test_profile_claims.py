"""Profile pointer claims on digikey JWTs (#308 / CHR-73).

Covers:
- claim present after profile create (bff_session mint)
- claim bumps on profile update
- missing-profile case: both claims absent from the JWT
"""

from __future__ import annotations

import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

# Signing key loads at digikey.server import — allow ephemeral RS256 for unit tests.
if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")

import digikey.db as digikey_db
from digikey.db import init_db, session_factory
from digikey.jwt_issue import issue_access_token
from digikey.jwt_verify import decode_token
from digikey.profile_pointer import (
    bump_profile_version,
    create_profile_pointer,
    get_profile_pointer,
)
from digikey.server import app

pytestmark = pytest.mark.unit

BFF_TOKEN = "test-bff-token-for-profile-claims"


@pytest.fixture()
def digikey_db_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "digikey.sqlite"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_BFF_TOKEN", BFF_TOKEN)
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-digikey")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    digikey_db._engine = None
    digikey_db._session_factory = None
    init_db()


@pytest.fixture()
def key_setup(monkeypatch: pytest.MonkeyPatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key_to_pem(key)
    pub_pem = public_key_to_pem(key.public_key())
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-digikey")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    return priv_pem, pub_pem


def _decode_unverified(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def test_issue_omits_profile_claims_when_absent(key_setup, monkeypatch):
    from cryptography.hazmat.primitives import serialization

    priv_pem, pub_pem = key_setup
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)

    token, _ = issue_access_token(
        priv,
        kid="t1",
        sub="bff:alice",
        tenant_slug="acme",
        scopes=["digigraph:chat"],
        principal_kind="bff_session",
    )
    claims = decode_token(token)
    assert claims.profile_id is None
    assert claims.profile_version is None
    raw = _decode_unverified(token)
    assert "profile_id" not in raw
    assert "profile_version" not in raw


def test_issue_includes_paired_profile_claims(key_setup, monkeypatch):
    from cryptography.hazmat.primitives import serialization

    priv_pem, pub_pem = key_setup
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)

    token, _ = issue_access_token(
        priv,
        kid="t1",
        sub="bff:alice",
        tenant_slug="acme",
        scopes=["digigraph:chat"],
        principal_kind="bff_session",
        profile_id="prof-abc",
        profile_version=3,
    )
    claims = decode_token(token)
    assert claims.profile_id == "prof-abc"
    assert claims.profile_version == 3


def test_claim_present_after_profile_create(digikey_db_env: None) -> None:
    subject = "user-alice"
    sf = session_factory()
    with sf() as session:
        pointer = create_profile_pointer(session, subject=subject, tenant_slug="acme")
        session.commit()
        assert pointer.profile_version == 1
        assert get_profile_pointer(session, subject) is not None

    client = TestClient(app)
    r = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": subject,
        },
    )
    assert r.status_code == 200, r.text
    raw = _decode_unverified(r.json()["access_token"])
    assert raw["profile_id"] == pointer.profile_id
    assert raw["profile_version"] == 1
    assert raw["sub"] == f"bff:{subject}"


def test_claim_bumps_on_profile_update(digikey_db_env: None) -> None:
    subject = "user-bob"
    sf = session_factory()
    with sf() as session:
        pointer = create_profile_pointer(session, subject=subject, tenant_slug="acme")
        session.commit()
        profile_id = pointer.profile_id

    client = TestClient(app)

    r1 = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": subject,
        },
    )
    assert r1.status_code == 200, r1.text
    assert _decode_unverified(r1.json()["access_token"])["profile_version"] == 1

    with sf() as session:
        bumped = bump_profile_version(session, subject)
        session.commit()
        assert bumped.profile_id == profile_id
        assert bumped.profile_version == 2

    r2 = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": subject,
        },
    )
    assert r2.status_code == 200, r2.text
    raw2 = _decode_unverified(r2.json()["access_token"])
    assert raw2["profile_id"] == profile_id
    assert raw2["profile_version"] == 2


def test_missing_profile_omits_claims_on_bff_mint(digikey_db_env: None) -> None:
    client = TestClient(app)
    r = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": "brand-new-user",
        },
    )
    assert r.status_code == 200, r.text
    raw = _decode_unverified(r.json()["access_token"])
    assert "profile_id" not in raw
    assert "profile_version" not in raw
