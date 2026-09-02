"""Environment-backed configuration for edit-mode."""

from __future__ import annotations

from digiquant.olympus.envcompat import STALE_FULL_DAYS, env_lookup

OLYMPUS_STALE_FULL_DAYS_ENV = "OLYMPUS_STALE_FULL_DAYS"
_DEFAULT_STALE_FULL_DAYS = 7


def stale_full_days() -> int:
    """Return max prior gap (calendar days) before forcing ``full`` rewrite."""
    raw = env_lookup(STALE_FULL_DAYS).strip()
    if not raw:
        return _DEFAULT_STALE_FULL_DAYS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_STALE_FULL_DAYS
    return max(value, 1)
