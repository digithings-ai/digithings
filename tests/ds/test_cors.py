"""CORS allowlist tests for DigiSearch (uses shared digibase.cors helper)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from digibase.cors import install_cors

SERVICE = "digisearch"


def _build(monkeypatch: pytest.MonkeyPatch, origins: str) -> TestClient:
    monkeypatch.delenv("DIGISEARCH_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("DIGI_CORS_ORIGINS", origins)
    app = FastAPI()
    install_cors(app, service=SERVICE)

    @app.post("/probe")
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
            "Access-Control-Request-Method": "POST",
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
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None


@pytest.mark.unit
def test_empty_default_blocks_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_ALLOWED_ORIGINS", raising=False)
    app = FastAPI()
    install_cors(app, service=SERVICE)

    @app.post("/probe")
    def _probe() -> dict[str, str]:
        return {"ok": "1"}

    client = TestClient(app)
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://any.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None
