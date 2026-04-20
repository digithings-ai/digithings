"""Unit tests for digibase.metrics.install_metrics."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from digibase.metrics import install_metrics

pytestmark = pytest.mark.unit


def _build_app(
    service: str = "digitest",
    *,
    version: str | None = None,
    environment: str | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item": item_id}

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise HTTPException(status_code=418, detail="nope")

    install_metrics(app, service=service, version=version, environment=environment)
    return app


def test_metrics_endpoint_content_type_and_format() -> None:
    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    # Prometheus text exposition content type (exact shape per ADR-0003).
    assert resp.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in resp.headers["content-type"]
    assert "charset=utf-8" in resp.headers["content-type"]
    body = resp.text
    # All three instrument families are registered up-front (even before traffic).
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "http_requests_in_flight" in body


def test_counter_increments_with_service_method_route_status_labels() -> None:
    app = _build_app(service="digitest_counter")
    with TestClient(app) as client:
        client.get("/ping")
        client.get("/items/42")
        client.get("/items/99")
        body = client.get("/metrics").text

    # Route label is collapsed to the matched template, not the raw path.
    assert 'service="digitest_counter"' in body
    assert 'route="/ping"' in body
    assert 'route="/items/{item_id}"' in body
    # Raw path params must not leak into labels (cardinality guard).
    assert 'route="/items/42"' not in body
    assert 'method="GET"' in body
    assert 'status="200"' in body


def test_histogram_records_duration_with_expected_labels() -> None:
    app = _build_app(service="digitest_hist")
    with TestClient(app) as client:
        client.get("/ping")
        body = client.get("/metrics").text

    # Histogram exports _bucket, _count, _sum series with full label set.
    assert "http_request_duration_seconds_bucket" in body
    assert "http_request_duration_seconds_count" in body
    assert "http_request_duration_seconds_sum" in body
    assert 'service="digitest_hist"' in body
    assert 'route="/ping"' in body


def test_in_flight_gauge_registered() -> None:
    app = _build_app(service="digitest_gauge")
    with TestClient(app) as client:
        client.get("/ping")
        body = client.get("/metrics").text

    # Gauge carries deploy-identity labels (service/version/environment) but
    # not the per-request labels (method/route/status).
    assert "http_requests_in_flight" in body
    assert 'service="digitest_gauge"' in body
    assert 'version="0.1.0"' in body
    assert 'environment="dev"' in body


def test_version_and_environment_labels_flow_from_install_args() -> None:
    """Explicit version/environment kwargs land on every series, not just defaults."""
    app = _build_app(
        service="digitest_labels",
        version="2.7.1",
        environment="staging",
    )
    with TestClient(app) as client:
        client.get("/ping")
        body = client.get("/metrics").text
    assert 'version="2.7.1"' in body
    assert 'environment="staging"' in body


def test_environment_label_defaults_to_digi_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``environment`` is omitted, the helper reads ``DIGI_ENV``."""
    monkeypatch.setenv("DIGI_ENV", "prod")
    app = _build_app(service="digitest_env_fallback")
    with TestClient(app) as client:
        client.get("/ping")
        body = client.get("/metrics").text
    assert 'environment="prod"' in body


def test_http_error_status_recorded() -> None:
    app = _build_app(service="digitest_err")
    with TestClient(app) as client:
        resp = client.get("/boom")
        assert resp.status_code == 418
        body = client.get("/metrics").text

    # 418 status ends up on the counter label without dropping the request.
    assert 'status="418"' in body
    assert 'route="/boom"' in body


def test_metrics_endpoint_itself_is_not_counted() -> None:
    app = _build_app(service="digitest_self")
    with TestClient(app) as client:
        # Hit /metrics twice; neither call should increment http_requests_total.
        first = client.get("/metrics").text
        second = client.get("/metrics").text

    # The /metrics route must not appear as a labelled series — we explicitly
    # skip instrumenting it to avoid cardinality/recursion on every scrape.
    assert 'route="/metrics"' not in first
    assert 'route="/metrics"' not in second


def test_install_metrics_requires_service_label() -> None:
    app = FastAPI()
    with pytest.raises(ValueError):
        install_metrics(app, service="")
