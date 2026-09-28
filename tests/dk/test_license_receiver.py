"""Slice 3: license heartbeat receiver + admin license revoke (unit, no stack).

Covers the §8 test plan rows owned by the receiver: the four-state matrix
(expired is 200, never 401; revoked beats expired), the crypto boundary, the
300s skew leeway, contract fidelity (only latch codes + generic 401 on this
route; telemetry mismatches are 400), auth isolation from the API-key/admin
paths, the admin license revoke, the 429 error-outcome shape, and secret
hygiene (no raw JWT in logs or bodies).
"""

from __future__ import annotations

import json
import logging
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.unit

ISSUER = "http://test-digikey"
ADMIN = "admin-secret"

DDL = """
CREATE TABLE IF NOT EXISTS digikey_licenses (
    license_id VARCHAR(36) PRIMARY KEY,
    customer_slug VARCHAR(256) NOT NULL,
    hosts TEXT NOT NULL,
    services TEXT NULL,
    issued_at DATETIME NULL,
    expires_at INTEGER NOT NULL,
    revoked_at DATETIME NULL,
    label VARCHAR(256) NULL
)
"""


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "dk-lic.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("DIGIKEY_ISSUER", ISSUER)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    from digikey.ratelimit import get_limiter

    from digikey import blocklist, db

    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()
    get_limiter().reset()

    from digikey.server import app

    with TestClient(app) as c:
        sf = db.session_factory()
        with sf() as session:
            session.execute(text(DDL))
            session.commit()
        yield c
    get_limiter().reset()


def _server_key():
    from digikey import server as srv

    return srv._private_key, srv._kid


def _mint(
    license_id: str,
    *,
    customer: str = "datatap",
    services: list[str] | None | str = "absent",
    hosts: list[str] | None = None,
    exp: int | None = None,
    iss: str = ISSUER,
    aud: str = "digichat-license",
    kind: str | None = "digichat-license",
    key=None,
) -> str:
    priv, kid = _server_key()
    now = int(time.time())
    claims: dict = {
        "sub": customer,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": exp if exp is not None else now + 90 * 86400,
        "jti": license_id,
        "license_id": license_id,
        "tenant_slug": customer,
        "hosts": hosts if hosts is not None else ["datatapstream.com"],
    }
    if kind is not None:
        claims["kind"] = kind
    if services != "absent" and services is not None:
        claims["services"] = list(services)
        claims["scope"] = " ".join(services)
    return str(jwt.encode(claims, _priv_pem(key or priv), algorithm="RS256", headers={"kid": kid}))


def _priv_pem(key) -> str:
    from digikey.crypto_keys import private_key_to_pem

    return private_key_to_pem(key)


def _body(license_id: str, *, seq: int = 1, status: str = "valid") -> dict:
    return {
        "license_id": license_id,
        "customer": "datatap",
        "license_status": status,
        "version": "2.3.2",
        "hosts_configured": ["datatapstream.com"],
        "started_at": "2026-09-28T09:14:02.000Z",
        "seq": seq,
    }


def _insert(
    c: TestClient,
    license_id: str,
    *,
    expires_at: int | None = None,
    revoked: bool = False,
    customer: str = "datatap",
) -> None:
    from digikey import db

    now = int(time.time())
    sf = db.session_factory()
    with sf() as session:
        session.execute(
            text(
                "INSERT INTO digikey_licenses"
                " (license_id, customer_slug, hosts, services, expires_at, revoked_at)"
                " VALUES (:lid, :cust, :hosts, NULL, :exp, :rev)"
            ),
            {
                "lid": license_id,
                "cust": customer,
                "hosts": json.dumps(["datatapstream.com"]),
                "exp": expires_at if expires_at is not None else now + 90 * 86400,
                "rev": ("2026-09-28T10:00:00+00:00" if revoked else None),
            },
        )
        session.commit()


def _beat(c: TestClient, token: str, body: dict | None = None, lid: str = ""):
    payload = body if body is not None else _body(lid)
    return c.post(
        "/v1/licenses/heartbeat",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_heartbeat_valid(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = _beat(client, _mint(lid), lid=lid)
    assert r.status_code == 200, r.text
    assert r.json() == {"license_status": "valid"}


def test_heartbeat_expired_is_200_never_401(client):
    lid = uuid.uuid4().hex
    _insert(client, lid, expires_at=int(time.time()) - 3600)
    r = _beat(client, _mint(lid), lid=lid)
    assert r.status_code == 200, r.text
    assert r.json() == {"license_status": "expired"}


def test_heartbeat_revoked(client):
    lid = uuid.uuid4().hex
    _insert(client, lid, revoked=True)
    r = _beat(client, _mint(lid), lid=lid)
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "license_revoked"


def test_heartbeat_unknown(client):
    lid = uuid.uuid4().hex
    r = _beat(client, _mint(lid), lid=lid)
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "unknown_license"


def test_heartbeat_revoked_beats_expired(client):
    lid = uuid.uuid4().hex
    _insert(client, lid, expires_at=int(time.time()) - 3600, revoked=True)
    r = _beat(client, _mint(lid), lid=lid)
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "license_revoked"


def test_heartbeat_row_drives_expiry_not_jwt(client):
    # JWT itself long expired, but the allowlist row is live: crypto must not
    # latch, and the row must still read valid (verify_exp=False by design).
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = _beat(client, _mint(lid, exp=int(time.time()) - 10 * 86400), lid=lid)
    assert r.status_code == 200, r.text
    assert r.json() == {"license_status": "valid"}


def test_heartbeat_skew_leeway(client):
    now = int(time.time())
    lid_live = uuid.uuid4().hex
    _insert(client, lid_live, expires_at=now - 240)
    r = _beat(client, _mint(lid_live), lid=lid_live)
    assert r.status_code == 200 and r.json() == {"license_status": "valid"}, r.text
    lid_past = uuid.uuid4().hex
    _insert(client, lid_past, expires_at=now - 360)
    r = _beat(client, _mint(lid_past), lid=lid_past)
    assert r.status_code == 200 and r.json() == {"license_status": "expired"}, r.text


def test_heartbeat_missing_bearer(client):
    r = client.post("/v1/licenses/heartbeat", json=_body("x"))
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_heartbeat_tampered_signature(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    token = _mint(lid)
    head, payload, sig = token.split(".")
    mid = len(sig) // 2
    bad_sig = sig[:mid] + ("A" if sig[mid] != "A" else "B") + sig[mid + 1 :]
    bad = ".".join([head, payload, bad_sig])
    r = _beat(client, bad, lid=lid)
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "unauthorized"


def test_heartbeat_alg_none_rejected(client):
    import base64

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    lid = uuid.uuid4().hex
    _insert(client, lid)
    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'license_id': lid})}."
    r = _beat(client, token, lid=lid)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_heartbeat_hs256_rejected_without_hmac_path(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    now = int(time.time())
    token = str(
        jwt.encode(
            {
                "sub": "datatap",
                "iss": ISSUER,
                "aud": "digichat-license",
                "iat": now,
                "exp": now + 86400,
                "jti": lid,
                "license_id": lid,
                "tenant_slug": "datatap",
                "hosts": ["datatapstream.com"],
                "kind": "digichat-license",
            },
            "not-a-real-hmac-secret",
            algorithm="HS256",
        )
    )
    r = _beat(client, token, lid=lid)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_heartbeat_wrong_audience_issuer_kind_claims(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    cases = [
        _mint(uuid.uuid4().hex, aud="digi-ecosystem"),
        _mint(lid, iss="http://someone-else"),
        _mint(lid, kind=None),
    ]
    # A token with no license_id at all: drop both id claims.
    priv, kid = _server_key()
    now = int(time.time())
    no_id = str(
        jwt.encode(
            {
                "sub": "datatap",
                "iss": ISSUER,
                "aud": "digichat-license",
                "iat": now,
                "exp": now + 86400,
                "tenant_slug": "datatap",
                "hosts": ["datatapstream.com"],
                "kind": "digichat-license",
            },
            _priv_pem(priv),
            algorithm="RS256",
            headers={"kid": kid},
        )
    )
    cases.append(no_id)
    for token in cases:
        r = _beat(client, token, lid=lid)
        assert r.status_code == 401, (token[:40], r.text)
        assert r.json()["error"] == "unauthorized"
    # Empty sub still verifies as a license when the id is known-shaped: with no
    # row it answers unknown (the heartbeat checks aud/iss/kind/license_id only).
    lid_empty = uuid.uuid4().hex
    r = _beat(client, _mint(lid_empty, customer=""), lid=lid_empty)
    assert r.status_code == 401 and r.json()["error"] == "unknown_license"


def test_heartbeat_401_bodies_are_only_latch_or_generic(client):
    from digikey.license_heartbeat import HEARTBEAT_401_ERRORS

    assert set(HEARTBEAT_401_ERRORS) == {"license_revoked", "unknown_license", "unauthorized"}
    lid = uuid.uuid4().hex
    _insert(client, lid, revoked=True)
    lid_unknown = uuid.uuid4().hex
    bodies = [
        _beat(client, _mint(lid), lid=lid).json(),  # revoked
        _beat(client, _mint(lid_unknown), lid=lid_unknown).json(),  # unknown
        _beat(client, "garbage-token", lid=lid).json(),  # generic
    ]
    for body in bodies:
        assert body["error"] in HEARTBEAT_401_ERRORS, body


def test_heartbeat_telemetry_mismatch_is_400_never_deny(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    token = _mint(lid)
    bad = _body("different-id")
    r = _beat(client, token, body=bad)
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_heartbeat_body"
    missing = _body(lid)
    del missing["seq"]
    r = _beat(client, token, body=missing)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_heartbeat_body"


def test_heartbeat_malformed_json_is_400(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = client.post(
        "/v1/licenses/heartbeat",
        content="{not json",
        headers={"Authorization": f"Bearer {_mint(lid)}", "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_heartbeat_body"


def test_access_token_rejected_at_heartbeat(client):
    from digikey.jwt_issue import issue_access_token

    priv, kid = _server_key()
    token, _ = issue_access_token(
        priv, kid=kid, sub="key:x", tenant_slug="acme", scopes=["digigraph:chat"]
    )
    r = _beat(client, token, lid="x")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_license_jwt_rejected_at_oauth_token(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = client.post("/v1/oauth/token", json={"grant_type": "api_key", "api_key": _mint(lid)})
    assert r.status_code in (400, 401, 403)


def test_admin_bearer_rejected_at_heartbeat(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = client.post(
        "/v1/licenses/heartbeat",
        json=_body(lid),
        headers={"Authorization": f"Bearer {ADMIN}"},
    )
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_admin_revoke_flips_live_to_revoked(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    token = _mint(lid)
    assert _beat(client, token, lid=lid).status_code == 200
    r = client.post(
        f"/v1/admin/licenses/{lid}/revoke", headers={"Authorization": f"Bearer {ADMIN}"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"revoked": True}
    r = client.post(
        f"/v1/admin/licenses/{lid}/revoke", headers={"Authorization": f"Bearer {ADMIN}"}
    )
    assert r.status_code == 200 and r.json() == {"revoked": True}
    r = _beat(client, token, lid=lid)
    assert r.status_code == 401 and r.json()["error"] == "license_revoked"


def test_admin_revoke_unknown_is_404(client):
    r = client.post(
        "/v1/admin/licenses/no-such-id/revoke", headers={"Authorization": f"Bearer {ADMIN}"}
    )
    assert r.status_code == 404


def test_admin_revoke_requires_admin(client):
    lid = uuid.uuid4().hex
    _insert(client, lid)
    r = client.post(f"/v1/admin/licenses/{lid}/revoke")
    assert r.status_code == 401
    r = client.post(f"/v1/admin/licenses/{lid}/revoke", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_admin_revoke_503_without_admin_env(client, monkeypatch):
    monkeypatch.delenv("DIGIKEY_ADMIN_TOKEN")
    r = client.post("/v1/admin/licenses/x/revoke", headers={"Authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 503


def test_heartbeat_429_is_error_outcome_not_latch(client):
    # Swap in a tight limiter scoped to this test only: rebuilding the global
    # from env would leak the 1/min budget into later tests (their exchanges
    # would 429), so the process-wide limiter is restored in `finally`.
    import digikey.ratelimit as rl

    lid = uuid.uuid4().hex
    _insert(client, lid)
    token = _mint(lid)
    previous = rl._limiter
    rl._limiter = rl.TokenBucketRateLimiter(per_min=1, burst=1)
    try:
        first = _beat(client, token, lid=lid)
        assert first.status_code == 200, first.text
        second = _beat(client, token, lid=lid)
        assert second.status_code == 429, second.text
        assert "error" not in second.json()
    finally:
        rl._limiter = previous
        previous.reset()


def test_secret_hygiene_no_raw_jwt_in_logs_or_bodies(client, caplog):
    lid = uuid.uuid4().hex
    _insert(client, lid, revoked=True)
    token = _mint(lid)
    with caplog.at_level(logging.INFO, logger="digikey.server"):
        r_ok = _beat(client, token, lid=lid)
        r_bad = _beat(client, "cellar-token", lid=lid)
    assert r_ok.status_code == 401
    assert token not in caplog.text
    assert "Authorization" not in caplog.text
    assert "PRIVATE KEY" not in caplog.text
    assert token not in r_ok.text
    assert token not in r_bad.text
