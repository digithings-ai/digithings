"""Service-to-service digikey auth for headless callers (no user session)."""

from __future__ import annotations

import hashlib
import os
import threading
import time

import httpx

EXPIRY_SKEW_S = 60.0


class ServiceAuthError(RuntimeError):
    pass


_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def clear_service_jwt_cache() -> None:
    with _lock:
        _cache.clear()


def _http_post(url: str, payload: dict) -> dict:
    with httpx.Client(timeout=10.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


def get_service_jwt(
    *,
    key_env: str = "DIGIQUANT_DIGIKEY_API_KEY",
    digikey_url_env: str = "DIGIKEY_URL",
    scopes: tuple[str, ...] = ("digisearch:query",),
) -> str:
    raw = os.environ.get(key_env, "")
    base = os.environ.get(digikey_url_env, "").rstrip("/")
    if not raw:
        raise ServiceAuthError(f"{key_env} is not set")
    if not base:
        raise ServiceAuthError(f"{digikey_url_env} is not set")
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    cache_key = f"{key_env}:{key_hash}:{','.join(scopes)}"
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
        token = str(data["access_token"])
        ttl = float(data.get("expires_in", 900))
    except Exception as exc:
        raise ServiceAuthError(f"digikey exchange failed: {exc}") from exc
    if not token:
        raise ServiceAuthError("digikey exchange returned empty token")
    with _lock:
        _cache[cache_key] = (token, now + ttl)
    return token
