"""Smoke test: DigiGraph exposes /metrics with service/version/environment labels."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digigraph.server import app

pytestmark = pytest.mark.unit


def test_metrics_endpoint_live() -> None:
    client = TestClient(app)
    # Generate a labeled observation first so that counter/histogram have lines.
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'service="digigraph"' in body
    assert 'version="' in body
    assert 'environment="' in body
