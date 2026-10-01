"""Attempt-loop checks for wake_stack. Does not open a socket."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wake_stack  # noqa: E402


def test_wake_retries_then_succeeds() -> None:
    seen: dict[str, int] = {}

    def opener(url: str, timeout: float) -> int:
        assert timeout == wake_stack.TIMEOUT_SECONDS
        seen[url] = seen.get(url, 0) + 1
        return 200 if seen[url] >= 2 else 503

    slept: list[float] = []
    result = wake_stack.wake(attempts=4, opener=opener, sleep=slept.append)
    assert result == {url: True for url in wake_stack.URLS}
    assert slept == [wake_stack.SLEEP_SECONDS]


def test_wake_stays_down_and_does_not_sleep_after_last() -> None:
    slept: list[float] = []
    result = wake_stack.wake(
        attempts=3,
        opener=lambda _url, _timeout: 0,
        sleep=slept.append,
    )
    assert result == {url: False for url in wake_stack.URLS}
    assert slept == [wake_stack.SLEEP_SECONDS, wake_stack.SLEEP_SECONDS]


def test_format_names_both_health_checks() -> None:
    line = wake_stack.format_wake({url: True for url in wake_stack.URLS})
    assert line == (
        "wake key.digithings.ai/healthz=true search.digithings.ai/healthz=true"
    )


def test_main_exits_zero_without_network(monkeypatch: object | None = None) -> None:
    del monkeypatch

    def _fake() -> dict[str, bool]:
        return {url: True for url in wake_stack.URLS}

    previous = wake_stack.wake
    wake_stack.wake = _fake  # type: ignore[assignment]
    try:
        assert wake_stack.main() == 0
    finally:
        wake_stack.wake = previous


def main() -> int:
    test_wake_retries_then_succeeds()
    test_wake_stays_down_and_does_not_sleep_after_last()
    test_format_names_both_health_checks()
    test_main_exits_zero_without_network()
    assert wake_stack.ATTEMPTS == 12
    assert wake_stack.TIMEOUT_SECONDS == 10
    assert wake_stack.SLEEP_SECONDS == 5
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
