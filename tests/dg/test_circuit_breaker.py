"""Unit tests for digigraph.circuit_breaker — the shared CLOSED→OPEN→HALF_OPEN state machine.

Hub tests (test_vertical_orchestrator_circuit_breaker.py) prove the *scoping* of what
counts as a failure. These pin the breaker itself: threshold open, fail-fast while
open, half-open probe after recovery_timeout, success closing the circuit, and that
CircuitBreakerOpen raised by the breaker is never counted as another failure.
"""

from __future__ import annotations

import pytest
from digigraph.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

pytestmark = pytest.mark.unit


def test_stays_closed_below_failure_threshold() -> None:
    cb = CircuitBreaker("t", failure_threshold=3, recovery_timeout=30.0)
    for _ in range(2):
        with pytest.raises(RuntimeError), cb:
            raise RuntimeError("boom")
    assert cb.state == "CLOSED"
    with cb:
        pass
    assert cb.state == "CLOSED"
    assert cb._failures == 0


def test_opens_after_threshold_and_fails_fast() -> None:
    cb = CircuitBreaker("t", failure_threshold=2, recovery_timeout=60.0)
    for _ in range(2):
        with pytest.raises(ValueError), cb:
            raise ValueError("down")
    assert cb.state == "OPEN"
    with pytest.raises(CircuitBreakerOpen, match="Circuit 't' is open"):
        with cb:
            pass


def test_half_open_probe_success_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """After recovery_timeout, one successful probe must return the breaker to CLOSED."""
    clock = {"now": 1000.0}
    monkeypatch.setattr("digigraph.circuit_breaker.time.monotonic", lambda: clock["now"])

    cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=10.0)
    with pytest.raises(RuntimeError), cb:
        raise RuntimeError("trip")
    assert cb.state == "OPEN"

    clock["now"] = 1009.0  # still inside the open window
    with pytest.raises(CircuitBreakerOpen):
        with cb:
            pass

    clock["now"] = 1010.0  # recovery elapsed → HALF_OPEN, then success → CLOSED
    with cb:
        pass
    assert cb.state == "CLOSED"
    assert cb._failures == 0


def test_half_open_probe_failure_reopens(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed probe must reopen immediately — never leave traffic flowing while broken."""
    clock = {"now": 0.0}
    monkeypatch.setattr("digigraph.circuit_breaker.time.monotonic", lambda: clock["now"])

    cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=5.0)
    with pytest.raises(RuntimeError), cb:
        raise RuntimeError("trip")
    assert cb.state == "OPEN"

    clock["now"] = 5.0
    with pytest.raises(RuntimeError), cb:
        raise RuntimeError("probe still dead")
    assert cb.state == "OPEN"

    # Still open until the *new* recovery window ends.
    with pytest.raises(CircuitBreakerOpen):
        with cb:
            pass


def test_circuit_breaker_open_is_not_counted_as_failure() -> None:
    """Fail-fast CircuitBreakerOpen must not inflate the failure counter / re-trip logic."""
    cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60.0)
    with pytest.raises(RuntimeError), cb:
        raise RuntimeError("trip")
    assert cb.state == "OPEN"
    failures_after_trip = cb._failures

    with pytest.raises(CircuitBreakerOpen), cb:
        pass
    assert cb._failures == failures_after_trip
    assert cb.state == "OPEN"


def test_call_wraps_zero_arg_callable() -> None:
    cb = CircuitBreaker("t", failure_threshold=5, recovery_timeout=30.0)
    assert cb.call(lambda: 42) == 42
    with pytest.raises(ZeroDivisionError):
        cb.call(lambda: 1 / 0)
