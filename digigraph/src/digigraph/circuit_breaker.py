"""Lightweight circuit breaker for downstream HTTP services.

States: CLOSED (normal) → OPEN (failing fast) → HALF_OPEN (probe).

Usage::

    _cb = CircuitBreaker("digisearch", failure_threshold=5, recovery_timeout=30.0)

    def call_downstream():
        with _cb:
            return httpx_client.post(...)

If *failure_threshold* consecutive failures occur the breaker opens and raises
``CircuitBreakerOpen`` for *recovery_timeout* seconds before allowing a single
probe request through.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when a circuit is open and requests are being rejected."""


class CircuitBreaker:
    """Thread-safe circuit breaker."""

    _CLOSED = "CLOSED"
    _OPEN = "OPEN"
    _HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self._CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Context manager interface
    # ------------------------------------------------------------------

    def __enter__(self) -> "CircuitBreaker":
        with self._lock:
            if self._state == self._OPEN:
                if time.monotonic() - (self._opened_at or 0) >= self.recovery_timeout:
                    logger.info("CircuitBreaker[%s] → HALF_OPEN (probing)", self.name)
                    self._state = self._HALF_OPEN
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit '{self.name}' is open; downstream unavailable."
                    )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        with self._lock:
            if (
                exc_type is not None
                and issubclass(exc_type, Exception)
                and not issubclass(exc_type, CircuitBreakerOpen)
            ):
                self._failures += 1
                if self._state == self._HALF_OPEN or self._failures >= self.failure_threshold:
                    self._state = self._OPEN
                    self._opened_at = time.monotonic()
                    logger.warning(
                        "CircuitBreaker[%s] → OPEN after %d failure(s)", self.name, self._failures
                    )
            else:
                # success
                if self._state == self._HALF_OPEN:
                    logger.info("CircuitBreaker[%s] → CLOSED (probe succeeded)", self.name)
                self._state = self._CLOSED
                self._failures = 0
                self._opened_at = None
        return False  # do not suppress the exception

    # ------------------------------------------------------------------
    # Callable interface (wraps a zero-arg callable)
    # ------------------------------------------------------------------

    def call(self, fn, *args, **kwargs):
        """Execute *fn* guarded by this circuit breaker."""
        with self:
            return fn(*args, **kwargs)

    @property
    def state(self) -> str:
        return self._state
