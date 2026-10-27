"""Unit tests for digitrace.server."""

from __future__ import annotations

import pytest
from digitrace.server import app
from fastapi.testclient import TestClient

_client = TestClient(app)

_OTLP_ENVS = ("DIGI_OTEL_ENDPOINT", "DIGITRACE_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")


@pytest.mark.unit
def test_health() -> None:
    r = _client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.unit
def test_status_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (*_OTLP_ENVS, "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGFUSE_HOST"):
        monkeypatch.delenv(key, raising=False)
    r = _client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert body["tracing_configured"] is False
    assert body["otel_export_configured"] is False
    assert body["export_backend"] == "none"
    # Optional integrations report their (absent) state without implying a vendor backend.
    assert body["langfuse_configured"] is False
    assert body["dual_export"] is False
    assert body["langsmith_host"] is None
    assert body["langfuse_host"] is None


@pytest.mark.unit
def test_status_defaults_to_in_house_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://digitrace:8003/v1/otlp")
    body = _client.get("/v1/status").json()
    assert body["export_backend"] == "otel"
    assert body["tracing_configured"] is True


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
