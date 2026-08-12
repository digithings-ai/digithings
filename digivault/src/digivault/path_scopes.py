"""digikey scope policy for digivault routes.

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
    # Invocation is gated at read here — most orchestrator tools are reads
    # (search, backlinks, lint). The one mutating tool (create_note) enforces
    # SCOPE_WRITE itself in the handler, keyed on the requested tool name, so a
    # read-only caller can't reach it via this shared endpoint.
    if path == "/v1/orchestrator_invoke":
        return [SCOPE_READ]
    # By-path note fetch is POST (the request body carries vault_path/path_prefix) but
    # is a pure read — scope it like the GET routes, not like a mutation. path_prefix
    # is still an enforced boundary; the handler returns 403 for an out-of-scope path.
    if path == "/v1/notes/by-path":
        return [SCOPE_READ]
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return [SCOPE_WRITE]
    return [SCOPE_READ]
