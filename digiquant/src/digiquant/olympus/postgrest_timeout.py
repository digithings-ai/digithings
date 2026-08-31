"""Bounded PostgREST/httpx timeouts for Olympus I/O (#3319).

httpx timeouts on ``build_client`` plus a thread deadline around H9
``execute()`` so a hung call raises instead of sitting until the 240-minute
job cancel. Independent of ``transient.py`` retries (#3299).
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
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

    The worker thread is not killed (stdlib has no portable cancel); the caller
    fails fast so the job can retry or exit instead of sitting until CI cancel.
    """
    if seconds <= 0:
        raise PostgrestTimeoutError(f"Olympus PostgREST call exceeded {seconds}s deadline")
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        return future.result(timeout=seconds)
    except FuturesTimeout as exc:
        raise PostgrestTimeoutError(
            f"Olympus PostgREST call exceeded {seconds:.2f}s deadline"
        ) from exc
    finally:
        # Do not wait for a hung worker — that would reintroduce the 240m stall.
        pool.shutdown(wait=False, cancel_futures=True)
