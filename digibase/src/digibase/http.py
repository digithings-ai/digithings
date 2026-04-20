"""Outbound HTTP helpers and inbound X-Request-ID correlation middleware.

X-Request-ID propagation pattern (task #213):
    - Inbound: :func:`install_request_id_middleware` reads ``X-Request-ID`` from
      the request, generates one if absent, stores it on ``request.state.request_id``
      and in a ContextVar (:func:`current_request_id`), and echoes it on the
      response.
    - Logging: :class:`RequestIdLogFilter` injects ``request_id`` onto every
      ``LogRecord`` so formatters can reference ``%(request_id)s``. Outside a
      request (startup, background tasks), the value falls back to ``"-"``.
    - Outbound: :func:`outbound_service_headers` (or its narrower sibling
      :func:`outbound_request_id_headers`) attaches the id to service-to-service
      calls.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

_REQUEST_ID_CTX: ContextVar[str | None] = ContextVar("digi_request_id", default=None)
"""ContextVar holding the current request's id, or ``None`` outside a request."""

_UNSET_REQUEST_ID = "-"
"""Placeholder used in log records emitted outside of any request."""


def current_request_id() -> str | None:
    """Return the X-Request-ID for the in-flight request, or ``None`` if unset."""
    return _REQUEST_ID_CTX.get()


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


def _coerce_inbound_request_id(raw: str | None) -> str:
    """Trim the inbound header; generate a hex id when missing or blank."""
    if raw is None:
        return uuid.uuid4().hex
    cleaned = raw.strip()
    return cleaned or uuid.uuid4().hex


def install_request_id_middleware(app: FastAPI) -> None:
    """Register X-Request-ID correlation middleware on *app*.

    Must be registered **after** any rate-limit middleware so the id wraps
    rate-limit rejections and error handlers — Starlette applies ``@middleware``
    in LIFO order (last registered runs outermost).

    Behavior:
        - Reads ``X-Request-ID`` from the incoming request; generates a uuid4
          hex when absent or blank.
        - Stores the id on ``request.state.request_id`` (compat with existing
          ``digibase.errors`` handlers and per-service resolvers).
        - Binds the id to :data:`_REQUEST_ID_CTX` for the duration of the
          request so log records and outbound helpers can read it without
          threading the ``Request`` through every call site.
        - Echoes the id on the response's ``X-Request-ID`` header.
    """

    @app.middleware("http")
    async def _correlation_id(request: Request, call_next):
        req_id = _coerce_inbound_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = req_id
        token = _REQUEST_ID_CTX.set(req_id)
        try:
            response = await call_next(request)
        finally:
            _REQUEST_ID_CTX.reset(token)
        response.headers["X-Request-ID"] = req_id
        return response


class RequestIdLogFilter(logging.Filter):
    """Inject ``request_id`` onto every ``LogRecord``.

    Attach once at process start (see :func:`install_request_id_logging`) so
    formatters can safely reference ``%(request_id)s`` — records created
    outside a request get :data:`_UNSET_REQUEST_ID` rather than raising
    ``KeyError`` in the formatter.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = _REQUEST_ID_CTX.get() or _UNSET_REQUEST_ID
        return True


def install_request_id_logging(logger: logging.Logger | None = None) -> RequestIdLogFilter:
    """Attach :class:`RequestIdLogFilter` to *logger* (defaults to root).

    Idempotent: re-attaching on hot reload won't stack filters. Returns the
    filter instance so tests can assert its presence.
    """
    target = logger or logging.getLogger()
    for existing in target.filters:
        if isinstance(existing, RequestIdLogFilter):
            return existing
    flt = RequestIdLogFilter()
    target.addFilter(flt)
    return flt


__all__ = [
    "RequestIdLogFilter",
    "current_request_id",
    "install_request_id_logging",
    "install_request_id_middleware",
    "outbound_request_id_headers",
    "outbound_service_headers",
]
