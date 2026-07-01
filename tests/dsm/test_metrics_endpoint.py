"""Smoke test: DigiSmith exposes /metrics with service/version/environment labels."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digismith.server import app
from tests.conftest import assert_prom_metrics_labels

pytestmark = pytest.mark.unit


def test_metrics_endpoint_live() -> None:
    client = TestClient(app)
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert_prom_metrics_labels(r.text, service="digismith")
