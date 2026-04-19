"""Shared CORS middleware installer for DigiThings FastAPI services.

Exposes :func:`install_cors` which reads an explicit allowlist from the
environment and applies Starlette's :class:`CORSMiddleware` with a fixed,
minimal method/header profile.

Precedence (first non-empty wins):

1. ``<SERVICE>_CORS_ORIGINS`` — per-service override (e.g. ``DIGIGRAPH_CORS_ORIGINS``).
2. ``DIGI_CORS_ORIGINS``      — global allowlist.
3. ``DIGI_ALLOWED_ORIGINS``   — legacy global allowlist (back-compat; deprecated).
4. ``[]``                     — empty (most restrictive). Deployments must set
   one of the above; without it, no browser origin is accepted.

Each origin may contain ``${VAR}`` / ``$VAR`` references expanded from the
current environment at call time, e.g. ``http://${API_HOST}:3000``.
"""

from __future__ import annotations

import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

__all__ = ["install_cors", "resolve_cors_origins"]

_VAR_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)")

_ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Request-ID"]
_MAX_AGE = 600


def _subst_env(s: str) -> str:
    """Expand ``${VAR}`` / ``$VAR`` patterns using the current environment."""
    return _VAR_PATTERN.sub(lambda m: os.environ.get(m.group(1) or m.group(2), ""), s)


def _parse(raw: str) -> list[str]:
    return [_subst_env(o.strip()) for o in raw.split(",") if o.strip()]


def resolve_cors_origins(service: str) -> list[str]:
    """Resolve the CORS allowlist for *service* using the documented precedence.

    Returns an empty list when no env var is set — the most restrictive default.
    """
    per_service = os.environ.get(f"{service.upper()}_CORS_ORIGINS", "").strip()
    if per_service:
        return _parse(per_service)
    global_new = os.environ.get("DIGI_CORS_ORIGINS", "").strip()
    if global_new:
        return _parse(global_new)
    legacy = os.environ.get("DIGI_ALLOWED_ORIGINS", "").strip()
    if legacy:
        return _parse(legacy)
    return []


def install_cors(app: FastAPI, service: str) -> None:
    """Install CORS middleware on *app* using the allowlist for *service*.

    The allowlist is resolved at call time via :func:`resolve_cors_origins`.
    ``allow_credentials=True`` is set because DigiChat forwards the DigiKey
    bearer cookie/session on cross-origin fetches; methods/headers are the
    minimum set used across the stack.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_cors_origins(service),
        allow_credentials=True,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
        max_age=_MAX_AGE,
    )
