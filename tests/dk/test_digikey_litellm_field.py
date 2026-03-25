"""DigiKey token response includes litellm_proxy_api_key when DIGIKEY_LITELLM_PROXY_KEY is set."""

from __future__ import annotations

import os
from pathlib import Path

# Signing key loads at digikey.server import — allow ephemeral RS256 for unit tests.
if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")

import digikey.db as digikey_db
import pytest
from fastapi.testclient import TestClient

from digikey.db import init_db, session_factory
from digikey.db_schema import ApiKeyRow
from digikey.key_crypto import generate_raw_key, hash_secret
from digikey.server import app


@pytest.mark.unit
def test_oauth_token_includes_litellm_proxy_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "digikey.sqlite"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_DEV_GLOBAL", "1")
    monkeypatch.setenv("DIGIKEY_LITELLM_PROXY_KEY", "sk-shared-lite")
    digikey_db._engine = None
    digikey_db._session_factory = None
    init_db()

    raw, prefix = generate_raw_key()
    row = ApiKeyRow(
        key_hash=hash_secret(raw),
        key_prefix=prefix,
        tenant_slug="t1",
        scopes=["*"],
        kind="dev_global",
        label="test",
    )
    sf = session_factory()
    with sf() as session:
        session.add(row)
        session.commit()

    client = TestClient(app)
    r = client.post("/v1/oauth/token", json={"grant_type": "api_key", "api_key": raw})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("access_token")
    assert data.get("litellm_proxy_api_key") == "sk-shared-lite"
