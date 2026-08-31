"""Retry transient Supabase/HTTP disconnects in Olympus data tools (#3299)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.2


def is_retryable_data_error(exc: BaseException) -> bool:
    """True for disconnect / PostgREST schema-cache / HTTP 502 failures."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 502:
        return True
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    return (
        "server disconnected" in lowered
        or "pgrst002" in lowered
        or "bad gateway" in lowered
        or "http 502" in lowered
        or "status code 502" in lowered
        or " 502" in text
        or text.rstrip().endswith("502")
    )


def call_with_disconnect_retry(
    fn: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> T:
    """Invoke *fn* up to *attempts* times on disconnect / PGRST002 / 502."""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if not is_retryable_data_error(exc) or attempt >= attempts:
                raise
            logger.info(
                "transient data error (attempt %d/%d): %s; retrying",
                attempt,
                attempts,
                exc,
            )
            time.sleep(backoff_seconds * attempt)
    assert last is not None
    raise last
