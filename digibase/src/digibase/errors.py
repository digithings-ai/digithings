"""Consistent JSON error responses for DigiThings HTTP APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiErrorBody(BaseModel):
    """Standard error envelope (v1)."""

    code: str = Field(
        ..., description="Stable machine-readable code, e.g. http_404, validation_error"
    )
    message: str = Field(..., description="Human-readable message")
    request_id: str | None = Field(None, description="Correlates with X-Request-ID when present")
    service: str | None = Field(None, description="Originating service name")


class ApiErrorEnvelope(BaseModel):
    """Wrapper used across DigiThings public HTTP APIs."""

    error: ApiErrorBody


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    if rid and str(rid).strip():
        return str(rid).strip()
    h = (request.headers.get("X-Request-ID") or "").strip()
    return h or None


def json_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request | None = None,
    service: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSONResponse with the standard ``error`` object."""
    req_id = _request_id(request) if request is not None else None
    body = ApiErrorEnvelope(
        error=ApiErrorBody(code=code, message=message, request_id=req_id, service=service),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def register_fastapi_error_handlers(app: Any, *, service: str) -> None:
    """Register handlers for HTTPException and RequestValidationError.

    *app* should be a FastAPI instance. ``request.state.request_id`` should be set by correlation middleware.

    Nested ``_http_exc`` / ``_validation`` handlers are registered on *app* at runtime;
    static analyzers (vulture) may flag them as unused — that is expected (SIMP-022).
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else str(detail)
        return json_error_response(
            status_code=exc.status_code,
            code=f"http_{exc.status_code}",
            message=message,
            request=request,
            service=service,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = exc.errors()
        message = str(errs[0].get("msg", "validation error")) if errs else "Validation error"
        return json_error_response(
            status_code=422,
            code="validation_error",
            message=message,
            request=request,
            service=service,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        req_id = _request_id(request)
        headers = {"X-Request-ID": req_id} if req_id else None
        return json_error_response(
            status_code=500,
            code="internal_error",
            message="Internal server error",
            request=request,
            service=service,
            headers=headers,
        )


__all__ = [
    "ApiErrorBody",
    "ApiErrorEnvelope",
    "json_error_response",
    "register_fastapi_error_handlers",
]
