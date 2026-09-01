"""Bounded PostgREST/httpx timeouts for Olympus I/O (#3319).

httpx timeouts on ``build_client`` plus a thread deadline around H9
``execute()`` so a hung call raises instead of sitting until the 240-minute
job cancel. Independent of ``transient.py`` retries (#3299).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 60.0
WRITE_TIMEOUT_SECONDS = 30.0
POOL_TIMEOUT_SECONDS = 10.0
# Connect + read, with a small slack so the httpx timeout can fire first.
EXECUTE_DEADLINE_SECONDS = CONNECT_TIMEOUT_SECONDS + READ_TIMEOUT_SECONDS


class PostgrestTimeoutError(TimeoutError):
    """Raised when a PostgREST call exceeds the Olympus deadline."""


def run_with_deadline(
    fn: Callable[[], T],
    *,
    seconds: float = EXECUTE_DEADLINE_SECONDS,
) -> T:
    """Run *fn* and raise :class:`PostgrestTimeoutError` if it exceeds *seconds*.

    The worker is a **daemon** thread so interpreter shutdown does not wait
    for a hung PostgREST call. ``ThreadPoolExecutor`` workers are non-daemon;
    ``shutdown(wait=False)`` returns to the caller but process exit still
    joins them — the 240-minute stall this module exists to prevent.
    Stdlib cannot kill the worker; abandoning it is the point.
    """
    if seconds <= 0:
        raise PostgrestTimeoutError(f"Olympus PostgREST call exceeded {seconds}s deadline")

    box: list[T] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            box.append(fn())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker, daemon=True, name="olympus-postgrest-deadline")
    thread.start()
    thread.join(timeout=seconds)
    if thread.is_alive():
        raise PostgrestTimeoutError(f"Olympus PostgREST call exceeded {seconds:.2f}s deadline")
    if errors:
        raise errors[0]
    return box[0]
