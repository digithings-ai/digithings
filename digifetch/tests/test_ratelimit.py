"""Tests for digifetch.ratelimit — min-interval gate with injected clock+sleep.

A fake monotonic clock and a recording sleep make the limiter fully
deterministic: we assert exactly how long each acquire would block.
"""

from __future__ import annotations

import pytest

from digifetch.ratelimit import RateLimiter

pytestmark = pytest.mark.unit


class _FakeClock:
    """Manually advanceable monotonic clock; sleeping advances it."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds  # a real sleep would advance wall-clock by this much


def test_first_acquire_never_waits() -> None:
    clock = _FakeClock()
    rl = RateLimiter(min_interval=2.0, clock=clock.now, sleep=clock.sleep)
    assert rl.acquire() == 0.0
    assert clock.slept == []


def test_second_acquire_waits_full_interval_when_immediate() -> None:
    clock = _FakeClock()
    rl = RateLimiter(min_interval=2.0, clock=clock.now, sleep=clock.sleep)
    rl.acquire()  # t=0, sets last
    waited = rl.acquire()  # no time passed → must wait the full 2.0
    assert waited == 2.0
    assert clock.slept == [2.0]


def test_partial_elapsed_waits_remainder() -> None:
    clock = _FakeClock()
    rl = RateLimiter(min_interval=2.0, clock=clock.now, sleep=clock.sleep)
    rl.acquire()  # t=0
    clock.t = 0.5  # 0.5s elapsed externally
    waited = rl.acquire()
    assert waited == pytest.approx(1.5)


def test_no_wait_when_interval_already_passed() -> None:
    clock = _FakeClock()
    rl = RateLimiter(min_interval=2.0, clock=clock.now, sleep=clock.sleep)
    rl.acquire()  # t=0
    clock.t = 5.0  # well past the interval
    assert rl.acquire() == 0.0
    assert clock.slept == []


def test_zero_interval_disables_throttle() -> None:
    clock = _FakeClock()
    rl = RateLimiter(min_interval=0.0, clock=clock.now, sleep=clock.sleep)
    assert rl.acquire() == 0.0
    assert rl.acquire() == 0.0
    assert clock.slept == []


def test_steady_cadence_does_not_drift() -> None:
    """Back-to-back acquires settle into a fixed min_interval cadence."""
    clock = _FakeClock()
    rl = RateLimiter(min_interval=1.0, clock=clock.now, sleep=clock.sleep)
    rl.acquire()  # t=0
    rl.acquire()  # waits 1.0 → t=1.0
    rl.acquire()  # waits 1.0 → t=2.0
    assert clock.slept == [1.0, 1.0]


def test_negative_interval_rejected() -> None:
    with pytest.raises(ValueError, match="min_interval"):
        RateLimiter(min_interval=-1.0)
