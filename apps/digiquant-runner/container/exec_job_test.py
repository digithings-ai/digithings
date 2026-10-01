"""Stdlib checks for the digiquant-runner allowlist. No uv, no pytest."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest import mock

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
    _check_busy_gate_and_publish_bound()
    _check_publish_if_present(commands)
    _check_house_run(commands)
    for mod_name in (
        "house_chain_step_test",
        "wake_stack_test",
        "web_search_preflight_test",
    ):
        mod = __import__(mod_name)
        code = mod.main()
        if code not in (0, None):
            raise SystemExit(f"{mod_name} failed: {code}")
    print("ok")
    return 0


def _check_busy_gate_and_publish_bound() -> None:
    """Same-command /run must 409 while running; publish is wall-clock bounded."""
    import json
    import tempfile
    import time
    from unittest import mock

    with tempfile.TemporaryDirectory() as tmp:
        status_dir = Path(tmp)
        previous = exec_job.STATUS_DIR
        exec_job.STATUS_DIR = status_dir
        try:
            if exec_job._running_command("market-data-refresh") is not None:
                raise SystemExit("empty status dir must report no busy command")
            payload = {
                "run_id": "run-alive",
                "command": "market-data-refresh",
                "status": "running",
            }
            (status_dir / "run-alive.status.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            busy = exec_job._running_command("market-data-refresh")
            if busy != "run-alive":
                raise SystemExit(f"expected run-alive busy, got {busy!r}")
            if exec_job._running_command("prices-at-open") is not None:
                raise SystemExit("other commands must stay free")
            payload["status"] = "succeeded"
            (status_dir / "run-alive.status.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            if exec_job._running_command("market-data-refresh") is not None:
                raise SystemExit("terminal status must clear the busy gate")
        finally:
            exec_job.STATUS_DIR = previous

    previous_timeout = exec_job.PUBLISH_TIMEOUT_SECONDS
    exec_job.PUBLISH_TIMEOUT_SECONDS = 0.05

    def _hang(*_args: object, **_kwargs: object) -> None:
        time.sleep(1.0)

    try:
        with mock.patch.object(exec_job, "_publish", _hang):
            try:
                exec_job._publish_bounded("market-data-refresh", "run-1", ["/tmp/x"])
            except TimeoutError as exc:
                if "publish exceeded" not in str(exc):
                    raise SystemExit(f"unexpected timeout message: {exc}") from exc
            else:
                raise SystemExit("hung publish must raise TimeoutError")
    finally:
        exec_job.PUBLISH_TIMEOUT_SECONDS = previous_timeout


def _check_publish_if_present(commands: dict[str, Any]) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        present = root / "checkpoint-archive-manifests.json"
        present.write_text("[]", encoding="utf-8")
        missing = root / "checkpoint-size-pre.json"
        kept = exec_job.publish_paths_present(
            [str(present), str(missing)],
            exists=lambda path: Path(path).is_file(),
        )
        if kept != [str(present)]:
            raise SystemExit(f"optional publish kept {kept}")
        try:
            exec_job.raise_if_required_missing(str(missing))
        except RuntimeError as exc:
            if "publish file missing" not in str(exc):
                raise
        else:
            raise SystemExit("required publish must reject a missing file")
        exec_job.raise_if_required_missing(str(present))
        neither = exec_job.publish_paths_present(
            [str(missing), str(root / "also-missing.json")],
            exists=lambda path: Path(path).is_file(),
        )
        if neither != []:
            raise SystemExit(f"missing optional paths must be a no-op, got {neither}")
        selected = exec_job._selected_publish_paths(
            {
                "publish": [str(missing)],
                "publish_if_present": [str(present), str(missing)],
            }
        )
        if selected != [str(missing), str(present)]:
            raise SystemExit(f"required path must stay strict, got {selected}")
        if exec_job._selected_publish_paths({"publish_if_present": [str(missing)]}) != []:
            raise SystemExit("dry-run with neither file must publish nothing")

        uploaded: list[str] = []

        class _Client:
            def upload_file(self, _filename: str, _bucket: str, key: str) -> None:
                uploaded.append(key)

        with mock.patch.object(exec_job, "_require_r2", return_value=(_Client(), "bucket")):
            try:
                exec_job._publish("market-data-refresh", "run-x", [str(missing)])
            except RuntimeError as exc:
                if "publish file missing" not in str(exc):
                    raise
            else:
                raise SystemExit("_publish must reject a missing required file")
            exec_job._publish("checkpoint-archive", "run-x", [str(present)])
        if uploaded != [
            "pipeline-runs/checkpoint-archive/run-x/checkpoint-archive-manifests.json"
        ]:
            raise SystemExit(f"present file was not published: {uploaded}")

    dry = exec_job.steps_for("checkpoint-archive", {"dry_run": "true"}, commands)
    live = exec_job.steps_for("checkpoint-archive", {}, commands)
    if len(dry) != 2 or len(live) != 2:
        raise SystemExit(f"checkpoint-archive step counts drifted: dry={len(dry)} live={len(live)}")
    if not any(part.endswith("digiquant_checkpoint_size_gate.py") for part in dry[0]):
        raise SystemExit(f"size gate must always run, got {dry[0]}")
    if "--snapshot-out" not in dry[0] or "--dry-run" in dry[0]:
        raise SystemExit(f"size gate argv drifted: {dry[0]}")
    if dry[0] != live[0]:
        raise SystemExit("size gate must run on both dry-run and live")
    if "--dry-run" not in dry[1] or "--retain-days" not in dry[1]:
        raise SystemExit(f"dry_run must select --dry-run archive, got {dry[1]}")
    if "--dry-run" in live[1] or "--manifest-out" not in live[1]:
        raise SystemExit(f"empty dry_run must select the live archive, got {live[1]}")
    spec = commands["checkpoint-archive"]
    if spec.get("publish"):
        raise SystemExit("checkpoint-archive must not use required publish")
    if spec.get("publish_if_present") != [
        "/tmp/checkpoint-archive-manifests.json",
        "/tmp/checkpoint-size-pre.json",
    ]:
        raise SystemExit(f"publish_if_present drifted: {spec.get('publish_if_present')}")
    if spec.get("timeout_seconds") != 3600:
        raise SystemExit(f"timeout drifted: {spec.get('timeout_seconds')}")


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
    house_sync = "uv sync --frozen --inexact --package digigraph --extra checkpoint-postgres"
    if house_sync not in dockerfile:
        raise SystemExit("house image must inexact-sync digigraph checkpoint-postgres")
    for needle in (
        "COPY digigraph ./digigraph",
        "COPY digillm ./digillm",
        "COPY digismith ./digismith",
        "COPY config/byok-providers.json",
        "COPY .github/digiquant-pipeline.yml",
        "COPY .github/workflows/pipeline-digiquant-allocation-shadow.yml",
        "/opt/runner/house_chain_step.py",
        "/opt/runner/wake_stack.py",
        "/opt/runner/web_search_preflight.py",
    ):
        if needle not in dockerfile:
            raise SystemExit(f"house image missing {needle}")
    github_at = ignore.find("\n.github\n")
    pipeline_at = ignore.find("!.github/digiquant-pipeline.yml")
    shadow_at = ignore.find("!.github/workflows/pipeline-digiquant-allocation-shadow.yml")
    if github_at < 0 or pipeline_at < github_at or shadow_at < pipeline_at:
        raise SystemExit("pipeline and shadow re-includes must follow the .github exclude")
    if "DigiQuantRunnerNautilusContainer" in wrangler:
        raise SystemExit("nautilus stays on the phase 1 class")
    if wrangler.count("[[containers]]") != 1:
        raise SystemExit("runner must keep a single container class")
    if 'instance_type = "standard-2"' not in wrangler or "max_instances = 1" not in wrangler:
        raise SystemExit("runner must stay on standard-2 with max_instances 1")
    if "standard-3" in wrangler or "standard-4" in wrangler:
        raise SystemExit("runner must not add a larger instance type")
    if 'binding = "ARCHIVE"' not in wrangler or 'bucket_name = "digithings-archive"' not in wrangler:
        raise SystemExit("house ledger binding ARCHIVE on digithings-archive is required")
    runner_ts = (root / "apps/digiquant-runner/src/runner.ts").read_text(encoding="utf-8")
    if 'sleepAfter = "2m"' not in runner_ts or '"30m"' not in runner_ts:
        raise SystemExit("idle sleepAfter stays 2m and busy window stays 30m")
    if ignore.count("!scripts/execution_cron_check.py") != 1:
        raise SystemExit("probe wrapper must be re-included in .dockerignore")
    scripts_at = ignore.find("\nscripts\n")
    archive_copy = "COPY scripts/digiquant_archive_checkpoints.py"
    gate_copy = "COPY scripts/digiquant_checkpoint_size_gate.py"
    if archive_copy not in dockerfile or gate_copy not in dockerfile:
        raise SystemExit("image must copy the checkpoint-archive scripts")
    archive_at = ignore.find("!scripts/digiquant_archive_checkpoints.py")
    gate_at = ignore.find("!scripts/digiquant_checkpoint_size_gate.py")
    if scripts_at < 0 or archive_at < scripts_at or gate_at < archive_at:
        raise SystemExit("checkpoint scripts must be re-included after scripts/")


def _check_house_run(commands: dict[str, Any]) -> None:
    text = 'env:\n  DIGIQUANT_MODEL_TIER: "cheap"\n  DIGI_CHECKPOINTER: postgres\n'
    got = exec_job.load_pipeline_env(text)
    if got["DIGIQUANT_MODEL_TIER"] != "cheap" or got["DIGI_CHECKPOINTER"] != "postgres":
        raise SystemExit(f"pipeline env parse drifted: {got}")
    commented = 'env:\n  DIGI_CHECKPOINTER: postgres          # resume\n  LANGSMITH_TRACING: "true"\n'
    parsed = exec_job.load_pipeline_env(commented)
    if parsed["DIGI_CHECKPOINTER"] != "postgres" or parsed["LANGSMITH_TRACING"] != "true":
        raise SystemExit(f"pipeline comment parse drifted: {parsed}")

    saved = {name: os.environ.get(name) for name in ("RUNNER_AUTH_TOKEN", "GH_ISSUE_TOKEN", "CHEAPERINFERENCE_API_BASE")}
    os.environ["RUNNER_AUTH_TOKEN"] = "sekret"
    os.environ["GH_ISSUE_TOKEN"] = "nope"
    os.environ.pop("CHEAPERINFERENCE_API_BASE", None)
    try:
        env = exec_job.build_child_env(
            "house-run",
            run_id="run-abc",
            commands=commands,
            args={"run_date": "2026-09-30", "refresh_scope": "none"},
        )
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
    if env.get("GITHUB_RUN_ID") != "run-abc":
        raise SystemExit(f"missing GITHUB_RUN_ID: {env.get('GITHUB_RUN_ID')}")
    if "RUNNER_AUTH_TOKEN" in env or "GH_ISSUE_TOKEN" in env:
        raise SystemExit("worker token leaked into house child env")
    if env.get("RUN_DATE") != "2026-09-30" or env.get("REFRESH_SCOPE") != "none":
        raise SystemExit(f"export_args drifted: {env.get('RUN_DATE')} {env.get('REFRESH_SCOPE')}")
    if env.get("DIGIQUANT_MODEL_TIER") != "cheap" or env.get("DIGI_CHECKPOINTER") != "postgres":
        raise SystemExit(f"pipeline file not loaded: {env.get('DIGIQUANT_MODEL_TIER')}")
    if env.get("CHEAPERINFERENCE_API_BASE") != "https://api.cheaperinference.com/v1":
        raise SystemExit(f"literal API base missing: {env.get('CHEAPERINFERENCE_API_BASE')}")
    if env.get("DIGILLM_MAX_CONCURRENT_CALLS") != "8":
        raise SystemExit("house literal caps missing")

    os.environ["CHEAPERINFERENCE_API_BASE"] = "https://override.example/v1"
    try:
        overridden = exec_job.build_child_env("house-run", run_id="run-abc", commands=commands)
    finally:
        if saved["CHEAPERINFERENCE_API_BASE"] is None:
            os.environ.pop("CHEAPERINFERENCE_API_BASE", None)
        else:
            os.environ["CHEAPERINFERENCE_API_BASE"] = saved["CHEAPERINFERENCE_API_BASE"]
    if overridden.get("CHEAPERINFERENCE_API_BASE") != "https://override.example/v1":
        raise SystemExit("non-empty worker API base must win over the literal")

    secret_names = (
        "OPENROUTER_API_KEY",
        "CHEAPERINFERENCE_API_KEY",
        "DIGIQUANT_DIGIKEY_API_KEY",
        "LANGSMITH_API_KEY",
        "CORE_POSTGRES_URI",
        "CORE_SUPABASE_URL",
        "CORE_SUPABASE_SERVICE_KEY",
        "R2_SECRET_ACCESS_KEY",
    )
    prior = {name: os.environ.get(name) for name in secret_names}
    for name in secret_names:
        os.environ[name] = "sekret"
    try:
        shadow = exec_job.build_child_env("allocation-shadow", run_id="s1", commands=commands)
    finally:
        for name, previous in prior.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
    for name in (
        "OPENROUTER_API_KEY",
        "CORE_SUPABASE_URL",
        "SUPABASE_URL",
        "LANGSMITH_API_KEY",
        "CORE_POSTGRES_URI",
        "R2_SECRET_ACCESS_KEY",
        "GITHUB_RUN_ID",
    ):
        if name in shadow:
            raise SystemExit(f"shadow child leaked {name}")

    if exec_job.interrupted_body("run-abc", "2026-09-30") != {
        "resume_run_id": "run-abc",
        "run_date": "2026-09-30",
    }:
        raise SystemExit("interrupted body drifted")
    if exec_job.interrupted_key("2026-09-30") != "pipeline-runs/house-run/2026-09-30/interrupted.json":
        raise SystemExit("interrupted key drifted")

    dry = exec_job.steps_for(
        "house-run",
        {"dry_run": "true", "run_date": "2026-09-30", "refresh_scope": "none"},
        commands,
    )
    live = exec_job.steps_for(
        "house-run",
        {"run_date": "2026-09-30", "refresh_scope": "none"},
        commands,
    )
    fed_dry = next(step for step in dry if "fedprob" in step)
    fed_live = next(step for step in live if "fedprob" in step)
    if "--dry-run" not in fed_dry or "--supabase" in fed_dry:
        raise SystemExit(f"dry_run must select fedprob --dry-run, got {fed_dry}")
    if "--supabase" not in fed_live or "--dry-run" in fed_live:
        raise SystemExit(f"empty dry_run must select fedprob --supabase, got {fed_live}")

    plans = exec_job.plans_for(
        "house-run",
        {"run_date": "2026-09-30", "refresh_scope": "none"},
        commands,
    )
    validate = next(plan for plan in plans if any(part.endswith("validate-providers.py") for part in plan.argv))
    chain = next(plan for plan in plans if any(part.endswith("house_chain_step.py") for part in plan.argv))
    if validate.step_timeout_seconds != 600 or chain.step_timeout_seconds != 13800:
        raise SystemExit(
            f"step caps drifted: validate={validate.step_timeout_seconds} chain={chain.step_timeout_seconds}"
        )
    if exec_job.step_wait_seconds(10000, 600) != 600:
        raise SystemExit("step cap must win when the job deadline is longer")
    if exec_job.step_wait_seconds(30, 600) != 30:
        raise SystemExit("remaining job deadline must win when it is shorter")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "sub"
        nested.mkdir()
        (root / "run.log").write_text("hi", encoding="utf-8")
        artifact = nested / "shadow-allocation-x.json"
        artifact.write_text(
            '{"source_workflow": "Pipeline: dashboard research"}\n',
            encoding="utf-8",
        )
        entries = exec_job._publish_entries("house-run", "run-1", [str(root)])
        keys = [key for _path, key in entries]
        if "pipeline-runs/house-run/run-1/run.log" not in keys:
            raise SystemExit(f"directory publish missed run.log: {keys}")
        if "pipeline-runs/house-run/run-1/sub/shadow-allocation-x.json" not in keys:
            raise SystemExit(f"directory publish missed nested artifact: {keys}")
        flagged = exec_job.append_shadow_flags(
            ["python", "check.py"],
            [artifact],
            source_branch="main",
        )
        if flagged[flagged.index("--artifact") + 1] != str(artifact):
            raise SystemExit(f"artifact flag drifted: {flagged}")
        if flagged[flagged.index("--source-workflow") + 1] != "Pipeline: dashboard research":
            raise SystemExit(f"producer flag drifted: {flagged}")
        if flagged[flagged.index("--source-branch") + 1] != "main":
            raise SystemExit(f"source branch flag drifted: {flagged}")
        bare = root / "shadow-allocation-bare.json"
        bare.write_text('{"schema_version": "1.0"}\n', encoding="utf-8")
        no_producer = exec_job.append_shadow_flags(["python", "check.py"], [bare])
        if "--source-workflow" in no_producer:
            raise SystemExit("missing producer must not invent a workflow name")

    source = Path(exec_job.__file__).read_text(encoding="utf-8")
    if "Pipeline: digiquant research" in source:
        raise SystemExit("exec_job must not hardcode the house workflow name")


if __name__ == "__main__":
    raise SystemExit(main())
