"""Shared FastAPI auth: DigiKey JWT verification and scope enforcement."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import jwt
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from digikey import blocklist
from digikey.jwt_verify import decode_token
from digikey.models import DigiAuthContext, claims_to_context
from digikey.scopes import scope_grants_required

logger = logging.getLogger(__name__)

PathScopeFn = Callable[[str, str], list[str] | None]
"""(method, path) -> required scopes, or None if route is auth-exempt."""

_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)
"""Paths every service treats as auth-exempt (liveness, observability, OpenAPI)."""


def bearer_from_request(request: Request) -> str | None:
    h = request.headers.get("Authorization") or ""
    if h.startswith("Bearer "):
        t = h[7:].strip()
        return t or None
    return None


def digikey_auth_active() -> bool:
    return bool(
        (os.environ.get("DIGIKEY_JWKS_URL") or "").strip()
        or (os.environ.get("DIGIKEY_PUBLIC_KEY_PEM") or "").strip()
    )


def _tenant_headers(request: Request) -> str:
    return (
        request.headers.get("X-Digi-Tenant") or request.headers.get("X-Digichat-Tenant") or ""
    ).strip()


def jwt_context(
    request: Request, raw_bearer: str, required_scopes: list[str]
) -> DigiAuthContext | JSONResponse:
    try:
        claims = decode_token(raw_bearer)
    except jwt.exceptions.PyJWTError as e:
        logger.debug("JWT verify failed: %s", e)
        return JSONResponse(
            status_code=401, content={"code": "invalid_token", "message": "Invalid token"}
        )
    except Exception as e:
        logger.debug("JWT verify error: %s", e)
        return JSONResponse(
            status_code=401, content={"code": "invalid_token", "message": "Invalid token"}
        )
    # Post-signature revocation check (ADR-0007). When Redis is unreachable we
    # fail closed — the alternative is silently accepting revoked tokens.
    if claims.jti and blocklist.is_configured():
        try:
            if blocklist.is_blocked(claims.jti):
                return JSONResponse(
                    status_code=401,
                    content={"code": "token_revoked", "message": "Token has been revoked"},
                )
        except blocklist.BlocklistUnavailable as e:
            logger.error("blocklist check failed: %s", e)
            return JSONResponse(
                status_code=503,
                content={
                    "code": "auth_backend_unavailable",
                    "message": "Auth backend temporarily unavailable",
                },
            )
    if required_scopes and not scope_grants_required(claims.scopes, required_scopes):
        return JSONResponse(
            status_code=403,
            content={"code": "insufficient_scope", "message": "Insufficient scope"},
        )
    ctx = claims_to_context(claims, bearer_token=raw_bearer)
    ctx.caller_service = (request.headers.get("X-Digi-Caller") or "").strip() or None
    if not ctx.tenant_slug and (tn := _tenant_headers(request)):
        ctx.tenant_slug = tn
    return ctx


class DigiAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        service: str,
        path_scopes: PathScopeFn,
    ) -> None:
        super().__init__(app)
        self.service = service
        self.path_scopes = path_scopes

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() == "OPTIONS":
            return await call_next(request)
        method = request.method.upper()
        path = request.url.path
        required = self.path_scopes(method, path)
        if required is None:
            return await call_next(request)

        if not digikey_auth_active():
            return JSONResponse(
                status_code=503,
                content={
                    "code": "auth_not_configured",
                    "message": "Set DIGIKEY_JWKS_URL or DIGIKEY_PUBLIC_KEY_PEM for JWT verification",
                },
            )

        raw = bearer_from_request(request)
        if not raw:
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Bearer token required"},
            )
        ctx = jwt_context(request, raw, required)
        if isinstance(ctx, JSONResponse):
            return ctx
        request.state.digi_auth = ctx
        request.state.digi_bearer = ctx.bearer_token
        return await call_next(request)


def attach_digi_auth_middleware(app: FastAPI, *, service: str, path_scopes: PathScopeFn) -> None:
    app.add_middleware(DigiAuthMiddleware, service=service, path_scopes=path_scopes)


def digigraph_path_scopes(method: str, path: str) -> list[str] | None:
    if path in _PUBLIC_PATHS:
        return None
    if path == "/workflow" and method == "POST":
        return ["digigraph:workflow"]
    if path.startswith("/v1/chat/completions"):
        return ["digigraph:chat"]
    if path in ("/v1/models",) or path.startswith("/v1/models/"):
        return ["digigraph:chat"]
    if path.startswith("/threads/") or path.startswith("/files/"):
        return ["digigraph:mcp"]
    if path.startswith("/v1/debug") or path == "/test_llm":
        return ["digigraph:workflow"]
    if method == "GET" and path == "/v1/debug/input_messages":
        return ["digigraph:workflow"]
    return ["digigraph:workflow"]


def digiquant_path_scopes(method: str, path: str) -> list[str] | None:
    if path in _PUBLIC_PATHS:
        return None
    if path == "/run_optimize":
        return ["digiquant:optimize"]
    if path in ("/run_pipeline", "/v1/workflow", "/v1/orchestrator_invoke"):
        return ["digiquant:backtest", "digiquant:optimize"]
    if path == "/v1/orchestrator_tools":
        return ["digiquant:backtest"]
    if path.startswith("/v1/jobs/"):
        return ["digiquant:backtest"]
    if path in ("/run_backtest", "/run_export", "/backtest/start") or path.startswith("/backtest/"):
        return ["digiquant:backtest"]
    return ["digiquant:backtest"]


def digisearch_path_scopes(method: str, path: str) -> list[str] | None:
    if path in _PUBLIC_PATHS:
        return None
    if path == "/ingest" or path.startswith("/ingest"):
        return ["digisearch:ingest"]
    if path in (
        "/query",
        "/v1/research_turn",
        "/v1/orchestrator_tools",
        "/v1/orchestrator_invoke",
    ) or path.startswith("/query"):
        return ["digisearch:query"]
    if path.startswith("/indexes"):
        return ["digisearch:query"]
    if path == "/azure_status":
        return ["digisearch:query"]
    return ["digisearch:query"]
