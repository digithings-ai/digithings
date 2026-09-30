"""Stdlib checks for the digiquant-runner allowlist. No uv, no pytest."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

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

    _check_phase2(commands)
    print("ok")
    return 0


def _check_phase2(commands: dict[str, Any]) -> None:
    repo = Path(__file__).resolve().parents[3]
    today = "2026-09-30"

    onchain = exec_job.steps_for("onchain-bitview", {}, commands)
    if onchain != [
        [
            "uv",
            "run",
            "--frozen",
            "--no-sync",
            "python",
            "-m",
            "digiquant",
            "onchain",
            "fetch-bitview",
            "--cache-dir",
            "data/onchain/bitview",
            "--supabase",
        ]
    ]:
        raise SystemExit(f"unexpected onchain argv: {onchain}")

    probe = exec_job.steps_for("execution-cron-check", {}, commands)
    if len(probe) != 5:
        raise SystemExit(f"execution probe must keep five steps, got {len(probe)}")
    joined = " ".join(" ".join(step) for step in probe)
    if "--execute" in joined or "--all" in joined or "portfolio.chain" in joined:
        raise SystemExit(f"probe gained a live flag: {joined}")
    if probe[0][-1] != "scripts/execution_cron_check.py":
        raise SystemExit(f"probe step 1 drifted: {probe[0]}")
    for step in probe[1:]:
        if "--dry-run" not in step:
            raise SystemExit(f"probe dry-run missing: {step}")
    probe_plans = exec_job.plans_for("execution-cron-check", {}, commands)
    if any(plan.always for plan in probe_plans[:1]) or not all(
        plan.always for plan in probe_plans[1:]
    ):
        raise SystemExit("later probe steps must run after an earlier failure")

    empty = exec_job.steps_for("research-metrics", {}, commands, today=today)
    if len(empty) != 5:
        raise SystemExit(f"empty date must select five metrics steps, got {len(empty)}")
    if any(part == "--date" or part.endswith(" --date") for part in empty[0]):
        raise SystemExit(f"finalize no-date branch drifted: {empty[0]}")
    if not any(part.endswith("finalize_period_accounting.py") for part in empty[0]):
        raise SystemExit(f"finalize no-date branch drifted: {empty[0]}")
    if empty[1][-2:] != ["--mark-through", today] or "--write" not in empty[1]:
        raise SystemExit(f"verify write no-date branch drifted: {empty[1]}")
    if "--mark-through-book" not in empty[2] or "--date" in empty[2]:
        raise SystemExit(f"metrics no-date branch drifted: {empty[2]}")
    read_only = empty[3]
    if (
        not read_only[-1].endswith("verify_nav_replay.py")
        or "--write" in read_only
        or "--date" in read_only
    ):
        raise SystemExit(f"read-only verify drifted: {read_only}")
    if "--date" in empty[4] or not any(
        part.endswith("refresh_attribution.py") for part in empty[4]
    ):
        raise SystemExit(f"attribution no-date branch drifted: {empty[4]}")
    dated = exec_job.steps_for(
        "research-metrics",
        {"date": "2026-01-02"},
        commands,
        today=today,
    )
    if dated[0][-2:] != ["--date", "2026-01-02"]:
        raise SystemExit(f"finalize date branch drifted: {dated[0]}")
    if dated[1][-2:] != ["--date", "2026-01-02"] or "--mark-through" in dated[1]:
        raise SystemExit(f"verify write date branch drifted: {dated[1]}")
    if dated[2][-2:] != ["--date", "2026-01-02"] or "--mark-through-book" in dated[2]:
        raise SystemExit(f"metrics date branch drifted: {dated[2]}")
    if dated[4][-2:] != ["--date", "2026-01-02"]:
        raise SystemExit(f"attribution date branch drifted: {dated[4]}")
    blank = exec_job.steps_for("research-metrics", {"date": ""}, commands, today=today)
    if blank[1][-1] != today:
        raise SystemExit("blank date must use the no-date branch")
    metrics_plans = exec_job.plans_for("research-metrics", {}, commands, today=today)
    if not metrics_plans[0].continue_on_error or not metrics_plans[-1].always:
        raise SystemExit("finalize must continue and attribution must always run")
    if metrics_plans[3].always or metrics_plans[3].continue_on_error:
        raise SystemExit("read-only verify must not run after a metrics failure")

    sheets = exec_job.steps_for("tearsheets", {}, commands, workdir=repo)
    if len(sheets) != 4:
        raise SystemExit(f"tearsheets with export script must be 4 steps, got {len(sheets)}")
    if not any(part.endswith("verify_strategy_calibrations_rls.py") for part in sheets[0]):
        raise SystemExit(f"calibrations step drifted: {sheets[0]}")
    if sheets[1][:5] != ["uv", "run", "--frozen", "--with", "ccxt"] or "--no-sync" in sheets[1]:
        raise SystemExit(f"coinbase step must use --with ccxt and not --no-sync: {sheets[1]}")
    if "--through-yesterday" not in sheets[1]:
        raise SystemExit(f"coinbase flags drifted: {sheets[1]}")
    if not any(part.endswith("export_sdca_macro.py") for part in sheets[2]):
        raise SystemExit(f"export step drifted: {sheets[2]}")
    if "--push-supabase" not in sheets[3] or "--signal-delay-days" not in sheets[3]:
        raise SystemExit(f"generate step drifted: {sheets[3]}")
    if sheets[3][sheets[3].index("--signal-delay-days") + 1] != "3":
        raise SystemExit(f"signal delay drifted: {sheets[3]}")
    skipped = exec_job.steps_for(
        "tearsheets",
        {},
        commands,
        workdir=Path("/tmp/digiquant-runner-no-export"),
    )
    export_ran = any("export_sdca_macro.py" in part for step in skipped for part in step)
    if export_ran or len(skipped) != 3:
        raise SystemExit(f"missing export script must skip that step, got {skipped}")

    child = exec_job.build_child_env("research-metrics", run_id="run-2", commands=commands)
    if child.get("DIGIQUANT_MARKET_DATA_BACKEND") != "r2":
        raise SystemExit(f"metrics missing r2 backend: {child}")
    if child.get("DIGIQUANT_ACCOUNTING_FINALIZER") != "shadow":
        raise SystemExit(f"metrics missing shadow finalizer: {child}")
    if "RUNNER_AUTH_TOKEN" in child or "GH_ISSUE_TOKEN" in child:
        raise SystemExit("worker token leaked into metrics child env")

    kept, code = exec_job.classify_step_exit(
        1,
        continue_on_error=True,
        hard_failure=False,
        exit_code=0,
    )
    if kept or code != 0:
        raise SystemExit("continue_on_error must not fail the job")
    failed, code = exec_job.classify_step_exit(
        3,
        continue_on_error=False,
        hard_failure=False,
        exit_code=0,
    )
    if not failed or code != 3:
        raise SystemExit("metrics exit 3 must stick")
    still, code = exec_job.classify_step_exit(
        2,
        continue_on_error=False,
        hard_failure=True,
        exit_code=3,
    )
    if not still or code != 3:
        raise SystemExit("later failure must keep the first exit code")

    root = repo
    dockerfile = (root / "Dockerfile.digiquant-runner").read_text(encoding="utf-8")
    wrangler = (root / "apps/digiquant-runner/wrangler.toml").read_text(encoding="utf-8")
    ignore = (root / ".dockerignore").read_text(encoding="utf-8")
    sync = "uv sync --frozen --package digiquant --extra prices --extra research --extra nautilus"
    if sync not in dockerfile or "scripts/execution_cron_check.py" not in dockerfile:
        raise SystemExit("image must install nautilus and copy the probe wrapper")
    if "DigiQuantRunnerNautilusContainer" in wrangler:
        raise SystemExit("nautilus stays on the phase 1 class")
    if ignore.count("!scripts/execution_cron_check.py") != 1:
        raise SystemExit("probe wrapper must be re-included in .dockerignore")


if __name__ == "__main__":
    raise SystemExit(main())
