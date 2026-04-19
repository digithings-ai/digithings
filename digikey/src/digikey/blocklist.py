"""Redis-backed jti blocklist for JWT revocation (ADR-0007).

Thin wrapper over redis-py. Keys are named ``jti:<uuid>`` and written with
per-entry TTL equal to the token's remaining lifetime so Redis self-cleans.

Configuration: ``DIGIKEY_BLOCKLIST_REDIS_URL``. When unset, ``is_blocked()``
returns ``False`` (feature-flag fallback) and ``write_blocklist_bulk()`` is a
no-op. This lets deployments without Redis keep the existing behavior.

On a Redis connection/communication failure in ``is_blocked()``, this module
re-raises ``BlocklistUnavailable``; ``DigiAuthMiddleware`` converts that to an
HTTP 503 (fail-closed, per ADR-0007).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_KEY_PREFIX = "jti:"

_client_cache: tuple[str, object] | None = None


class BlocklistUnavailable(RuntimeError):
    """Raised when the Redis blocklist backend is configured but unreachable."""


def _redis_url() -> str:
    return (os.environ.get("DIGIKEY_BLOCKLIST_REDIS_URL") or "").strip()


def is_configured() -> bool:
    return bool(_redis_url())


def _get_client():
    """Return a cached redis client for the current URL, or None if unset."""
    global _client_cache
    url = _redis_url()
    if not url:
        _client_cache = None
        return None
    if _client_cache is not None and _client_cache[0] == url:
        return _client_cache[1]
    try:
        import redis  # local import so digikey loads without redis installed
    except ImportError as e:  # pragma: no cover - redis is a declared dep
        raise BlocklistUnavailable(f"redis package not installed: {e}") from e
    client = redis.Redis.from_url(url, decode_responses=True)
    _client_cache = (url, client)
    return client


def reset_client_cache() -> None:
    """Test helper — drop the memoized client so env changes take effect."""
    global _client_cache
    _client_cache = None


def write_blocklist_bulk(entries: list[tuple[str, int]]) -> int:
    """Push ``(jti, ttl_sec)`` entries to Redis in a single pipeline.

    Entries with ``ttl_sec <= 0`` are skipped (the token is already expired).
    Returns the number of entries actually written. No-op if Redis unconfigured.
    """
    if not entries:
        return 0
    client = _get_client()
    if client is None:
        return 0
    import redis as _redis

    pipe = client.pipeline(transaction=False)
    written = 0
    for jti, ttl in entries:
        if ttl <= 0:
            continue
        pipe.setex(_KEY_PREFIX + jti, ttl, "1")
        written += 1
    if written == 0:
        return 0
    try:
        pipe.execute()
    except _redis.RedisError as e:
        raise BlocklistUnavailable(f"redis pipeline failed: {e}") from e
    return written


def is_blocked(jti: str) -> bool:
    """Return True if this jti is in the blocklist.

    Raises :class:`BlocklistUnavailable` if the Redis URL is configured but the
    backend is unreachable. Returns ``False`` when the URL is unset.
    """
    if not jti:
        return False
    client = _get_client()
    if client is None:
        return False
    import redis as _redis

    try:
        return bool(client.exists(_KEY_PREFIX + jti))
    except _redis.RedisError as e:
        raise BlocklistUnavailable(f"redis exists failed: {e}") from e
