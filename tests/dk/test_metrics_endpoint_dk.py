"""Smoke test: DigiKey exposes /metrics with service/version/environment labels."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")

from digikey.server import app  # noqa: E402

pytestmark = pytest.mark.unit


def test_metrics_endpoint_live() -> None:
    client = TestClient(app)
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'service="digikey"' in body
    assert 'version="' in body
    assert 'environment="' in body
