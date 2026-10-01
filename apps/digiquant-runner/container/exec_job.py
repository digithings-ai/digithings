"""Allowlisted argv runner for the digiquant-runner container (issue #4761).

`serve` binds 0.0.0.0:8080 inside the container. Child processes receive only
the command's env allowlist plus a small interpreter baseline (PATH and
friends). RUNNER_AUTH_TOKEN stays on the Worker. The runner does not file
GitHub issues; a leftover GH_ISSUE_TOKEN is stripped and never required.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, NamedTuple

COMMANDS_PATH = Path("/opt/runner/commands.json")
STATUS_DIR = Path("/tmp/runner")
WORKDIR = Path(os.environ.get("RUNNER_WORKDIR", "/app"))
HOST = "0.0.0.0"
PORT = 8080
LOG_TAIL_LINES = 200
# Artifact upload is outside the step deadline; bound it so status clears and
# a twin /run cannot be blocked forever by a hung boto3 call.
PUBLISH_TIMEOUT_SECONDS = 120

# Interpreter baseline. The full process environ is never copied: that would
# leak Worker-only tokens into the pipeline child.
_BASELINE_ENV = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "TMPDIR",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "VIRTUAL_ENV",
    "UV_PROJECT_ENVIRONMENT",
    "UV_CACHE_DIR",
)
_FORBIDDEN_ENV = frozenset({"RUNNER_AUTH_TOKEN", "GH_ISSUE_TOKEN"})

_lock = threading.Lock()
_current: dict[str, str | int] = {
    "run_id": "",
    "pgid": 0,
    "command": "",
    "run_date": "",
}


def commands_file() -> Path:
    override = os.environ.get("RUNNER_COMMANDS", "").strip()
    if override:
        return Path(override)
    if COMMANDS_PATH.is_file():
        return COMMANDS_PATH
    return Path(__file__).resolve().parents[1] / "commands.json"


def load_commands(path: Path | None = None) -> dict[str, Any]:
    raw = json.loads((path or commands_file()).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("commands.json must be an object")
    return raw


def git_sha() -> str:
    value = os.environ.get("DIGIQUANT_RUNNER_GIT_SHA", "").strip()
    return value or "unknown"


class StepPlan(NamedTuple):
    argv: list[str]
    continue_on_error: bool = False
    always: bool = False
    step_timeout_seconds: int | None = None


def _utc_today(today: str | None) -> str:
    if today:
        return today
    return datetime.now(timezone.utc).date().isoformat()


def _arg_value(provided: dict[str, str], name: str) -> str:
    return str(provided.get(name, "")).strip()


def _resolve_step(
    step: Any,
    provided: dict[str, str],
    *,
    today: str,
    workdir: Path,
) -> StepPlan | None:
    if isinstance(step, list):
        return StepPlan([str(part) for part in step])
    argv = [str(part) for part in step["argv"]]
    when_arg = step.get("when_arg")
    if when_arg is not None and provided.get(str(when_arg)) != step.get("equals"):
        return None
    empty_key = step.get("when_arg_empty")
    if empty_key is not None and _arg_value(provided, str(empty_key)):
        return None
    set_key = step.get("when_arg_set")
    if set_key is not None and not _arg_value(provided, str(set_key)):
        return None
    when_file = step.get("when_file")
    if when_file is not None and not (workdir / str(when_file)).is_file():
        return None
    append = step.get("append_arg")
    if append is not None:
        argv.append(_arg_value(provided, str(append)))
    if step.get("append_utc_date"):
        argv.append(today)
    cap_raw = step.get("step_timeout_seconds")
    cap = cap_raw if isinstance(cap_raw, int) and cap_raw > 0 else None
    return StepPlan(
        argv,
        continue_on_error=bool(step.get("continue_on_error")),
        always=bool(step.get("always")),
        step_timeout_seconds=cap,
    )


def plans_for(
    command: str,
    args: dict[str, str] | None = None,
    commands: dict[str, Any] | None = None,
    *,
    today: str | None = None,
    workdir: Path | None = None,
) -> list[StepPlan]:
    """Selected steps for this kick, including continue/always flags."""
    catalog = commands if commands is not None else load_commands()
    spec = catalog.get(command)
    if spec is None:
        raise SystemExit(f"unknown command: {command}")
    provided = args or {}
    stamp = _utc_today(today)
    root = workdir if workdir is not None else WORKDIR
    selected: list[StepPlan] = []
    for step in spec.get("steps", []):
        plan = _resolve_step(step, provided, today=stamp, workdir=root)
        if plan is not None:
            selected.append(plan)
    return selected


def steps_for(
    command: str,
    args: dict[str, str] | None = None,
    commands: dict[str, Any] | None = None,
    *,
    today: str | None = None,
    workdir: Path | None = None,
) -> list[list[str]]:
    """Argv lists for this kick. Gated steps run only when their predicate matches."""
    return [plan.argv for plan in plans_for(command, args, commands, today=today, workdir=workdir)]


def classify_step_exit(
    code: int,
    *,
    continue_on_error: bool,
    hard_failure: bool,
    exit_code: int,
) -> tuple[bool, int]:
    """Return (hard_failure, exit_code) after one step.

    continue_on_error does not fail the job. The first hard failure's exit
    code sticks when a later step also fails.
    """
    if code == 0 or continue_on_error:
        return hard_failure, exit_code
    if hard_failure:
        return True, exit_code
    return True, code


def _yaml_scalar(raw: str) -> str:
    if not raw:
        return ""
    if raw[0] in {'"', "'"}:
        quote = raw[0]
        end = raw.find(quote, 1)
        if end != -1:
            return raw[1:end]
        return raw.strip(quote)
    if " #" in raw:
        raw = raw.split(" #", 1)[0]
    return raw.strip()


def load_pipeline_env(text: str) -> dict[str, str]:
    """Parse the `env:` map. Stdlib only — the unit test stays PyYAML-free."""
    out: dict[str, str] = {}
    in_env = False
    for line in text.splitlines():
        if not in_env:
            if line.strip() == "env:":
                in_env = True
            continue
        if not line.strip():
            continue
        if line[:1] not in (" ", "\t"):
            break
        stripped = line.strip()
        if stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, raw = stripped.partition(":")
        key = key.strip()
        if not key:
            continue
        out[key] = _yaml_scalar(raw.strip())
    return out


def _pipeline_env_for(spec: dict[str, Any], workdir: Path | None = None) -> dict[str, str]:
    rel = spec.get("pipeline_env")
    if not isinstance(rel, str) or not rel.strip():
        return {}
    roots = [workdir or WORKDIR, Path(__file__).resolve().parents[3]]
    for root in roots:
        path = root / rel
        if path.is_file():
            return load_pipeline_env(path.read_text(encoding="utf-8"))
    return {}


def step_wait_seconds(remaining: float, step_timeout_seconds: int | None) -> float:
    """Cap one step at min(step timeout, remaining job deadline)."""
    if step_timeout_seconds is None:
        return remaining
    return min(float(step_timeout_seconds), remaining)


def build_child_env(
    command: str,
    *,
    run_id: str,
    commands: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    args: dict[str, str] | None = None,
) -> dict[str, str]:
    """Env for one command. Never includes Worker auth tokens.

    Literals (`extra_env`, pipeline file) fill first. A non-empty allowlisted
    Worker value wins, so a secret API base overrides the catalog literal.
    """
    catalog = commands if commands is not None else load_commands()
    spec = catalog.get(command)
    if spec is None:
        raise SystemExit(f"unknown command: {command}")
    source = environ if environ is not None else dict(os.environ)
    child: dict[str, str] = {}
    for name in _BASELINE_ENV:
        value = source.get(name, "")
        if value and name not in _FORBIDDEN_ENV:
            child[name] = value
    for name, value in (spec.get("extra_env") or {}).items():
        if name in _FORBIDDEN_ENV or not isinstance(value, str) or not value:
            continue
        child[str(name)] = value
    for name, value in _pipeline_env_for(spec).items():
        if name in _FORBIDDEN_ENV or not value:
            continue
        child[name] = value
    for name in spec.get("env", []):
        if name in _FORBIDDEN_ENV:
            continue
        value = source.get(name, "")
        if value:
            child[name] = value
    if spec.get("alias_supabase"):
        core_url = source.get("CORE_SUPABASE_URL", "")
        core_key = source.get("CORE_SUPABASE_SERVICE_KEY", "")
        if core_url:
            child["SUPABASE_URL"] = core_url
        if core_key:
            child["SUPABASE_SERVICE_ROLE_KEY"] = core_key
    if spec.get("market_backend") == "r2":
        child["DIGIQUANT_MARKET_DATA_BACKEND"] = "r2"
    provided = args or {}
    for arg_name in spec.get("export_args") or []:
        exported = str(arg_name).upper()
        if exported in _FORBIDDEN_ENV:
            continue
        value = str(provided.get(str(arg_name), "")).strip()
        if value:
            child[exported] = value
    if spec.get("checkpoint_run_id"):
        child["GITHUB_RUN_ID"] = run_id
    child["RUN_ID"] = run_id
    child.pop("RUNNER_AUTH_TOKEN", None)
    child.pop("GH_ISSUE_TOKEN", None)
    return child


def interrupted_body(run_id: str, run_date: str) -> dict[str, str]:
    return {"resume_run_id": run_id, "run_date": run_date}


def interrupted_key(run_date: str) -> str:
    return f"pipeline-runs/house-run/{run_date}/interrupted.json"


_PRODUCER_KEYS = ("source_workflow", "producer_workflow", "producer", "workflow")


def producer_name(payload: dict[str, Any]) -> str | None:
    """Workflow name carried on the artifact, when the JSON has one."""
    for key in _PRODUCER_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def append_shadow_flags(
    argv: list[str],
    artifact_paths: list[Path],
    *,
    source_branch: str = "",
) -> list[str]:
    """Append local artifact paths. --source-workflow only if the JSON names one."""
    out = list(argv)
    producer: str | None = None
    for path in artifact_paths:
        out.extend(["--artifact", str(path)])
        if producer is not None or not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            producer = producer_name(loaded)
    if producer:
        out.extend(["--source-workflow", producer])
    branch = source_branch.strip()
    if branch:
        out.extend(["--source-branch", branch])
    return out


def _r2_client() -> tuple[Any, str] | None:
    account = os.environ.get("R2_ACCOUNT_ID", "").strip()
    bucket = os.environ.get("R2_BUCKET", "").strip()
    access = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    if not (account and bucket and access and secret):
        return None
    import boto3  # deferred — same pattern as digiquant.ops.checkpoint_archive

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=access,
        aws_secret_access_key=secret,
    )
    return client, bucket


def _require_r2() -> tuple[Any, str]:
    found = _r2_client()
    if found is None:
        raise RuntimeError("missing R2 credentials for publish")
    return found


def _put_r2_bytes(key: str, body: bytes) -> None:
    client, bucket = _require_r2()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def upload_interrupted(run_id: str, run_date: str) -> None:
    if not run_date:
        return
    payload = json.dumps(interrupted_body(run_id, run_date)).encode("utf-8")
    _put_r2_bytes(interrupted_key(run_date), payload)


def _upload_interrupted_best_effort(run_id: str, run_date: str) -> None:
    if not run_id or not run_date:
        return
    errors: list[BaseException] = []

    def _target() -> None:
        try:
            upload_interrupted(run_id, run_date)
        except BaseException as exc:  # noqa: BLE001 — best-effort; still exit 143
            errors.append(exc)

    thread = threading.Thread(target=_target, name="interrupted-upload", daemon=True)
    thread.start()
    thread.join(10)
    if errors:
        sys.stderr.write(
            "digiquant-runner interrupted upload failed: "
            f"{type(errors[0]).__name__}\n"
        )


def _read_interrupted_resume(run_date: str) -> str | None:
    if not run_date:
        return None
    found = _r2_client()
    if found is None:
        return None
    client, bucket = found
    try:
        obj = client.get_object(Bucket=bucket, Key=interrupted_key(run_date))
        raw = obj["Body"].read()
    except Exception:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    resume = payload.get("resume_run_id")
    if isinstance(resume, str) and resume.strip():
        return resume.strip()
    return None


def _list_prefix_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents") or []:
            key = item.get("Key")
            if isinstance(key, str):
                keys.append(key)
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token:
            break
    return keys


def stage_shadow_prefix(prefix: str, dest: Path) -> list[Path]:
    """Download shadow-allocation JSON into dest. Parent process only."""
    client, bucket = _require_r2()
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for key in _list_prefix_keys(client, bucket, prefix):
        name = Path(key).name
        if not (name.startswith("shadow-allocation-") and name.endswith(".json")):
            continue
        target = dest / name
        client.download_file(bucket, key, str(target))
        paths.append(target)
    paths.sort()
    return paths


def _prepare_shadow_plans(
    run_id: str,
    args: dict[str, str],
    spec: dict[str, Any],
    plans: list[StepPlan],
) -> list[StepPlan]:
    prefix_arg = spec.get("stage_r2_prefix_arg")
    if not isinstance(prefix_arg, str) or not prefix_arg or not plans:
        return plans
    prefix = str(args.get(prefix_arg, "")).strip()
    if not prefix:
        return plans
    if "/" in run_id or run_id.startswith("."):
        raise RuntimeError("invalid run_id")
    staged = stage_shadow_prefix(prefix, Path("/tmp/shadow-in") / run_id)
    first = plans[0]
    flagged = append_shadow_flags(
        first.argv,
        staged,
        source_branch=str(args.get("source_branch", "")),
    )
    updated = list(plans)
    updated[0] = first._replace(argv=flagged)
    return updated


def _apply_resume(spec: dict[str, Any], args: dict[str, str], child_env: dict[str, str]) -> None:
    export_args = spec.get("export_args") or []
    if "resume_run_id" not in export_args or child_env.get("RESUME_RUN_ID"):
        return
    resumed = _read_interrupted_resume(str(args.get("run_date", "")).strip())
    if resumed:
        child_env["RESUME_RUN_ID"] = resumed


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_path(run_id: str) -> Path:
    return STATUS_DIR / f"{run_id}.log"


def _status_path(run_id: str) -> Path:
    return STATUS_DIR / f"{run_id}.status.json"


def _tail(path: Path, lines: int = LOG_TAIL_LINES) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def _write_status(run_id: str, payload: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["log_tail"] = _tail(_log_path(run_id))
    path = _status_path(run_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _read_status(run_id: str) -> dict[str, Any] | None:
    path = _status_path(run_id)
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    loaded["log_tail"] = _tail(_log_path(run_id))
    return loaded


def _running_command(command: str) -> str | None:
    """Return the run_id of an in-progress job for ``command``, else None.

    The Durable Object is the primary concurrency ledger, but a premature
    watchdog timeout can release that lock while this container is still
    writing. Refusing a twin ``/run`` for the same command prevents two
    ``market-data-refresh`` (or similar) processes from racing the same R2
    generation keys.
    """
    if not STATUS_DIR.is_dir():
        return None
    for path in STATUS_DIR.glob("*.status.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("status") != "running":
            continue
        if payload.get("command") != command:
            continue
        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id:
            return run_id
    return None


def _wait_argv(
    argv: list[str],
    child_env: dict[str, str],
    log: Any,
    timeout: float,
) -> tuple[int, bool]:
    """Run one argv. The bool is true when the step hit the deadline."""
    proc = subprocess.Popen(
        argv,
        cwd=str(WORKDIR),
        env=child_env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with _lock:
        _current["pgid"] = proc.pid or 0
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        return 124, True
    finally:
        with _lock:
            _current["pgid"] = 0
    return int(code), False


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.pid is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _resolve_publish_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return WORKDIR / path


def publish_paths_present(paths: list[str], exists: Callable[[str], bool]) -> list[str]:
    """Keep publish_if_present paths the caller says exist. Missing paths are skipped."""
    return [path for path in paths if exists(path)]


def raise_if_required_missing(path: str) -> None:
    """Required publish entries fail when the path is not a file."""
    if not Path(path).is_file():
        raise RuntimeError(f"publish file missing: {path}")


def _selected_publish_paths(spec: dict[str, Any]) -> list[str]:
    """Required paths stay. Optional paths stay only when the file exists."""
    required = [str(path) for path in (spec.get("publish") or [])]
    raw_optional = spec.get("publish_if_present") or []
    optional: list[str] = []
    if isinstance(raw_optional, list):
        optional = publish_paths_present(
            [str(path) for path in raw_optional],
            exists=lambda raw: _resolve_publish_path(raw).is_file(),
        )
    return required + optional


def _publish_entries(command: str, run_id: str, paths: list[str]) -> list[tuple[Path, str]]:
    """File keys keep the basename. A directory uses paths relative to that root."""
    entries: list[tuple[Path, str]] = []
    for raw_path in paths:
        path = _resolve_publish_path(raw_path)
        if path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
            if not files:
                raise RuntimeError(f"publish directory empty: {path}")
            for file in files:
                rel = file.relative_to(path).as_posix()
                entries.append((file, f"pipeline-runs/{command}/{run_id}/{rel}"))
            continue
        entries.append((path, f"pipeline-runs/{command}/{run_id}/{path.name}"))
    return entries


def _publish(command: str, run_id: str, paths: list[str]) -> None:
    """Upload step outputs to R2. boto3 stays inside _r2_client so unit tests are stdlib-only."""
    client, bucket = _require_r2()
    for path, key in _publish_entries(command, run_id, paths):
        raise_if_required_missing(str(path))
        client.upload_file(str(path), bucket, key)


def _publish_bounded(command: str, run_id: str, paths: list[str]) -> None:
    """Run ``_publish`` with a hard wall clock so status cannot stick on running."""
    errors: list[BaseException] = []

    def _target() -> None:
        try:
            _publish(command, run_id, paths)
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            errors.append(exc)

    thread = threading.Thread(target=_target, name=f"publish-{run_id}", daemon=True)
    thread.start()
    thread.join(PUBLISH_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise TimeoutError(f"publish exceeded {PUBLISH_TIMEOUT_SECONDS}s")
    if errors:
        raise errors[0]


def _run_steps(run_id: str, command: str, args: dict[str, str], timeout_seconds: int) -> None:
    spec = load_commands()[command]
    log_path = _log_path(run_id)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    started = _now()
    status: dict[str, Any] = {
        "run_id": run_id,
        "command": command,
        "status": "running",
        "exit_code": None,
        "started_at": started,
        "finished_at": None,
        "git_sha": git_sha(),
        "reason": None,
    }
    _write_status(run_id, status)
    try:
        plans = _prepare_shadow_plans(run_id, args, spec, plans_for(command, args))
    except Exception as exc:  # stage failure fails the run; do not leak secrets
        status["status"] = "failed"
        status["exit_code"] = 1
        status["finished_at"] = _now()
        status["reason"] = type(exc).__name__
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\nstage failed: {type(exc).__name__}\n")
        _write_status(run_id, status)
        _clear_current(run_id)
        return
    child_env = build_child_env(command, run_id=run_id, args=args)
    _apply_resume(spec, args, child_env)
    deadline = time.monotonic() + max(timeout_seconds, 0)
    exit_code = 0
    reason: str | None = None
    outcome = "succeeded"
    hard_failure = False
    with log_path.open("ab") as log:
        for plan in plans:
            if hard_failure and not plan.always:
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome = "timed_out"
                reason = "timeout"
                exit_code = 124
                break
            limit = step_wait_seconds(remaining, plan.step_timeout_seconds)
            code, timed_out = _wait_argv(plan.argv, child_env, log, limit)
            if timed_out:
                outcome = "timed_out"
                reason = "timeout"
                exit_code = 124
                break
            if code != 0 and plan.continue_on_error:
                log.write(f"\nstep exited {code} (continue_on_error)\n".encode())
            hard_failure, exit_code = classify_step_exit(
                code,
                continue_on_error=plan.continue_on_error,
                hard_failure=hard_failure,
                exit_code=exit_code,
            )
            if hard_failure:
                outcome = "failed"
    publish_paths = _selected_publish_paths(spec)
    publish_dir = spec.get("publish_dir")
    if isinstance(publish_dir, str) and publish_dir:
        resolved = _resolve_publish_path(publish_dir)
        if outcome == "succeeded" or resolved.exists():
            publish_paths.append(publish_dir)
    always_publish = bool(spec.get("publish_always"))
    if always_publish:
        should_publish = outcome in {"succeeded", "failed", "timed_out"} and bool(publish_paths)
    else:
        should_publish = outcome == "succeeded" and bool(publish_paths)
    if should_publish:
        try:
            _publish_bounded(command, run_id, publish_paths)
        except Exception as exc:  # publish failure fails the run; do not leak secrets
            outcome = "failed"
            exit_code = 1
            reason = type(exc).__name__
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\npublish failed: {type(exc).__name__}\n")
    status["status"] = outcome
    status["exit_code"] = exit_code
    status["finished_at"] = _now()
    status["reason"] = reason
    _write_status(run_id, status)
    _clear_current(run_id)


def _clear_current(run_id: str) -> None:
    with _lock:
        if _current.get("run_id") == run_id:
            _current["run_id"] = ""
            _current["command"] = ""
            _current["run_date"] = ""


def _on_sigterm(signum: int, _frame: object) -> None:
    del signum
    with _lock:
        run_id = str(_current.get("run_id") or "")
        pgid = int(_current.get("pgid") or 0)
        command = str(_current.get("command") or "")
        run_date = str(_current.get("run_date") or "")
    if run_id:
        existing = _read_status(run_id) or {
            "run_id": run_id,
            "status": "failed",
            "exit_code": None,
            "started_at": None,
            "finished_at": None,
            "git_sha": git_sha(),
        }
        existing["status"] = "failed"
        existing["reason"] = "sigterm"
        existing["finished_at"] = _now()
        _write_status(run_id, existing)
    if command == "house-run":
        _upload_interrupted_best_effort(run_id, run_date)
    if pgid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    raise SystemExit(143)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("digiquant-runner %s\n" % (fmt % args))

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            running: list[str] = []
            if STATUS_DIR.is_dir():
                for path in STATUS_DIR.glob("*.status.json"):
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict) and payload.get("status") == "running":
                        run_id = payload.get("run_id")
                        if isinstance(run_id, str):
                            running.append(run_id)
            self._json(
                200,
                {
                    "ok": True,
                    "service": "digiquant-runner",
                    "git_sha": git_sha(),
                    "running": running,
                },
            )
            return
        if parsed.path == "/status":
            query = urllib.parse.parse_qs(parsed.query)
            run_id = (query.get("run_id") or [""])[0]
            if not run_id:
                self._json(400, {"error": "run_id_required"})
                return
            payload = _read_status(run_id)
            if payload is None:
                self._json(404, {"error": "not_found"})
                return
            self._json(200, payload)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/run":
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("content-length") or "0")
        if length <= 0 or length > 1_000_000:
            self._json(400, {"error": "invalid_body"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "invalid_json"})
            return
        run_id = body.get("run_id")
        command = body.get("command")
        args = body.get("args") or {}
        timeout = body.get("timeout_seconds")
        if not isinstance(run_id, str) or not isinstance(command, str):
            self._json(400, {"error": "invalid_body"})
            return
        if not isinstance(args, dict) or not isinstance(timeout, int):
            self._json(400, {"error": "invalid_body"})
            return
        try:
            steps_for(command, {str(k): str(v) for k, v in args.items()})
        except SystemExit:
            self._json(400, {"error": "unknown command"})
            return
        string_args = {str(k): str(v) for k, v in args.items()}
        with _lock:
            busy = _running_command(command)
            if busy:
                self._json(409, {"error": "already_running", "run_id": busy})
                return
            # Reserve the command slot before the thread starts so a twin
            # POST cannot slip through between check and first status write.
            _write_status(
                run_id,
                {
                    "run_id": run_id,
                    "command": command,
                    "status": "running",
                    "exit_code": None,
                    "started_at": _now(),
                    "finished_at": None,
                    "git_sha": git_sha(),
                    "reason": None,
                },
            )
            _current["run_id"] = run_id
            _current["command"] = command
            _current["run_date"] = string_args.get("run_date", "")
        thread = threading.Thread(
            target=_run_steps,
            args=(run_id, command, string_args, timeout),
            name=f"run-{run_id}",
            daemon=False,
        )
        thread.start()
        self._json(202, {"ok": True, "run_id": run_id})


def serve() -> None:
    signal.signal(signal.SIGTERM, _on_sigterm)
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["serve"]:
        serve()
        return
    raise SystemExit("usage: exec_job.py serve")


if __name__ == "__main__":
    main()
