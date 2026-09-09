#!/usr/bin/env python3
"""Skip a later house cron when today's pipeline already succeeded.

GitHub ``schedule`` at minute 0 is delayed for hours under load. House uses
the same off-peak minute as FX Hub (``17``) plus hourly retries; this helper
prevents those retries from re-running the LLM chain after a success.

Stdlib only — the GHA gate job must not ``uv sync``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

WORKFLOW_FILE = "pipeline-digiquant.yml"


# Only these events count as "today's house already landed". A same-day
# workflow_dispatch dry-run success must not suppress the scheduled book.
_COUNTING_EVENTS = frozenset({"schedule", "repository_dispatch"})


@dataclass(frozen=True)
class PriorRun:
    """Sanitized Actions run — ids, event, and conclusions only."""

    run_id: int
    status: str
    conclusion: str | None
    created_at: datetime
    event: str


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def parse_runs(raw: object) -> tuple[PriorRun, ...]:
    """Build runs from ``gh run list --json``. Never logs the payload."""
    if not isinstance(raw, list):
        return ()
    rows: list[PriorRun] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        run_id = item.get("databaseId")
        status = item.get("status")
        created = item.get("createdAt")
        event = item.get("event")
        if not isinstance(run_id, int) or not isinstance(status, str):
            continue
        if not isinstance(created, str) or not isinstance(event, str):
            continue
        conclusion = item.get("conclusion")
        rows.append(
            PriorRun(
                run_id=run_id,
                status=status,
                conclusion=conclusion if isinstance(conclusion, str) else None,
                created_at=parse_utc(created),
                event=event,
            )
        )
    return tuple(rows)


def should_skip_house_run(
    *,
    current_run_id: int,
    run_date: date,
    runs: Sequence[PriorRun],
    force: bool = False,
) -> bool:
    """True when another completed success already exists on ``run_date`` UTC."""
    if force:
        return False
    start = datetime(run_date.year, run_date.month, run_date.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    for run in runs:
        if run.run_id == current_run_id:
            continue
        if run.event not in _COUNTING_EVENTS:
            continue
        if run.status != "completed" or run.conclusion != "success":
            continue
        if start <= run.created_at < end:
            return True
    return False


def _list_runs() -> tuple[PriorRun, ...]:
    proc = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            WORKFLOW_FILE,
            "--limit",
            "30",
            "--json",
            "databaseId,conclusion,status,createdAt,event",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ()
    try:
        payload: object = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return ()
    return parse_runs(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--current-run-id", required=True, type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--runs-json", default="")
    args = parser.parse_args()
    run_date = date.fromisoformat(args.run_date)
    if args.runs_json:
        payload: object = json.loads(Path(args.runs_json).read_text(encoding="utf-8"))
        runs = parse_runs(payload)
    else:
        runs = _list_runs()
    skip = should_skip_house_run(
        current_run_id=args.current_run_id,
        run_date=run_date,
        runs=runs,
        force=args.force,
    )
    print(f"skip={str(skip).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
