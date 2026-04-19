"""CORS allowlist tests for DigiGraph.

Exercises the shared :func:`digibase.cors.install_cors` helper as wired into
``digigraph.server``: an allowed origin receives an ``access-control-allow-origin``
reflection on preflight; a disallowed origin does not.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from digibase.cors import install_cors

SERVICE = "digigraph"


def _fresh_client(monkeypatch: pytest.MonkeyPatch, origins: str) -> TestClient:
    # Clear all three precedence tiers so the test's intent is unambiguous.
    monkeypatch.delenv("DIGIGRAPH_CORS_ORIGINS", raising=False)
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
def test_allowed_origin_reflected_in_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fresh_client(monkeypatch, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://allowed.example"


@pytest.mark.unit
def test_disallowed_origin_rejected_in_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fresh_client(monkeypatch, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Starlette returns 400 for preflight from non-allowlisted origins; regardless,
    # the reflection header must be absent.
    assert r.headers.get("access-control-allow-origin") is None


@pytest.mark.unit
def test_per_service_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_CORS_ORIGINS", "https://global.example")
    monkeypatch.setenv("DIGIGRAPH_CORS_ORIGINS", "https://override.example")
    app = FastAPI()
    install_cors(app, service=SERVICE)

    @app.post("/probe")
    def _probe() -> dict[str, str]:
        return {"ok": "1"}

    client = TestClient(app)
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://override.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "https://override.example"

    r2 = client.options(
        "/probe",
        headers={
            "Origin": "https://global.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r2.headers.get("access-control-allow-origin") is None
