"""DigiThings shared platform utilities (HTTP, errors, audit redaction, metrics, optional OTel)."""

from digibase.http import outbound_request_id_headers
from digibase.http_client import DEFAULT_TIMEOUT, async_client, sync_client
from digibase.metrics import install_metrics

__all__ = [
    "DEFAULT_TIMEOUT",
    "async_client",
    "install_metrics",
    "outbound_request_id_headers",
    "sync_client",
]
