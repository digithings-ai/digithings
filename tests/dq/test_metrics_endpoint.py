"""Smoke test: DigiQuant exposes /metrics with service/version/environment labels."""

from __future__ import annotations

import pytest

pytest.importorskip("nautilus_trader")

from fastapi.testclient import TestClient  # noqa: E402

from digiquant.server import app  # noqa: E402
from tests.conftest import assert_prom_metrics_labels  # noqa: E402

pytestmark = pytest.mark.unit


def test_metrics_endpoint_live() -> None:
    client = TestClient(app)
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert_prom_metrics_labels(r.text, service="digiquant")
