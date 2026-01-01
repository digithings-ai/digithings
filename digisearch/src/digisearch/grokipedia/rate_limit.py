"""Polite limiter: min-interval gate plus a simple token bucket.

Injectable ``clock`` / ``sleep`` so unit tests stay deterministic. Not
distributed — one process, one consumer (this spike).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class PoliteLimiter:
    """Wait for both a min spacing and a token-bucket slot.

    ``min_interval`` is the floor between successive ``acquire()`` returns
    (default 300ms). The bucket (default capacity 2, refill 2/s) caps short
    bursts so a retry loop cannot slam grokipedia.com.
    """

    min_interval: float = 0.3
    capacity: float = 2.0
    refill_per_s: float = 2.0
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: float | None = field(default=None, init=False, repr=False)
    _tokens: float = field(init=False, repr=False)
    _updated: float = field(init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.min_interval < 0:
            raise ValueError("PoliteLimiter.min_interval must be non-negative")
        if self.capacity <= 0:
            raise ValueError("PoliteLimiter.capacity must be positive")
        if self.refill_per_s < 0:
            raise ValueError("PoliteLimiter.refill_per_s must be non-negative")
        now = self.clock()
        self._tokens = self.capacity
        self._updated = now

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_s)
        self._updated = now

    def acquire(self) -> float:
        """Block until a token and the min interval are available.

        Returns the seconds actually slept (0.0 if no wait).
        """
        slept = 0.0
        with self._lock:
            now = self.clock()
            self._refill(now)
            if self._tokens < 1.0 and self.refill_per_s > 0:
                need = (1.0 - self._tokens) / self.refill_per_s
                if need > 0:
                    self.sleep(need)
                    slept += need
                    now = self.clock()
                    self._refill(now)
            self._tokens = max(0.0, self._tokens - 1.0)

            if self.min_interval > 0 and self._last is not None:
                elapsed = now - self._last
                wait = self.min_interval - elapsed
                if wait > 0:
                    self.sleep(wait)
                    slept += wait
                    now = self._last + self.min_interval
            self._last = now
        return slept
