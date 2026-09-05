"""Bounded retry for Supabase reads hit by transient network faults (#3299).

The Olympus daily run failed on ``httpx.ReadTimeout`` out of
``query_returns_window`` (#3078); cheap-model tool rounds also see PostgREST
``PGRST002`` and 502s. Retry those (and only those) 3× with short backoff;
everything else — including 42703 unknown-column — still fails fast so real
bugs stay loud. Callers keep their existing ``Error: …`` / ``{"error": …}``
contract: the retry helper only decides *whether to try again*, never how
failure is reported.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 3
# Short backoff between attempts 1→2 and 2→3. Tests monkeypatch time.sleep.
RETRY_BACKOFF_S: tuple[float, ...] = (0.2, 0.5)

# Matched against "ExcName: message" (case-insensitive). Tight on purpose:
# disconnects, PostgREST fetch failures, and bad-gateway classes only.
_RETRYABLE_MARKERS = (
    "disconnect",
    "pgrst002",
    "502",
    "503",
    "readtimeout",
    "connecttimeout",
    "connecterror",
    "timed out",
    "temporarily unavailable",
)


def is_retryable_supabase_error(exc: BaseException) -> bool:
    """True for transient transport/gateway faults worth one more attempt."""
    haystack = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in haystack for marker in _RETRYABLE_MARKERS)


def run_with_supabase_retry(
    fn: Callable[[], T],
    *,
    operation: str = "supabase read",
    attempts: int = MAX_ATTEMPTS,
) -> T:
    """Run ``fn`` up to ``attempts`` times, retrying transient faults only.

    Non-retryable exceptions propagate immediately. After the final attempt
    the last exception propagates — the caller reports it as before.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not is_retryable_supabase_error(exc) or attempt == attempts:
                raise
            backoff = RETRY_BACKOFF_S[min(attempt - 1, len(RETRY_BACKOFF_S) - 1)]
            logger.warning(
                "%s transient failure (attempt %d/%d: %s: %s); retrying in %.1fs",
                operation,
                attempt,
                attempts,
                type(exc).__name__,
                exc,
                backoff,
            )
            time.sleep(backoff)
    assert last_exc is not None  # attempts >= 1 always runs once
    raise last_exc


__all__ = [
    "MAX_ATTEMPTS",
    "RETRY_BACKOFF_S",
    "is_retryable_supabase_error",
    "run_with_supabase_retry",
]
