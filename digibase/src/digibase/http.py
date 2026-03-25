"""Outbound HTTP helpers for service-to-service calls."""

from __future__ import annotations


def outbound_request_id_headers(request_id: str | None) -> dict[str, str] | None:
    """Return headers dict for X-Request-ID, or None when *request_id* is empty."""
    if request_id and str(request_id).strip():
        return {"X-Request-ID": str(request_id).strip()}
    return None


def outbound_service_headers(
    request_id: str | None,
    bearer_token: str | None,
    *,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Merge correlation id, optional Bearer (DigiKey JWT or legacy API key material), and extra headers.
    *bearer_token* must be the raw secret or JWT (no ``Bearer `` prefix).
    """
    h: dict[str, str] = {}
    rid = outbound_request_id_headers(request_id)
    if rid:
        h.update(rid)
    if bearer_token and str(bearer_token).strip():
        h["Authorization"] = f"Bearer {str(bearer_token).strip()}"
    if extra:
        h.update({k: v for k, v in extra.items() if v})
    return h


__all__ = ["outbound_request_id_headers", "outbound_service_headers"]
