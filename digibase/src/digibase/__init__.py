"""DigiThings shared platform utilities (HTTP, errors, audit redaction, metrics, optional OTel)."""

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
    "DEFAULT_TIMEOUT",
    "async_client",
    "current_request_id",
    "install_cors",
    "install_metrics",
    "install_request_id_logging",
    "install_request_id_middleware",
    "outbound_request_id_headers",
    "outbound_service_headers",
    "resolve_cors_origins",
    "sync_client",
]
