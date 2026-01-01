"""Bounded Supabase retry: transient faults retry 3×, real errors fail fast (#3299)."""

from __future__ import annotations

import time

import httpx
import pytest
from digiquant.supabase_retry import (
    MAX_ATTEMPTS,
    is_retryable_supabase_error,
    run_with_supabase_retry,
)

pytestmark = pytest.mark.unit


def _read_timeout() -> httpx.ReadTimeout:
    return httpx.ReadTimeout(
        "The read operation timed out",
        request=httpx.Request("GET", "https://x.supabase.co/rest/v1/t"),
    )


def test_retryable_markers_cover_daily_run_failures() -> None:
    assert is_retryable_supabase_error(_read_timeout())
    assert is_retryable_supabase_error(ConnectionError("disconnect: connection reset"))
    assert is_retryable_supabase_error(Exception("PGRST002: could not fetch"))
    assert is_retryable_supabase_error(Exception("502 Bad Gateway"))


def test_schema_errors_fail_fast_without_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    assert not is_retryable_supabase_error(
        ValueError('column "hist_vol_21" does not exist (42703)')
    )
    calls = 0

    def _boom() -> object:
        nonlocal calls
        calls += 1
        raise ValueError('column "hist_vol_21" does not exist (42703)')

    with pytest.raises(ValueError, match="42703"):
        run_with_supabase_retry(_boom, operation="test 42703")
    assert calls == 1
    assert sleeps == []


def test_transient_failure_retries_then_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    calls = 0

    def _flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _read_timeout()
        return "rows"

    assert run_with_supabase_retry(_flaky, operation="test flaky") == "rows"
    assert calls == 3
    assert len(sleeps) == 2


def test_persistent_transient_raises_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    calls = 0

    def _down() -> object:
        nonlocal calls
        calls += 1
        raise _read_timeout()

    with pytest.raises(httpx.ReadTimeout):
        run_with_supabase_retry(_down, operation="test down")
    assert calls == MAX_ATTEMPTS == 3
