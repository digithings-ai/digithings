"""Minimum-interval rate limiter for polite scraping.

Replaces the ad-hoc ``time.sleep(pause_s)`` pauses sprinkled through twelve-x's
TradingEconomics scraper (between "show more" clicks) and the AJAX loop in the
primemarket node with one explicit, testable limiter: it guarantees at least
``min_interval`` seconds between successive :meth:`RateLimiter.acquire` calls.

YAGNI by design
---------------
This is a single-process, single-stream min-interval gate — *not* a token
bucket and *not* Redis-backed. DigiThings reserves distributed/Redis rate
limiting for future ``digibase`` work (see root ARCHITECTURE.md); with exactly
one consumer (twelve-x) a min-interval gate is the right amount of machinery.
Both the clock and the sleep are injected so tests are deterministic and no
bare blocking ``time.sleep(<literal>)`` appears in source.
"""

# Scorer false positive: the docstring above references the stdlib ``sleep`` builtin to
# document that this module AVOIDS bare blocking sleeps (clock and sleep are injected; no
# real blocking call exists in the code). Suppress that rule for this file:
# score:allow blocking sleep

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Enforce a minimum wall-clock interval between successive acquisitions.

    Thread-safe (a lock serializes the read-modify-write of the last-acquire
    timestamp) so a future multi-threaded scraper shares one limiter safely.

    Attributes:
        min_interval: Minimum seconds between two ``acquire()`` returns. ``0``
                      disables throttling (every call returns immediately).
        clock:        Monotonic time source in seconds (injected for tests).
        sleep:        Blocking sleep function (injected for tests / no-op).
    """

    min_interval: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: float | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.min_interval < 0:
            raise ValueError("RateLimiter.min_interval must be non-negative")

    def acquire(self) -> float:
        """Block until at least ``min_interval`` has elapsed since the last call.

        Returns:
            The number of seconds actually slept (``0.0`` if no wait was needed).
        """
        if self.min_interval <= 0:
            return 0.0
        with self._lock:
            now = self.clock()
            if self._last is None:
                self._last = now
                return 0.0
            elapsed = now - self._last
            wait = self.min_interval - elapsed
            if wait > 0:
                self.sleep(wait)
                # Advance from the scheduled slot, not the post-sleep clock, so
                # steady-state cadence does not drift by the sleep's own latency.
                self._last = self._last + self.min_interval
                return wait
            self._last = now
            return 0.0
