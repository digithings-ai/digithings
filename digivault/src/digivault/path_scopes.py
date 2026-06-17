"""DigiKey scope policy for DigiVault routes.

Defined here (not in ``digikey``) so the auth plane stays untouched — the
middleware accepts any ``(method, path) -> scopes | None`` function. Reads need
``digivault:read``; mutations need ``digivault:write``.
"""

from __future__ import annotations

SCOPE_READ = "digivault:read"
SCOPE_WRITE = "digivault:write"

_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/status",
    }
)


def digivault_path_scopes(method: str, path: str) -> list[str] | None:
    """Return required scopes for a request, or None if the route is auth-exempt."""
    if path in _PUBLIC_PATHS:
        return None
    # Discovery is a read; the hub fetches the tool manifest before invoking.
    if path == "/v1/orchestrator_tools":
        return [SCOPE_READ]
    # Invocation and all mutating note routes require write — invoke can create.
    if path == "/v1/orchestrator_invoke":
        return [SCOPE_WRITE]
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return [SCOPE_WRITE]
    return [SCOPE_READ]
