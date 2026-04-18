"""DigiThings shared platform utilities (HTTP, errors, audit redaction, optional OTel)."""

from digibase.http import outbound_request_id_headers

__all__ = [
    "outbound_request_id_headers",
]
