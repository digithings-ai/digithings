"""CORS allowlist tests for DigiSmith (uses shared digibase.cors helper)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from digibase.cors import install_cors

SERVICE = "digismith"


def _build(monkeypatch: pytest.MonkeyPatch, origins: str) -> TestClient:
    monkeypatch.delenv("DIGISMITH_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("DIGI_CORS_ORIGINS", origins)
    app = FastAPI()
    install_cors(app, service=SERVICE)

    @app.get("/probe")
    def _probe() -> dict[str, str]:
        return {"ok": "1"}

    return TestClient(app)


@pytest.mark.unit
def test_allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build(monkeypatch, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "https://allowed.example"


@pytest.mark.unit
def test_disallowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build(monkeypatch, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None
