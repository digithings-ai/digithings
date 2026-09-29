"""Stdlib checks for the digiquant-runner allowlist. No uv, no pytest."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_job  # noqa: E402


def main() -> int:
    commands = exec_job.load_commands()

    calendar = exec_job.steps_for("prices-eod-macro", {}, commands)
    if len(calendar) != 1:
        raise SystemExit(f"expected only sync-calendar, got {len(calendar)} steps")
    if "sync-calendar" not in calendar[0] or "fetch-macro" in calendar[0]:
        raise SystemExit(f"unexpected calendar argv: {calendar[0]}")

    both = exec_job.steps_for("prices-eod-macro", {"run_writers": "true"}, commands)
    if len(both) != 2:
        raise SystemExit(f"expected both eod steps, got {len(both)}")
    if "sync-calendar" not in both[0] or "fetch-macro" not in both[1]:
        raise SystemExit(f"unexpected gated argv: {both}")

    writers = exec_job.steps_for("prices-fx-refresh-writers", {}, commands)
    if writers != []:
        raise SystemExit(f"writers without run_writers must be empty, got {writers}")

    try:
        exec_job.steps_for("nope", {}, commands)
    except SystemExit as exc:
        if "unknown command" not in str(exc):
            raise
    else:
        raise SystemExit("expected SystemExit for unknown command")

    os.environ["RUNNER_AUTH_TOKEN"] = "super-secret"
    os.environ["GH_ISSUE_TOKEN"] = "also-secret"
    try:
        child = exec_job.build_child_env("prices-at-open", run_id="run-1", commands=commands)
    finally:
        os.environ.pop("RUNNER_AUTH_TOKEN", None)
        os.environ.pop("GH_ISSUE_TOKEN", None)
    if child.get("DIGIQUANT_MARKET_DATA_BACKEND") != "r2":
        raise SystemExit(f"missing r2 backend: {child}")
    if "RUNNER_AUTH_TOKEN" in child or "GH_ISSUE_TOKEN" in child:
        raise SystemExit(f"worker token leaked into child env: {sorted(child)}")
    if child.get("RUN_ID") != "run-1":
        raise SystemExit(f"missing RUN_ID: {child}")

    flat = str(exec_job.steps_for("prices-fx-candles", {}, commands))
    if "fetch-macro" in flat:
        raise SystemExit("prices-fx-candles must not call fetch-macro")

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
