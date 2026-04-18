"""DigiQuant /v1/jobs API (async backtest lifecycle)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from digiquant.server import app
from tests.digi_test_jwt import auth_headers


@pytest.mark.unit
def test_v1_jobs_backtest_returns_job_id() -> None:
    with patch("digiquant.server.threading.Thread") as tmock:
        tmock.return_value.start = MagicMock()
        client = TestClient(app, headers=auth_headers())
        r = client.post(
            "/v1/jobs/backtest",
            json={
                "strategy_name": "mean_reversion_stat_arb",
                "symbols": ["AAPL"],
                "data_dir": "/tmp",
            },
        )
    assert r.status_code == 200
    assert r.json().get("job_id")


@pytest.mark.unit
def test_v1_job_status_unknown_404() -> None:
    client = TestClient(app, headers=auth_headers())
    r = client.get("/v1/jobs/nonexistentjobid00000000000000/status")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "http_404"
