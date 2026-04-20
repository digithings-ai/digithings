"""Smoke test: DigiSearch exposes /metrics with service/version/environment labels."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digisearch.server import app

pytestmark = pytest.mark.unit


def test_metrics_endpoint_live() -> None:
    client = TestClient(app)
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'service="digisearch"' in body
    assert 'version="' in body
    assert 'environment="' in body
