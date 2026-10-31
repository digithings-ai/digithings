#!/usr/bin/env python3
"""Render the launchd clocks for the digiquant host runner (DIG-2915).

The schedule is not invented here. Every row below is one enabled container row in
``apps/digithings-cron/src/jobs.ts``, copied with its cron and its catalogue job.
``tests/scripts/test_digiquant_host_runner.py`` parses ``jobs.ts`` and fails when the
two disagree, so a moved clock in the Worker cannot leave a stale one on the Mac.

The crons are UTC because that is what the Worker's ``[triggers] crons`` mean. launchd's
``StartCalendarInterval`` is local time, and it cannot express a time zone. So:

* each row is converted at render time from its next UTC occurrence to the Mac's local
  clock, which keeps it correct across a DST change for that occurrence;
* the rendered plist carries the UTC cron in a comment, and ``install.sh --status``
  compares the file on disk with a fresh render, so a change that crosses a DST
  boundary shows up as ``stale`` instead of as a job that silently runs an hour late.

Weekday numbers follow launchd: 0 and 7 are Sunday, 1 is Monday.

Usage (normally through install.sh):

    python3 schedule.py --list
    python3 schedule.py --render-to /tmp/plists --checkout /path/to/digithings
    python3 schedule.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, NamedTuple
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "com.digithings.digiquant-job.plist.template"
LABEL_PREFIX = "com.digithings.digiquant."
UV = "/opt/homebrew/bin/uv"
DEFAULT_ENV_FILE = "~/.config/digithings/digiquant-host-runner.env"
DEFAULT_LOG_DIR = "~/.config/digithings/logs/digiquant-host-runner"

UTC_DAY = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}


class Row(NamedTuple):
    """One enabled container clock, as digithings-cron declares it."""

    label: str  # the row id in jobs.ts; also the launchd label suffix
    job: str  # the commands.json job name
    cron: str  # the UTC cron, five fields


ROWS: tuple[Row, ...] = (
    # Disabled 2026-10-31 with their digithings-cron rows: the runner fails these
    # on a stale CORE_POSTGRES_URI (~350 failures/day, digikey_app lockout risk).
    # Re-enabling needs the S7 fix; restore these lines with the jobs.ts rows.
    # Row("market-data-refresh-morning", "market-data-refresh", "0 13 * * *"),
    # Row("market-data-refresh-evening", "market-data-refresh", "30 21 * * *"),
    # Row("checkpoint-archive", "checkpoint-archive", "30 13 * * *"),
    Row("prices-at-open-13", "prices-at-open", "40 13 * * MON-FRI"),
    Row("prices-at-open-14", "prices-at-open", "40 14 * * MON-FRI"),
    Row("prices-fx-refresh", "prices-fx-candles", "19 */2 * * MON-FRI"),
    Row("prices-fx-refresh-sun", "prices-fx-candles", "19 22 * * SUN"),
    Row("prices-eod-macro", "prices-eod-macro", "27 21 * * MON-FRI"),
    Row("house-run-09", "house-run", "17 9 * * MON"),
    Row("research-metrics", "research-metrics", "5 22 * * *"),
    Row("tearsheets", "tearsheets", "12 0 * * *"),
    Row("onchain", "onchain-bitview", "40 22 * * *"),
    Row("execution-cron-check", "execution-cron-check", "15 12 * * *"),
)


def label_for(row: Row) -> str:
    return f"{LABEL_PREFIX}{row.label}"


class CronError(ValueError):
    """A cron form this renderer does not support. Loud, never silent."""


def _int_field(raw: str, low: int, high: int, what: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise CronError(f"{what}: {raw!r} is not a number") from exc
    if not low <= value <= high:
        raise CronError(f"{what}: {value} is outside {low}-{high}")
    return value


def parse_cron(expr: str) -> list[dict[str, int]]:
    """Expand a five-field UTC cron into launchd interval dicts (UTC weekday/hour/minute).

    Only the forms this repository uses are supported: ``*`` or a number in each of
    minute and hour, ``*/N`` in hour, ``*`` for day-of-month and month, and ``*``, one
    weekday name or a ``A-B`` weekday range in day-of-week. Anything else raises,
    because a cron this renderer misreads would move a production clock.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise CronError(f"cron needs five fields, got {len(fields)}: {expr!r}")
    minute_raw, hour_raw, dom, month, dow = fields
    if dom != "*" or month != "*":
        raise CronError(f"day-of-month and month must be '*': {expr!r}")
    if minute_raw == "*":
        minutes = list(range(0, 60))
    else:
        minutes = [_int_field(minute_raw, 0, 59, "minute")]
    if hour_raw == "*":
        hours = list(range(0, 24))
    elif hour_raw.startswith("*/"):
        step = _int_field(hour_raw[2:], 1, 24, "hour step")
        hours = list(range(0, 24, step))
    else:
        hours = [_int_field(hour_raw, 0, 23, "hour")]
    if dow == "*":
        weekdays: list[int] = []
    elif "-" in dow:
        start_raw, _, end_raw = dow.partition("-")
        start = _day_name(start_raw)
        end = _day_name(end_raw)
        if end < start:
            raise CronError(f"weekday range must not wrap: {dow!r}")
        weekdays = list(range(start, end + 1))
    else:
        weekdays = [_day_name(dow)]
    intervals: list[dict[str, int]] = []
    for weekday in weekdays or [None]:
        for hour in hours:
            for minute in minutes:
                interval = {"Hour": hour, "Minute": minute}
                if weekday is not None:
                    interval["Weekday"] = weekday
                intervals.append(interval)
    return intervals


def _day_name(raw: str) -> int:
    key = raw.strip().upper()
    if key not in UTC_DAY:
        raise CronError(f"unknown weekday: {raw!r}")
    return UTC_DAY[key]


def _next_utc(interval: dict[str, int], now: datetime) -> datetime:
    """The first UTC instant at or after ``now`` that matches one interval."""
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    weekday = interval.get("Weekday")
    for _ in range(8 * 24 * 60):
        if candidate.hour == interval["Hour"] and candidate.minute == interval["Minute"]:
            # launchd: 0 and 7 are Sunday. Python: Monday is 0, Sunday is 6.
            sunday_based = (candidate.weekday() + 1) % 7
            if weekday is None or sunday_based == weekday:
                return candidate
        candidate += timedelta(minutes=1)
    raise CronError(f"no occurrence within 8 days for {interval}")  # pragma: no cover


def local_intervals(expr: str, now: datetime | None = None) -> list[dict[str, int]]:
    """Convert a UTC cron into the local-time launchd intervals it fires at.

    Each UTC occurrence is resolved against the Mac's own zone rules, so the next
    occurrence is right in the current offset. A weekly clock that crosses a DST
    change keeps firing at the old local hour until the plist is re-rendered;
    ``install.sh --status`` reports that as ``stale``.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seen: set[tuple[int, int, int | None]] = set()
    out: list[dict[str, int]] = []
    for interval in parse_cron(expr):
        local = _next_utc(interval, moment).astimezone()
        key = (local.hour, local.minute, (local.weekday() + 1) % 7 if "Weekday" in interval else None)
        if key in seen:
            continue
        seen.add(key)
        entry = {"Hour": local.hour, "Minute": local.minute}
        if "Weekday" in interval:
            entry["Weekday"] = (local.weekday() + 1) % 7
        out.append(entry)
    out.sort(key=lambda item: (item.get("Weekday", -1), item["Hour"], item["Minute"]))
    return out


def _interval_xml(intervals: Iterable[dict[str, int]]) -> str:
    lines = ["<key>StartCalendarInterval</key>", "<array>"]
    for interval in intervals:
        lines.append("<dict>")
        for key in ("Weekday", "Hour", "Minute"):
            if key in interval:
                lines.append(f"<key>{key}</key><integer>{int(interval[key])}</integer>")
        lines.append("</dict>")
    lines.append("</array>")
    return "\n".join(lines)


def render_plist(
    row: Row,
    *,
    checkout: Path,
    env_file: str,
    now: datetime | None = None,
) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    checkout_text = str(checkout)
    replacements = {
        "__LABEL__": escape(label_for(row)),
        "__JOB__": escape(row.job),
        "__CRON__": escape(row.cron),
        "__PROGRAM__": escape(UV),
        "__CHECKOUT__": escape(checkout_text),
        "__SCRIPT__": escape(f"{checkout_text}/scripts/digiquant-host-runner/run_job.py"),
        "__ENVFILE__": escape(str(Path(env_file).expanduser())),
        "__LOGDIR__": escape(str(Path(DEFAULT_LOG_DIR).expanduser())),
        "__HOME__": escape(str(Path.home())),
        "__INTERVALS__": _interval_xml(local_intervals(row.cron, now)),
    }
    out = template
    for token, value in replacements.items():
        out = out.replace(token, value)
    leftover = [token for token in replacements if token in out]
    if leftover:  # pragma: no cover - defensive
        raise ValueError(f"unreplaced template tokens: {leftover}")
    return out


def render_all(
    *,
    checkout: Path,
    env_file: str = DEFAULT_ENV_FILE,
    now: datetime | None = None,
) -> dict[str, str]:
    return {label_for(row): render_plist(row, checkout=checkout, env_file=env_file, now=now) for row in ROWS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schedule.py", description=__doc__.splitlines()[0])
    parser.add_argument("--checkout", default=str(HERE.parents[1]))
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--list", action="store_true", help="print label, job and UTC cron")
    parser.add_argument("--json", action="store_true", help="print rows with local intervals")
    parser.add_argument("--render-to", metavar="DIR", help="write one plist per row into DIR")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    checkout = Path(args.checkout).expanduser().resolve()
    if args.list:
        for row in ROWS:
            print(f"{label_for(row)}\t{row.job}\t{row.cron}")
        return 0
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "label": label_for(row),
                        "job": row.job,
                        "cron": row.cron,
                        "local": local_intervals(row.cron),
                    }
                    for row in ROWS
                ],
                indent=2,
            )
        )
        return 0
    rendered = render_all(checkout=checkout, env_file=args.env_file)
    if args.render_to:
        target = Path(args.render_to).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        for label, text in rendered.items():
            (target / f"{label}.plist").write_text(text, encoding="utf-8")
        print(f"render-to: wrote {len(rendered)} plists to {target}")
        return 0
    for text in rendered.values():
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
