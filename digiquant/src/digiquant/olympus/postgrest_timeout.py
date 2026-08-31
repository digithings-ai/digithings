"""Bounded PostgREST/httpx timeouts for Olympus I/O (#3319).

Monday run 33395925331 booked positions then stalled inside
``append_commit_chain``'s ``price_history`` read until GitHub cancelled the
job at 240 minutes. This module:

- documents the per-request bound (60s read / 10s connect — stricter than
  supabase-py's 120s library default);
- wraps ``execute()`` with a hard thread deadline so H9 fails in minutes
  even if the injected client has no httpx timeout;
- raises (never swallows) so the outer pipeline retry can fire.

Independent of ``transient.py`` disconnect retries (#3299).
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
