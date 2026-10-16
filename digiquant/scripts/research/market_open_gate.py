#!/usr/bin/env python3
"""Resolve whether an at-open workflow trigger may write the Activity ledger."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_OPEN_ET = time(9, 30)
_SUMMER_SCHEDULE = "35 13 * * MON-FRI"
_WINTER_SCHEDULE = "35 14 * * MON-FRI"


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def should_run_at_open(*, now: datetime, schedule: str, force: bool = False) -> bool:
    if force:
        return True
    utc_now = now.astimezone(timezone.utc)
    et_now = utc_now.astimezone(_ET)
    expected_schedule = (
        _SUMMER_SCHEDULE if et_now.utcoffset().total_seconds() == -4 * 3600 else _WINTER_SCHEDULE
    )
    return schedule == expected_schedule and et_now.time() >= _OPEN_ET


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", default="")
    parser.add_argument("--now-utc", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    now = parse_utc(args.now_utc) if args.now_utc else datetime.now(timezone.utc)
    allowed = should_run_at_open(now=now, schedule=args.schedule, force=args.force)
    print(f"in_window={str(allowed).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
