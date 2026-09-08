"""Cross-service HTTP surface contracts — CORS, /healthz, /metrics (#1196).

Parametrized over the always-on Compose services that share digibase CORS and
the liveness/metrics conventions. Optional Compose profiles are listed in
``OPTIONAL_PROFILE_SKIP`` and intentionally omitted here — their dedicated
suites under ``tests/dv/`` (etc.) still cover them.

Run::

    pytest -m unit tests/contracts/test_cross_service_surface.py
"""

from __future__ import annotations

import os
from typing import (
    Any,  # score:allow untyped any — FastAPI app factory return for parametrized services
)

import pytest
from digibase.cors import install_cors
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import assert_prom_metrics_labels

# Always-on HTTP services with digibase CORS + /healthz + /metrics.
CORS_SERVICES = ("digigraph", "digiquant", "digisearch", "digismith", "digikey")

# Optional Compose profiles — not parametrized here; see per-component suites.
OPTIONAL_PROFILE_SKIP = (
    "digivault",  # profile digivault — tests/dv/
    "digichat",  # Next.js BFF — Vitest under frontend/digichat/
)

pytestmark = pytest.mark.unit


def _cors_client(monkeypatch: pytest.MonkeyPatch, service: str, origins: str) -> TestClient:
    monkeypatch.delenv(f"{service.upper()}_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DIGI_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("DIGI_CORS_ORIGINS", origins)
    app = FastAPI()
    install_cors(app, service=service)

    @app.get("/probe")
    def _probe() -> dict[str, str]:
        return {"ok": "1"}

    return TestClient(app)


@pytest.mark.parametrize("service", CORS_SERVICES)
def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch, service: str) -> None:
    client = _cors_client(monkeypatch, service, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "https://allowed.example"


@pytest.mark.parametrize("service", CORS_SERVICES)
def test_cors_rejects_unknown_origin(monkeypatch: pytest.MonkeyPatch, service: str) -> None:
    client = _cors_client(monkeypatch, service, "https://allowed.example")
    r = client.options(
        "/probe",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None


def _load_app(service: str) -> Any:
    """Import the FastAPI app for ``service``, applying digikey's ephemeral-key gate."""
    if service == "digikey" and not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
        os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    if service == "digiquant":
        pytest.importorskip("nautilus_trader")
    mod = __import__(f"{service}.server", fromlist=["app"])
    return mod.app


HEALTHZ_SERVICES = ("digigraph", "digisearch", "digismith", "digikey", "digiquant")
METRICS_SERVICES = ("digigraph", "digisearch", "digismith", "digikey", "digiquant")


@pytest.mark.parametrize("service", HEALTHZ_SERVICES)
def test_healthz_ok_shape(service: str) -> None:
    client = TestClient(_load_app(service))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.parametrize("service", METRICS_SERVICES)
def test_metrics_exposes_service_label(service: str) -> None:
    client = TestClient(_load_app(service))
    # Warm instrumentation the same way the per-service smoke tests do.
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert_prom_metrics_labels(r.text, service=service)


def test_optional_profile_skip_list_documented() -> None:
    """Keep the skip list visible so optional profiles are not silently dropped."""
    assert "digivault" in OPTIONAL_PROFILE_SKIP
    assert "digichat" in OPTIONAL_PROFILE_SKIP
