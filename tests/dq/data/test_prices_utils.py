"""Unit tests for digiquant.data.prices._utils."""

from __future__ import annotations

import pytest

from digiquant.data.prices._utils import call_with_retry


@pytest.mark.unit
def test_call_with_retry_succeeds_on_first_attempt() -> None:
    calls = {"n": 0}

    def ok() -> int:
        calls["n"] += 1
        return 42

    assert call_with_retry(ok) == 42
    assert calls["n"] == 1


@pytest.mark.unit
def test_call_with_retry_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert call_with_retry(flaky, attempts=5, backoff_seconds=0) == "ok"
    assert calls["n"] == 3


@pytest.mark.unit
def test_call_with_retry_raises_after_exhausting_attempts() -> None:
    with pytest.raises(RuntimeError, match="still failing"):
        call_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("still failing")), attempts=2)
