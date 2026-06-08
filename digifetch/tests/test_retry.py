"""Tests for digifetch.retry — backoff, selective retry, injected sleep.

Sleep and RNG are injected so tests run instantly and assert the exact backoff
schedule (no real waiting, no wall-clock flakiness).
"""

from __future__ import annotations

import pytest

from digifetch.retry import RetryPolicy, with_retry

pytestmark = pytest.mark.unit


class _Boom(RuntimeError):
    pass


class _Other(ValueError):
    pass


def _recorder() -> tuple[list[float], object]:
    slept: list[float] = []
    return slept, slept.append


def test_succeeds_first_try_no_sleep() -> None:
    slept, sleep = _recorder()
    policy = RetryPolicy(attempts=3, sleep=sleep)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        return "ok"

    assert with_retry(fn, policy) == "ok"
    assert calls["n"] == 1
    assert slept == []  # no retry → no sleep


def test_invalid_policy_rejected() -> None:
    # factor must be non-negative — a negative factor yields negative delays and
    # tight-loop retries (regression guard for the Copilot review finding).
    with pytest.raises(ValueError, match="factor must be non-negative"):
        RetryPolicy(factor=-1.0)
    with pytest.raises(ValueError, match="attempts must be >= 1"):
        RetryPolicy(attempts=0)
    with pytest.raises(ValueError, match="delays must be non-negative"):
        RetryPolicy(base_delay=-1.0)


def test_retries_then_succeeds() -> None:
    slept, sleep = _recorder()
    # jitter off + factor 2 + base 1 → deterministic delays 1.0 then 2.0
    policy = RetryPolicy(attempts=4, base_delay=1.0, factor=2.0, jitter=False, sleep=sleep)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Boom("transient")
        return "recovered"

    assert with_retry(fn, policy) == "recovered"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0]  # backoff before attempts 2 and 3


def test_exhausts_and_reraises_last_error() -> None:
    slept, sleep = _recorder()
    policy = RetryPolicy(attempts=3, base_delay=0.5, jitter=False, sleep=sleep)

    def fn() -> None:
        raise _Boom("still failing")

    with pytest.raises(_Boom, match="still failing"):
        with_retry(fn, policy)
    # 3 attempts → 2 backoff sleeps (none after the final attempt).
    assert len(slept) == 2


def test_non_retryable_exception_propagates_immediately() -> None:
    slept, sleep = _recorder()
    policy = RetryPolicy(attempts=5, retry_on=(_Boom,), jitter=False, sleep=sleep)
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1
        raise _Other("permanent")

    with pytest.raises(_Other, match="permanent"):
        with_retry(fn, policy)
    assert calls["n"] == 1  # not retried
    assert slept == []


def test_delay_capped_at_max_delay() -> None:
    policy = RetryPolicy(base_delay=10.0, factor=10.0, max_delay=25.0, jitter=False)
    assert policy.delay_for(1) == 10.0
    assert policy.delay_for(2) == 25.0  # 100 capped to 25
    assert policy.delay_for(5) == 25.0


def test_full_jitter_scales_capped_delay() -> None:
    # Injected RNG returns 0.5 → delay should be half the capped value.
    policy = RetryPolicy(base_delay=8.0, factor=1.0, jitter=True, rand=lambda: 0.5)
    assert policy.delay_for(1) == 4.0


def test_invalid_attempts_rejected() -> None:
    with pytest.raises(ValueError, match="attempts"):
        RetryPolicy(attempts=0)
