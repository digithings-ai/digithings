"""digiclaw CLI — ``digiclaw schedule …`` and heartbeat entry.

Heartbeat remains available as ``digiclaw heartbeat`` (and ``python -m digiclaw``).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from digiclaw.scheduler import (
    Scheduler,
    SchedulerError,
    default_agents_dir,
    default_state_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digiclaw",
        description="digiclaw — heartbeat, audit, and agent scheduling.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    heartbeat = sub.add_parser("heartbeat", help="Run one heartbeat cycle and exit")
    heartbeat.set_defaults(_handler=_cmd_heartbeat)

    schedule = sub.add_parser("schedule", help="Agent schedule lifecycle and status")
    schedule_sub = schedule.add_subparsers(dest="command", required=True)

    status = schedule_sub.add_parser("status", help="Show lifecycle and next run times")
    _add_schedule_paths(status)
    status.set_defaults(_handler=_cmd_schedule_status)

    start = schedule_sub.add_parser("start", help="Start a scheduled agent")
    _add_schedule_paths(start)
    start.add_argument("agent", help="Agent name from YAML definition")
    start.set_defaults(_handler=_cmd_schedule_start)

    stop = schedule_sub.add_parser("stop", help="Stop a scheduled agent")
    _add_schedule_paths(stop)
    stop.add_argument("agent", help="Agent name from YAML definition")
    stop.set_defaults(_handler=_cmd_schedule_stop)

    pause = schedule_sub.add_parser("pause", help="Pause a running agent")
    _add_schedule_paths(pause)
    pause.add_argument("agent", help="Agent name from YAML definition")
    pause.set_defaults(_handler=_cmd_schedule_pause)

    resume = schedule_sub.add_parser("resume", help="Resume a paused agent")
    _add_schedule_paths(resume)
    resume.add_argument("agent", help="Agent name from YAML definition")
    resume.set_defaults(_handler=_cmd_schedule_resume)

    tick = schedule_sub.add_parser(
        "tick",
        help="Process due jobs once (for tests / external supervisors)",
    )
    _add_schedule_paths(tick)
    tick.set_defaults(_handler=_cmd_schedule_tick)

    return parser


def _add_schedule_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agents-dir",
        type=Path,
        default=None,
        help="Directory of agent YAML files (default: DIGICLAW_AGENTS_DIR or digiclaw/agents)",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=None,
        help="Scheduler state JSON path (default: DIGICLAW_SCHEDULER_STATE)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.error("unknown command")
    try:
        return int(handler(args))
    except SchedulerError as exc:
        print(f"error[{exc.code}]: {exc.message}", file=sys.stderr)
        return 2


def _scheduler_from_args(args: argparse.Namespace) -> Scheduler:
    from digiclaw.scheduler import JsonStateStore

    agents_dir = args.agents_dir or default_agents_dir()
    state_path = args.state or default_state_path()
    return Scheduler(agents_dir=agents_dir, state_store=JsonStateStore(state_path))


def _cmd_heartbeat(_args: argparse.Namespace) -> int:
    from digiclaw.heartbeat_runner import main as heartbeat_main

    return int(heartbeat_main())


def _cmd_schedule_status(args: argparse.Namespace) -> int:
    scheduler = _scheduler_from_args(args)
    rows = scheduler.status()
    if not rows:
        print("no agents loaded")
        return 0
    print(f"{'NAME':<20} {'MODE':<12} {'LIFE':<10} {'NEXT_RUN_AT':<28} {'LAST_STATUS':<10} PENDING")
    for row in rows:
        next_s = _fmt_dt(row.next_run_at)
        last = row.last_status or "-"
        print(
            f"{row.name:<20} {row.mode.value:<12} {row.lifecycle.value:<10} "
            f"{next_s:<28} {last:<10} {str(row.pending).lower()}"
        )
    return 0


def _cmd_schedule_start(args: argparse.Namespace) -> int:
    runtime = _scheduler_from_args(args).start(args.agent)
    print(f"started {args.agent}: next_run_at={_fmt_dt(runtime.next_run_at)}")
    return 0


def _cmd_schedule_stop(args: argparse.Namespace) -> int:
    _scheduler_from_args(args).stop(args.agent)
    print(f"stopped {args.agent}")
    return 0


def _cmd_schedule_pause(args: argparse.Namespace) -> int:
    _scheduler_from_args(args).pause(args.agent)
    print(f"paused {args.agent}")
    return 0


def _cmd_schedule_resume(args: argparse.Namespace) -> int:
    runtime = _scheduler_from_args(args).resume(args.agent)
    print(f"resumed {args.agent}: next_run_at={_fmt_dt(runtime.next_run_at)}")
    return 0


def _cmd_schedule_tick(args: argparse.Namespace) -> int:
    outcomes = _scheduler_from_args(args).tick()
    if not outcomes:
        print("no due jobs")
        return 0
    for outcome in outcomes:
        if outcome.ok:
            print(f"ran {outcome.name}: ok")
        else:
            print(f"ran {outcome.name}: error ({outcome.error})")
    return 0


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.isoformat()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
