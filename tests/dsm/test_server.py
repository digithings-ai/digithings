"""Unit tests for digitrace.server."""

from __future__ import annotations

import pytest
from digitrace.server import app
from fastapi.testclient import TestClient

_client = TestClient(app)


@pytest.mark.unit
def test_health() -> None:
    r = _client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.unit
def test_status_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    r = _client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert body["tracing_configured"] in (True, False)
    assert body["langsmith_sdk_installed"] in (True, False)
    assert "langsmith_host" in body


@pytest.mark.unit
def test_status_never_exposes_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_super_secret_token_do_not_leak")
    r = _client.get("/v1/status")
    assert r.status_code == 200
    assert "super_secret_token" not in r.text
    assert "lsv2_" not in r.text


@pytest.mark.unit
def test_smith_status_compat_alias() -> None:
    """Phase 0 compat (#4929): pre-rename SmithStatus aliases TraceStatus."""
    from digitrace.config import SmithStatus, TraceStatus

    assert SmithStatus is TraceStatus
