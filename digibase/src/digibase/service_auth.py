"""Service-to-service digikey auth for headless callers (no user session).

Exchanges a long-lived service API key (read from an environment variable) for a
short-lived digikey JWT via ``POST {digikey_url}/v1/oauth/token``. Tokens are
cached in a **module-global** dict keyed by the key env var, a SHA-256 of the raw
key, the digikey base URL, and a canonical JSON encoding of the requested scopes,
so repeated calls in the same process reuse a token until it is within
:data:`EXPIRY_SKEW_S` of expiry. The cache is process-local, shared across
threads, and never persisted; call :func:`clear_service_jwt_cache` in tests or
after rotating credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any  # score:allow untyped any

from digibase.http_client import sync_client

EXPIRY_SKEW_S = 60.0


class ServiceAuthError(RuntimeError):
    """Raised when a service JWT cannot be obtained from digikey.

    Covers missing key/URL configuration, transport failures, malformed
    responses, and empty or non-string access tokens.
    """


_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def clear_service_jwt_cache() -> None:
    """Drop every cached service JWT in this process.

    The cache is a module global shared across threads; this clears it under the
    module lock. Intended for tests and credential rotation, not request paths.
    """
    with _lock:
        _cache.clear()


def _http_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST ``payload`` as JSON to ``url`` and return the decoded JSON body.

    Performs blocking network I/O through the bounded-timeout
    :func:`digibase.http_client.sync_client` factory, so a slow digikey can never
    hang the caller indefinitely. Raises ``httpx.HTTPError`` on a non-2xx
    response or transport error; callers wrap it in :class:`ServiceAuthError`.
    """
    with sync_client() as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


def get_service_jwt(
    *,
    key_env: str = "DIGIQUANT_DIGIKEY_API_KEY",
    digikey_url_env: str = "DIGIKEY_URL",
    scopes: tuple[str, ...] = ("digisearch:query",),
) -> str:
    """Return a cached or freshly exchanged digikey service JWT.

    Reads the raw API key from ``key_env`` and the digikey base URL from
    ``digikey_url_env``; raises :class:`ServiceAuthError` if either is unset. On a
    cache miss this performs a network token exchange and stores the result in
    the module-global cache until ``expires_in`` minus :data:`EXPIRY_SKEW_S`. The
    cache key includes the env var name, a SHA-256 of the raw key, the base URL,
    and a canonical JSON encoding of ``scopes`` so distinct keys, hosts, or scope
    sets never share an entry. A response whose ``access_token`` is missing,
    null, or not a non-empty string is rejected rather than coerced.
    """
    raw = os.environ.get(key_env, "")
    base = os.environ.get(digikey_url_env, "").rstrip("/")
    if not raw:
        raise ServiceAuthError(f"{key_env} is not set")
    if not base:
        raise ServiceAuthError(f"{digikey_url_env} is not set")
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    scopes_key = json.dumps(list(scopes), separators=(",", ":"))
    cache_key = f"{key_env}:{base}:{key_hash}:{scopes_key}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cache_key)
        if hit is not None and hit[1] - EXPIRY_SKEW_S > now:
            return hit[0]
    try:
        data = _http_post(
            f"{base}/v1/oauth/token",
            {"grant_type": "api_key", "api_key": raw, "requested_scopes": list(scopes)},
        )
        raw_token = data.get("access_token")
        if not isinstance(raw_token, str) or not raw_token:
            raise ServiceAuthError("digikey exchange returned empty token")
        token = raw_token
        ttl = float(data.get("expires_in", 900))
    except ServiceAuthError:
        raise
    except Exception as exc:
        raise ServiceAuthError(f"digikey exchange failed: {exc}") from exc
    with _lock:
        _cache[cache_key] = (token, now + ttl)
    return token
