#!/usr/bin/env python3
"""Run one ``apps/digiquant-runner/commands.json`` job on this Mac (DIG-2915).

Why this exists (DIG-2915, parent DIG-2904 "Cloudflare cost minimum")

The digiquant batch cadence used to run inside the ``digiquant-runner`` container:
``digithings-cron`` POSTs ``/v1/jobs`` and the container's ``exec_job.py`` resolves the
job from ``commands.json``, runs its steps, and publishes the artifacts to R2.

This script is the same executor, on the host, under launchd. It does not carry a
second copy of the step plan: it imports the container's ``exec_job`` module and
uses ``plans_for``, ``build_child_env``, ``classify_step_exit`` and
``step_wait_seconds`` as they are. A change to a job, or to how a gate arg is read,
lands once and both executors agree. What is added here is the part the container
had from its platform and this Mac does not:

* a lock per ``concurrency`` key, so two launchd labels that share one job (the
  morning and evening market-data refreshes) cannot overlap;
* an env file outside the repository, because a launchd plist cannot hold secrets;
* a run record and a log per run, because nobody watches a launchd job's stdout;
* ``/opt/runner/*.py`` rewritten to ``apps/digiquant-runner/container/*.py``, the
  paths the house-run steps carry from the image.

What this script does not do

* It does not publish artifacts to ``pipeline-runs/<job>/<run_id>/`` unless
  ``--publish`` is passed, because ``boto3`` is not in the host environment. The
  jobs themselves still write their results to R2/D1/Supabase through the env the
  catalogue already allows; only the artifact upload is opt-in. See
  ``docs/ops/digiquant-host-runner.md``.
* It never reads secrets from the command line and never prints a value, only names.
* It does not install or load a launchd job. ``install.sh`` writes the plists and
  leaves the load to an explicit flag; loading is Chris's call.

Exit codes: 0 success, 1 the job failed, 2 usage, 74 I/O error, 75 another run holds
the lock, 78 the env file is missing, unreadable or too permissive.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import importlib.util
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_PATH = REPO_ROOT / "apps" / "digiquant-runner" / "commands.json"
CONTAINER_DIR = REPO_ROOT / "apps" / "digiquant-runner" / "container"
DEFAULT_ENV_FILE = Path.home() / ".config" / "digithings" / "digiquant-host-runner.env"
DEFAULT_STATE_DIR = Path.home() / ".config" / "digithings" / "state" / "digiquant-host-runner"
DEFAULT_LOG_DIR = Path.home() / ".config" / "digithings" / "logs" / "digiquant-host-runner"

RUNNER_IMAGE_PREFIX = "/opt/runner/"
TERM_GRACE_SECONDS = 10.0
EXIT_USAGE = 2
EXIT_IO = 74
EXIT_LOCKED = 75
EXIT_CONFIG = 78

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigError(Exception):
    """A problem the operator has to fix before a job may run."""


def _exec_job_module() -> Any:
    """Load the container's executor without installing it on ``sys.path``.

    The container module is imported by path so the Mac executor and the image run
    the same planner. Importing it has no side effects: it defines constants and
    functions only.
    """
    path = CONTAINER_DIR / "exec_job.py"
    if not path.is_file():  # pragma: no cover - the module ships with the repo
        raise ConfigError(f"no container executor at {path}")
    spec = importlib.util.spec_from_file_location("digiquant_runner_exec_job", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ConfigError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or COMMANDS_PATH
    with target.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict) or not catalog:
        raise ConfigError(f"{target} is not a non-empty job map")
    return catalog


def rewrite_argv(argv: list[str], container_dir: Path | None = None) -> list[str]:
    """Point ``/opt/runner/<file>`` at this checkout's container directory."""
    root = container_dir or CONTAINER_DIR
    out: list[str] = []
    for part in argv:
        if part.startswith(RUNNER_IMAGE_PREFIX) and len(part) > len(RUNNER_IMAGE_PREFIX):
            out.append(str(root / part[len(RUNNER_IMAGE_PREFIX) :]))
        else:
            out.append(part)
    return out


def host_plans(
    exec_job: Any,
    job: str,
    args: dict[str, str],
    *,
    catalog: dict[str, Any] | None = None,
    workdir: Path | None = None,
) -> list[Any]:
    """The container's plan for this job, with image paths made local."""
    catalog = catalog if catalog is not None else load_catalog()
    if job not in catalog:
        raise ConfigError(f"unknown job: {job} (see --list)")
    plans = exec_job.plans_for(job, args, catalog, workdir=workdir or REPO_ROOT)
    return [plan._replace(argv=rewrite_argv(list(plan.argv))) for plan in plans]


def parse_env_file(path: Path) -> dict[str, str]:
    """Read ``KEY=VALUE`` lines. Blank lines and ``#`` comments are ignored.

    Values are taken literally: no shell expansion, no ``eval``. A line that is not
    an assignment raises, because a typo must not silently drop a credential.
    """
    values: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not _ENV_NAME.match(name):
            raise ConfigError(f"{path}:{number}: not a KEY=VALUE assignment")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def check_env_file(path: Path) -> dict[str, str]:
    """Refuse a missing, unreadable or group/world-readable env file."""
    if not path.is_file():
        raise ConfigError(
            f"no env file at {path}. Create it mode 600 with the names each job needs "
            "(see docs/ops/digiquant-host-runner.md)."
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ConfigError(f"{path} is mode {mode:o}; chmod 600 it before a job may read it")
    try:
        return parse_env_file(path)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror}") from exc


def merged_environ(base: dict[str, str] | None = None) -> dict[str, str]:
    return dict(base if base is not None else os.environ)


def run_id_now() -> str:
    """A numeric, sortable run id. ``checkpoint_run_id`` exports it as GITHUB_RUN_ID."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def acquire_lock(path: Path) -> Any:
    """Take an exclusive non-blocking lock. Returns the open handle, or None if held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()} {run_id_now()}\n")
    handle.flush()
    return handle


def _kill_group(proc: subprocess.Popen[Any], sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:  # already gone
        pass
    except OSError:  # pragma: no cover - a group we may not signal
        try:
            proc.send_signal(sig)
        except OSError:
            pass


# The step group that is running right now. A launchd stop sends SIGTERM to the
# runner only; without this the ``uv`` child keeps working after the job is gone.
_CURRENT_PGID: int | None = None


def _stop_current_step(signum: int, _frame: Any) -> None:
    pgid = _CURRENT_PGID
    if pgid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            pass
    raise SystemExit(128 + signum)


def install_signal_handlers() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _stop_current_step)


def run_step(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
    limit_seconds: float,
    log: Any,
    out: Any = None,
) -> tuple[int, bool]:
    """Run one step, streaming its output to ``log`` and ``out``.

    Returns ``(exit_code, timed_out)``. The deadline kills the whole process group,
    because the first argument is ``uv`` and the work is in its grandchild; killing
    only ``uv`` would leave the job running past its deadline.
    """
    stream = out if out is not None else sys.stdout
    log.write(f"\n$ {' '.join(argv)}\n")
    log.flush()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        start_new_session=True,
    )
    finished = threading.Event()
    killed = threading.Event()

    global _CURRENT_PGID
    _CURRENT_PGID = proc.pid

    def killer() -> None:
        if limit_seconds <= 0:
            return
        if finished.wait(limit_seconds):
            return
        killed.set()
        _kill_group(proc, signal.SIGTERM)
        if finished.wait(TERM_GRACE_SECONDS):
            return
        _kill_group(proc, signal.SIGKILL)

    thread = threading.Thread(target=killer, name="step-deadline", daemon=True)
    thread.start()
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            try:
                stream.write(line)
                stream.flush()
            except (BrokenPipeError, ValueError):  # pragma: no cover - detached stdout
                pass
        code = proc.wait()
    finally:
        finished.set()
        thread.join(timeout=1.0)
        if proc.poll() is None:  # pragma: no cover - defensive
            _kill_group(proc, signal.SIGKILL)
            proc.wait()
            code = -signal.SIGKILL
        if proc.stdout is not None:
            proc.stdout.close()
        _CURRENT_PGID = None
    timed_out = killed.is_set()
    if timed_out:
        log.write(f"\n(step stopped at its {limit_seconds:.0f}s limit)\n")
        log.flush()
    return (code if code >= 0 else 128 - code), timed_out


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    staged.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(staged, path)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _missing_env(spec: dict[str, Any], environ: dict[str, str]) -> list[str]:
    return [name for name in spec.get("env") or [] if not environ.get(name)]


def execute(
    job: str,
    args: dict[str, str],
    *,
    environ: dict[str, str],
    state_dir: Path,
    log_dir: Path,
    out: Any = None,
    require_env: tuple[str, ...] = (),
    publish: bool = False,
    catalog: dict[str, Any] | None = None,
    exec_job: Any = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one job and return its record. Never raises for a job failure."""
    catalog = catalog if catalog is not None else load_catalog()
    spec = catalog.get(job)
    if spec is None:
        raise ConfigError(f"unknown job: {job} (see --list)")
    module = exec_job if exec_job is not None else _exec_job_module()
    missing_required = [name for name in require_env if not environ.get(name)]
    if missing_required:
        raise ConfigError("missing required env: " + ", ".join(missing_required))

    run_id = run_id or run_id_now()
    concurrency = str(spec.get("concurrency") or job)
    lock_path = state_dir / "locks" / f"{concurrency}.lock"
    record: dict[str, Any] = {
        "job": job,
        "run_id": run_id,
        "concurrency": concurrency,
        "host": "mac-launchd",
        "started_at": _now(),
        "finished_at": None,
        "status": "running",
        "exit_code": None,
        "reason": None,
        "log": None,
        "missing_env": _missing_env(spec, environ),
        "steps": [],
        "publish": "skipped (host runner default)",
    }
    lock = acquire_lock(lock_path)
    if lock is None:
        record.update(
            status="skipped",
            reason="already_running",
            exit_code=0,
            finished_at=_now(),
        )
        write_json_atomic(state_dir / f"{job}.json", record)
        return record
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job}-{run_id}.log"
    record["log"] = str(log_path)
    deadline = time.monotonic() + max(float(spec.get("timeout_seconds") or 0), 0.0)
    hard_failure = False
    exit_code = 0
    status = "succeeded"
    reason: str | None = None
    try:
        plans = host_plans(module, job, args, catalog=catalog)
        child_env = module.build_child_env(job, run_id=run_id, commands=catalog, environ=environ, args=args)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"{_now()} {job} run_id={run_id} steps={len(plans)}\n")
            if record["missing_env"]:
                log.write("missing env (not passed to the job): " + ", ".join(record["missing_env"]) + "\n")
            for plan in plans:
                if hard_failure and not plan.always:
                    record["steps"].append({"argv": plan.argv, "skipped": "after_hard_failure"})
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status, reason, exit_code = "timed_out", "timeout", 124
                    break
                limit = module.step_wait_seconds(remaining, plan.step_timeout_seconds)
                started = time.monotonic()
                code, timed_out = run_step(
                    plan.argv,
                    env=child_env,
                    cwd=REPO_ROOT,
                    limit_seconds=limit,
                    log=log,
                    out=out,
                )
                took = round(time.monotonic() - started, 3)
                record["steps"].append(
                    {
                        "argv": plan.argv,
                        "exit_code": code,
                        "seconds": took,
                        "continue_on_error": plan.continue_on_error,
                        "timed_out": timed_out,
                    }
                )
                if timed_out:
                    status, reason, exit_code = "timed_out", "timeout", 124
                    break
                if code != 0 and plan.continue_on_error:
                    log.write(f"\nstep exited {code} (continue_on_error)\n")
                hard_failure, exit_code = module.classify_step_exit(
                    code,
                    continue_on_error=plan.continue_on_error,
                    hard_failure=hard_failure,
                    exit_code=exit_code,
                )
                if hard_failure:
                    status = "failed"
            if publish:
                record["publish"] = _publish(module, job, run_id, spec, log)
            elif spec.get("publish") or spec.get("publish_dir") or spec.get("publish_if_present"):
                log.write("\npublish skipped: the host runner does not upload artifacts unless --publish is passed\n")
    except ConfigError:
        raise
    except Exception as exc:
        status, exit_code, reason = "failed", 1, type(exc).__name__
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\nhost runner error: " + "".join(traceback.format_exception_only(exc)))
    finally:
        record.update(
            status=status,
            exit_code=exit_code,
            reason=reason,
            finished_at=_now(),
        )
        write_json_atomic(state_dir / f"{job}.json", record)
        history = state_dir / "history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()
    return record


def _publish(module: Any, job: str, run_id: str, spec: dict[str, Any], log: Any) -> str:
    """Upload this run's artifacts through the container's own publisher.

    ``exec_job`` imports ``boto3`` lazily, so an absent ``boto3`` is a named failure
    in the record instead of an import error at startup.
    """
    try:
        paths = module._selected_publish_paths(spec)
        publish_dir = spec.get("publish_dir")
        if isinstance(publish_dir, str) and publish_dir:
            resolved = module._resolve_publish_path(publish_dir)
            if resolved.exists():
                paths.append(publish_dir)
        if not paths:
            return "nothing to publish"
        module._publish_bounded(job, run_id, paths)
        log.write(f"\npublished {len(paths)} path(s) to R2\n")
        return f"published {len(paths)} path(s)"
    except Exception as exc:
        log.write(f"\npublish failed: {type(exc).__name__}\n")
        return f"failed: {type(exc).__name__}"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_job.py",
        description="Run one digiquant-runner catalogue job on this Mac.",
    )
    parser.add_argument("job", nargs="?", help="job name from commands.json")
    parser.add_argument("--list", action="store_true", help="print the job names and exit")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    parser.add_argument("--json", action="store_true", help="print the run record as JSON")
    parser.add_argument("--arg", action="append", default=[], metavar="NAME=VALUE", help="catalogue arg")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--require-env", action="append", default=[], metavar="NAME")
    parser.add_argument("--publish", action="store_true", help="upload artifacts to R2 (needs boto3)")
    parser.add_argument("--allow-missing-env-file", action="store_true", help="--dry-run without secrets")
    return parser.parse_args(argv)


def _parse_pairs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name.strip():
            raise ConfigError(f"--arg needs NAME=VALUE, got {pair!r}")
        out[name.strip()] = value
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    install_signal_handlers()
    try:
        catalog = load_catalog()
        if args.list:
            for name in catalog:
                print(name)
            return 0
        if not args.job:
            raise ConfigError("a job name is required (--list shows them)")
        job_args = _parse_pairs(args.arg)
        if args.dry_run:
            module = _exec_job_module()
            plans = host_plans(module, args.job, job_args, catalog=catalog)
            spec = catalog[args.job]
            print(f"job: {args.job}")
            print(f"cwd: {REPO_ROOT}")
            print(f"timeout_seconds: {spec.get('timeout_seconds')}")
            print("env names: " + (", ".join(spec.get("env") or []) or "(none)"))
            for index, plan in enumerate(plans, start=1):
                flags = []
                if plan.continue_on_error:
                    flags.append("continue_on_error")
                if plan.always:
                    flags.append("always")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                print(f"{index}. {' '.join(plan.argv)}{suffix}")
            return 0
        env_file = Path(args.env_file).expanduser()
        try:
            file_env = check_env_file(env_file)
        except ConfigError:
            if not args.allow_missing_env_file:
                raise
            file_env = {}
        environ = merged_environ()
        environ.update(file_env)
        record = execute(
            args.job,
            job_args,
            environ=environ,
            state_dir=Path(args.state_dir).expanduser(),
            log_dir=Path(args.log_dir).expanduser(),
            require_env=tuple(args.require_env),
            publish=args.publish,
            catalog=catalog,
        )
    except ConfigError as exc:
        print(f"run_job.py: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"{record['status']}: {record['job']} run_id={record['run_id']} exit={record['exit_code']}")
        if record.get("reason"):
            print(f"reason: {record['reason']}")
        if record.get("log"):
            print(f"log: {record['log']}")
    if record["status"] == "succeeded":
        return 0
    if record["status"] == "skipped":
        return EXIT_LOCKED
    return 1


if __name__ == "__main__":
    sys.exit(main())
