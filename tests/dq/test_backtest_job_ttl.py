"""REM-056: TTL prune for async backtest jobs."""

from __future__ import annotations

import time
from queue import Queue

import pytest

from digiquant import backtest_jobs
from digiquant.backtest_jobs import BACKTEST_JOB_TTL_SECS, prune_stale_backtest_jobs


@pytest.mark.unit
def test_prune_stale_backtest_jobs_removes_expired() -> None:
    backtest_jobs._backtest_jobs.clear()
    try:
        backtest_jobs._backtest_jobs["old"] = {
            "queue": Queue(),
            "result": None,
            "error": None,
            "done": True,
            "created_at": time.monotonic() - BACKTEST_JOB_TTL_SECS - 1,
        }
        backtest_jobs._backtest_jobs["fresh"] = {
            "queue": Queue(),
            "result": None,
            "error": None,
            "done": True,
            "created_at": time.monotonic(),
        }
        prune_stale_backtest_jobs()
        assert "old" not in backtest_jobs._backtest_jobs
        assert "fresh" in backtest_jobs._backtest_jobs
    finally:
        backtest_jobs._backtest_jobs.clear()
