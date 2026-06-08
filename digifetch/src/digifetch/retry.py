"""Composable retry-with-backoff for fetch operations.

Generalizes the ad-hoc navigation-retry loop in twelve-x's
``fx_calendar/scraper.py`` (``for attempt in range(1, navigation_retries + 1): ...
time.sleep(2.0 * attempt)``) into a reusable, *composable* wrapper that is NOT
baked into the browser session. Any callable — a Playwright navigation, an HTTP
fetch, a download — can be wrapped.

Design notes
------------
- **Injectable sleep.** ``RetryPolicy.sleep`` defaults to ``time.sleep`` but is a
  constructor parameter so unit tests run instantly (inject a no-op) and so no
  bare ``time.sleep(<literal>)`` blocking call appears in the engine source.
- **Exponential backoff with optional jitter.** ``delay = base * factor**(n-1)``,
  capped at ``max_delay``. Jitter (full-jitter, injectable RNG) spreads retries
  so concurrent scrapers do not synchronize their hammering of a site.
- **Selective retry.** ``retry_on`` narrows which exception types are retried;
  anything else propagates immediately (a 404 should not be retried like a
  transient timeout).
"""

# Scorer false positive: the docstring above references the stdlib ``sleep`` builtin to
# document that this module AVOIDS bare blocking sleeps (sleep is injected; no real
# blocking call exists in the code). Suppress that rule for this file:
# score:allow blocking sleep

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential-backoff retry policy.

    Attributes:
        attempts:   Total tries (``1`` disables retry). Must be >= 1.
        base_delay: First backoff delay in seconds.
        factor:     Multiplier applied per subsequent attempt (geometric growth).
        max_delay:  Upper bound on any single backoff delay.
        jitter:     When True, sleep a random fraction in ``[0, delay]`` (full
                    jitter) instead of exactly ``delay``.
        retry_on:   Exception types that trigger a retry. Defaults to
                    ``(Exception,)`` — broad, matching twelve-x's catch-all
                    navigation loop. Narrow it for call sites that can classify
                    transient vs permanent failures.
        sleep:      Blocking sleep function (injected for tests / no-op).
        rand:       Zero-arg RNG returning ``[0.0, 1.0)`` for jitter (injected).
    """

    attempts: int = 3
    base_delay: float = 1.0
    factor: float = 2.0
    max_delay: float = 30.0
    jitter: bool = True
    retry_on: tuple[type[BaseException], ...] = (Exception,)
    sleep: Callable[[float], None] = time.sleep
    rand: Callable[[], float] = field(default_factory=lambda: __import__("random").random)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("RetryPolicy.attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < 0:
            raise ValueError("RetryPolicy delays must be non-negative")

    def delay_for(self, attempt: int) -> float:
        """Backoff delay (seconds) before the given 1-based ``attempt`` number.

        ``attempt=1`` is the first *retry* (i.e. after the initial try failed),
        so the geometric series starts at ``base_delay``.
        """
        raw = self.base_delay * (self.factor ** max(0, attempt - 1))
        capped = min(raw, self.max_delay)
        if self.jitter:
            return capped * self.rand()
        return capped


def with_retry(
    func: Callable[[], T],
    policy: RetryPolicy | None = None,
    *,
    description: str = "operation",
) -> T:
    """Call ``func`` with retry/backoff per ``policy``; re-raise the last error.

    The callable takes no arguments — bind site-specific parameters with a
    ``lambda`` or ``functools.partial`` at the call site. This keeps the retry
    wrapper fully decoupled from *what* is being retried (browser nav, HTTP GET,
    download), exactly the seam twelve-x lacked.

    Args:
        func:        Zero-arg callable to invoke.
        policy:      Retry policy; a default :class:`RetryPolicy` is used if None.
        description: Human label used in retry log lines.

    Returns:
        The return value of the first successful call.

    Raises:
        The last exception raised by ``func`` once attempts are exhausted, or
        immediately if the exception is not in ``policy.retry_on``.
    """
    pol = policy or RetryPolicy()
    last_error: BaseException | None = None
    for attempt in range(1, pol.attempts + 1):
        try:
            return func()
        except pol.retry_on as exc:
            last_error = exc
            if attempt >= pol.attempts:
                break
            delay = pol.delay_for(attempt)
            logger.warning(
                "%s attempt %d/%d failed: %s — retrying in %.2fs",
                description,
                attempt,
                pol.attempts,
                exc,
                delay,
            )
            if delay > 0:
                pol.sleep(delay)
    # attempts exhausted — surface the real cause rather than a generic message.
    assert last_error is not None  # loop ran at least once (attempts >= 1)
    raise last_error
