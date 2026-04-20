"""Prometheus metrics helper for DigiThings FastAPI services.

Provides :func:`install_metrics` which mounts a ``/metrics`` endpoint and an ASGI
middleware that records standard HTTP metrics (request count, duration, in-flight)
for the given FastAPI application.

Design notes:

* Route labels are collapsed to the *matched* FastAPI route template (e.g.
  ``/items/{item_id}``) instead of the raw request path so cardinality stays
  bounded. Requests that do not match any route are labelled ``"<unmatched>"``.
* Collectors are registered on the default global ``REGISTRY`` once per
  (service, metric-name) pair — calling :func:`install_metrics` repeatedly is
  safe across tests that build throwaway FastAPI apps.
* The ``/metrics`` response uses the documented Prometheus text content type
  ``text/plain; version=0.0.4; charset=utf-8``.

See ADR-0003 for the design rationale.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["install_metrics"]

# ADR-0003 pins the Prometheus text exposition content type we emit. Newer
# prometheus_client releases default ``CONTENT_TYPE_LATEST`` to
# ``version=1.0.0`` (OpenMetrics), but the broad Prometheus ecosystem — and the
# ADR itself — expects the ``0.0.4`` plain-text format. Hardcode it so the
# contract is stable regardless of library version.
_PROM_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Prometheus metric names are stable identifiers shared across services; the
# service-label disambiguates which emitter produced the sample. We register the
# collectors lazily and cache them by name so we never hit the
# ``Duplicated timeseries`` error when install_metrics is called multiple times
# (e.g. in the unit-test suite).
_METRIC_CACHE: dict[str, Any] = {}

_REQUEST_LABELS = ("service", "version", "environment", "method", "route", "status")
_INFLIGHT_LABELS = ("service", "version", "environment")

# Histogram buckets in seconds — tuned for typical HTTP API latencies; the
# default prometheus_client buckets top out at 10s which is plenty for our
# services (any slower request is already broken).
_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _get_or_create(name: str, factory):
    """Return the cached collector for *name*, creating it via *factory* if needed.

    Guards against ``ValueError: Duplicated timeseries`` when the module is
    re-imported or ``install_metrics`` is invoked multiple times in one process.
    """
    cached = _METRIC_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        collector = factory()
    except ValueError:
        # Another import path registered it on the same REGISTRY; fish it out.
        existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
        if existing is None:
            raise
        collector = existing
    _METRIC_CACHE[name] = collector
    return collector


def _requests_total() -> Counter:
    return _get_or_create(
        "http_requests_total",
        lambda: Counter(
            "http_requests_total",
            "Total HTTP requests processed, labelled by service/method/route/status.",
            _REQUEST_LABELS,
        ),
    )


def _request_duration_seconds() -> Histogram:
    return _get_or_create(
        "http_request_duration_seconds",
        lambda: Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds, labelled by service/method/route/status.",
            _REQUEST_LABELS,
            buckets=_DURATION_BUCKETS,
        ),
    )


def _requests_in_flight() -> Gauge:
    return _get_or_create(
        "http_requests_in_flight",
        lambda: Gauge(
            "http_requests_in_flight",
            "Number of HTTP requests currently being processed.",
            _INFLIGHT_LABELS,
        ),
    )


def _match_route_template(app: FastAPI, scope: Scope) -> str:
    """Return the matched FastAPI route template for *scope*, or ``"<unmatched>"``.

    Iterates the app's router and finds the first fully-matching route, using
    Starlette's own matcher to stay consistent with how FastAPI dispatches
    requests. This bounds the ``route`` label cardinality to the number of
    declared routes.
    """
    if scope.get("type") != "http":
        return "<unmatched>"
    for route in app.router.routes:
        try:
            match, _ = route.matches(scope)
        except Exception:
            continue
        if match == Match.FULL:
            template = getattr(route, "path", None)
            if template:
                return template
    return "<unmatched>"


class _PrometheusMiddleware:
    """ASGI middleware that records request count, duration, and in-flight gauge."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        fastapi_app: FastAPI,
        service: str,
        version: str,
        environment: str,
    ) -> None:
        self._app = app
        self._fastapi_app = fastapi_app
        self._service = service
        self._version = version
        self._environment = environment
        self._counter = _requests_total()
        self._histogram = _request_duration_seconds()
        self._in_flight = _requests_in_flight()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        # Skip instrumenting the /metrics scrape itself to avoid recursive
        # cardinality blow-up on every Prometheus poll.
        if scope.get("path") == "/metrics":
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        route = _match_route_template(self._fastapi_app, scope)
        status_holder: dict[str, int] = {"status": 500}

        async def _send(message: Any) -> None:
            if message.get("type") == "http.response.start":
                status_holder["status"] = int(message.get("status", 500))
            await send(message)

        self._in_flight.labels(
            service=self._service,
            version=self._version,
            environment=self._environment,
        ).inc()
        start = time.perf_counter()
        try:
            await self._app(scope, receive, _send)
        finally:
            elapsed = time.perf_counter() - start
            self._in_flight.labels(
                service=self._service,
                version=self._version,
                environment=self._environment,
            ).dec()
            status = str(status_holder["status"])
            self._counter.labels(
                service=self._service,
                version=self._version,
                environment=self._environment,
                method=method,
                route=route,
                status=status,
            ).inc()
            self._histogram.labels(
                service=self._service,
                version=self._version,
                environment=self._environment,
                method=method,
                route=route,
                status=status,
            ).observe(elapsed)


def install_metrics(
    app: FastAPI,
    *,
    service: str,
    version: str | None = None,
    environment: str | None = None,
) -> None:
    """Install Prometheus metrics collection on *app*.

    Mounts ``GET /metrics`` returning the default global ``REGISTRY`` in
    Prometheus text exposition format, and registers an ASGI middleware that
    records request count, duration, and in-flight gauge labelled by
    ``service``, ``version``, ``environment``, ``method``, ``route`` (collapsed
    to the matched route template), and ``status``.

    ``version`` defaults to ``"0.1.0"`` when omitted. ``environment`` defaults
    to ``$DIGI_ENV`` or ``"dev"`` so local runs get a stable label without
    forcing callers to plumb it through. The label set is intentionally small
    so per-series cardinality stays bounded even across many deploys.
    """
    if not service:
        raise ValueError("install_metrics requires a non-empty 'service' label")

    resolved_version = (version or "0.1.0").strip() or "0.1.0"
    resolved_env = (
        (environment or os.environ.get("DIGI_ENV") or "dev").strip() or "dev"
    )

    # Prime the collectors so the metric names exist on REGISTRY even before the
    # first request arrives (useful for initial scrapes).
    _requests_total()
    _request_duration_seconds()
    _requests_in_flight()

    app.add_middleware(
        _PrometheusMiddleware,
        fastapi_app=app,
        service=service,
        version=resolved_version,
        environment=resolved_env,
    )

    @app.get("/metrics", include_in_schema=False)
    def _metrics() -> Response:
        return Response(
            content=generate_latest(REGISTRY),
            media_type=_PROM_CONTENT_TYPE,
        )
