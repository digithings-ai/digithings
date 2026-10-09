"""digithings shared platform utilities (HTTP, errors, audit redaction, metrics, optional OTel)."""

from digibase.art9 import (
    ART9_CATEGORIES,
    CONTROL_PLANE_PREFIXES,
    CONTROL_PLANE_ROUTES,
    INGEST_PREFIXES,
    INGEST_ROUTES,
    ROUTE_KIND_INGEST,
    ROUTE_KIND_READ,
    ROUTE_UNREGISTERED,
    RouteDecision,
    check_route,
    is_control_plane,
    is_registered,
    is_under_prefix,
    iter_ingest_routes,
    route_kind,
)
from digibase.cors import install_cors, resolve_cors_origins
from digibase.http import (
    current_request_id,
    install_request_id_logging,
    install_request_id_middleware,
    outbound_request_id_headers,
    outbound_service_headers,
)
from digibase.http_client import DEFAULT_TIMEOUT, async_client, sync_client
from digibase.metrics import install_metrics

__all__ = [
    "ART9_CATEGORIES",
    "CONTROL_PLANE_PREFIXES",
    "CONTROL_PLANE_ROUTES",
    "DEFAULT_TIMEOUT",
    "INGEST_PREFIXES",
    "INGEST_ROUTES",
    "ROUTE_KIND_INGEST",
    "ROUTE_KIND_READ",
    "ROUTE_UNREGISTERED",
    "RouteDecision",
    "async_client",
    "check_route",
    "current_request_id",
    "install_cors",
    "install_metrics",
    "install_request_id_logging",
    "install_request_id_middleware",
    "is_control_plane",
    "is_registered",
    "is_under_prefix",
    "iter_ingest_routes",
    "outbound_request_id_headers",
    "outbound_service_headers",
    "resolve_cors_origins",
    "route_kind",
    "sync_client",
]
