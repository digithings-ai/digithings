"""In-process async backtest job table with TTL pruning (REM-056)."""

from __future__ import annotations

import time
from queue import Queue
from typing import Any  # noqa: ANN401 — job record JSON blobs

_backtest_jobs: dict[str, dict[str, Any]] = {}
BACKTEST_JOB_TTL_SECS = 300


def prune_stale_backtest_jobs() -> None:
    """Drop jobs older than :data:`BACKTEST_JOB_TTL_SECS`."""
    now = time.monotonic()
    stale = [
        job_id
        for job_id, job in _backtest_jobs.items()
        if now - float(job.get("created_at", now)) > BACKTEST_JOB_TTL_SECS
    ]
    for job_id in stale:
        _backtest_jobs.pop(job_id, None)


def create_backtest_job() -> tuple[str, dict[str, Any]]:
    """Register a new job and return ``(job_id, job_record)``."""
    import uuid

    prune_stale_backtest_jobs()
    job_id = uuid.uuid4().hex
    record = {
        "queue": Queue(),
        "result": None,
        "error": None,
        "done": False,
        "created_at": time.monotonic(),
    }
    _backtest_jobs[job_id] = record
    return job_id, record


def get_backtest_job(job_id: str) -> dict[str, Any] | None:
    return _backtest_jobs.get(job_id)
