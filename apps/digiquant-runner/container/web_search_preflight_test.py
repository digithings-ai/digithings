"""Attempt-loop checks for web_search_preflight. Does not call digiquant."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import web_search_preflight  # noqa: E402


def test_succeeds_on_a_later_attempt() -> None:
    codes = iter((1, 1, 0))
    slept: list[float] = []
    code = web_search_preflight.run_preflight(
        lambda: next(codes),
        attempts=6,
        sleep=slept.append,
    )
    assert code == 0
    assert slept == [10, 10]


def test_exit_one_when_all_six_fail() -> None:
    slept: list[float] = []
    calls = {"n": 0}

    def healthcheck() -> int:
        calls["n"] += 1
        return 1

    code = web_search_preflight.run_preflight(healthcheck, attempts=6, sleep=slept.append)
    assert code == 1
    assert calls["n"] == 6
    assert slept == [10, 10, 10, 10, 10]


def main() -> int:
    test_succeeds_on_a_later_attempt()
    test_exit_one_when_all_six_fail()
    assert web_search_preflight.ATTEMPTS == 6
    assert web_search_preflight.SLEEP_SECONDS == 10
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
