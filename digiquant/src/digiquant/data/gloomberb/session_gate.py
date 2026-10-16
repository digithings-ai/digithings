"""Secret-gated advertisement of the Gloomberb session tools (#2752).

Chris, 10 Oct 2026: the Gloomberb session cookie belongs to whoever deploys
the digithings stack. It is that deployer's own secret, from their own
Gloomberb account, never digithings'. So digithings can only *hold* a cookie
briefly to check it — it cannot mint one, share one, or stand in for one.

This module is the single answer to "may the ``session`` / ``preview`` /
``pro`` tools be advertised?". It exists because the previous gate was
presence-only: any non-empty ``GLOOMBERB_SESSION_COOKIE`` advertised 41 tools
that could only return ``auth_required`` (#4099 was written when the tools
answered at call time; this issue moves the check to list time).

Three rules make it fail closed:

1. **No secret, no HTTP.** Without a cookie there is nothing to validate, so
   the gate costs zero network calls — the ``GLOOMBERB_ENABLED`` default-off
   path from #5245 is unchanged.
2. **One probe per TTL window.** The first list call with a fresh cookie
   performs exactly one bounded, single-attempt authenticated read
   (:meth:`GloomberbClient.check_session`); later calls inside the TTL reuse
   the verdict and make no request. This is a deliberate, documented relaxation
   of the zero-HTTP-at-list-time policy in #4099, and it costs one request per
   ``DEFAULT_CACHE_TTL_SECONDS`` and only when a secret is actually configured.
3. **Anything unproven is a no.** A disabled kill switch, a missing cookie, an
   HTTP 401, a 5xx, a transport fault or an exception all hide the tools. The
   gate can only fail towards "hidden", never towards "advertised".

The cache key is :func:`session_cache_fingerprint` — the existing sha256
discriminator — so the cookie is never hashed twice and never stored. Nothing
in this module logs, returns or prints the cookie value.

Reset semantics: a change to the cookie changes the fingerprint, so a new
secret invalidates the cache with no explicit purge.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from .client import (
    DEFAULT_CACHE_TTL_SECONDS,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
    gloomberb_enabled,
    session_cache_fingerprint,
)

__all__ = [
    "SessionGateStatus",
    "gated_tools_advertised",
    "reset_session_gate_cache",
    "session_gate_status",
]

_LOGGER = logging.getLogger(__name__)

# Human-facing remediation, quoted in the warning and printed by
# `digiquant gloomberb status`. It names the env var and the command, never a
# value.
_LOGIN_HINT = (
    "run `digiquant gloomberb login` and store the cookie in "
    f"{GLOOMBERB_SESSION_COOKIE_ENV} (Keychain or .env locally, "
    "`wrangler secret put GLOOMBERB_SESSION_COOKIE` on Cloudflare)"
)


@dataclass(frozen=True)
class SessionGateStatus:
    """Why the session tools are or are not advertised.

    ``authenticated`` is the only field a caller should branch on; the rest is
    for operators (``digiquant gloomberb status``) and for the warning text.
    """

    authenticated: bool
    code: str
    detail: str
    probed: bool = False


_lock = threading.Lock()
_cache: dict[str, tuple[float, SessionGateStatus]] = {}
_clock: Any = None


def _now() -> float:
    """Monotonic seconds. Indirected so tests can pin the TTL boundary."""
    if _clock is not None:
        return float(_clock())
    import time

    return time.monotonic()


def reset_session_gate_cache() -> None:
    """Drop every cached verdict. Test and CLI-login seam, never automatic."""
    with _lock:
        _cache.clear()


def _read_cookie() -> str:
    """The configured cookie, or "" when unset. Never logged, never returned."""
    return (os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV) or "").strip()


def _probe() -> SessionGateStatus:
    """Run one bounded authenticated read and classify it. Never raises."""
    try:
        with GloomberbClient() as client:
            verdict = client.check_session()
    except Exception as exc:  # fail closed — see module rule 3
        _LOGGER.warning(
            "Gloomberb session validation could not complete (%s); the session "
            "tools stay hidden. To authenticate: %s",
            type(exc).__name__,
            _LOGIN_HINT,
        )
        return SessionGateStatus(False, "probe_failed", type(exc).__name__, probed=True)
    status = SessionGateStatus(verdict.valid, verdict.code, verdict.detail, probed=True)
    if not verdict.valid:
        _LOGGER.warning(
            "Gloomberb session cookie rejected (%s: %s); the session tools stay "
            "hidden. To authenticate: %s",
            verdict.code,
            verdict.detail,
            _LOGIN_HINT,
        )
    return status


def session_gate_status(cookie: str | None = None) -> SessionGateStatus:
    """Return the gate verdict, validating at most once per TTL window.

    Pass ``cookie`` to validate a specific value (that is how
    ``digiquant gloomberb login`` checks a freshly pasted cookie before it is
    stored). The cache key is the sha256 fingerprint, so passing a different
    cookie never returns another cookie's verdict.
    """
    if not gloomberb_enabled():
        return SessionGateStatus(
            False, "disabled", "GLOOMBERB_ENABLED is not set; the whole family is off"
        )
    raw = _read_cookie() if cookie is None else cookie.strip()
    if not raw:
        return SessionGateStatus(
            False,
            "no_secret",
            f"{GLOOMBERB_SESSION_COOKIE_ENV} is not set, so there is nothing to validate",
        )

    key = session_cache_fingerprint(raw)
    now = _now()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and (now - hit[0]) < DEFAULT_CACHE_TTL_SECONDS:
            return hit[1]

    status = _probe() if cookie is None else _probe_specific(raw)
    with _lock:
        _cache[key] = (now, status)
    return status


def _probe_specific(raw: str) -> SessionGateStatus:
    """Validate a candidate cookie that is not (yet) the environment's."""
    try:
        with GloomberbClient(session_cookie=raw) as client:
            verdict = client.check_session()
    except Exception as exc:
        return SessionGateStatus(False, "probe_failed", type(exc).__name__, probed=True)
    return SessionGateStatus(verdict.valid, verdict.code, verdict.detail, probed=True)


def gated_tools_advertised() -> bool:
    """True only when a live, validated deployer session exists."""
    return session_gate_status().authenticated
