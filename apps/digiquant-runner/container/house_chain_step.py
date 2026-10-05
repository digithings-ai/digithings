"""Two-attempt wrapper for `python -m digiquant.portfolio.chain`.

The catalog step is this script. Flags stay the workflow's flags. This module
does not import digiquant; the child process is the chain.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

MAX_OUTER_ATTEMPTS = 2
BACKOFF_SECONDS = (0, 300)
ATTEMPT_TIMEOUT_SECONDS = 6000
SIGKILL_GRACE_SECONDS = 30

Spawn = Callable[[list[str], dict[str, str]], int]


def chain_argv(env: Mapping[str, str]) -> list[str]:
    """Argv for one daily chain attempt. Resume and dry-run are optional."""
    argv = [
        "uv",
        "run",
        "--frozen",
        "--no-sync",
        "python",
        "-m",
        "digiquant.portfolio.chain",
        "--cadence",
        "daily",
        "--run-date",
        env["RUN_DATE"],
        "--refresh-scope",
        env["REFRESH_SCOPE"],
    ]
    if env.get("DRY_RUN") == "true":
        argv.append("--dry-run")
    resume = str(env.get("RESUME_RUN_ID", "")).strip()
    if resume:
        argv.extend(["--resume-run-id", resume])
    return argv


def _signal_group(proc: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    if proc.pid is None:
        return
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def _default_spawn(argv: list[str], env: dict[str, str]) -> int:
    """Run one attempt. Tee stdout to artifacts/run.log. Kill the group at the cap."""
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    log_path = artifacts / "run.log"
    proc = subprocess.Popen(
        argv,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if proc.stdout is None:
        raise RuntimeError("chain stdout pipe missing")

    def _copy() -> None:
        assert proc.stdout is not None
        with log_path.open("ab") as log:
            while True:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                log.write(chunk)
                log.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()

    copier = threading.Thread(target=_copy, name="house-chain-log", daemon=True)
    copier.start()
    try:
        code = proc.wait(timeout=ATTEMPT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=SIGKILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _signal_group(proc, signal.SIGKILL)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        code = 124
    copier.join(timeout=5)
    return int(code)


def run_attempts(
    env: Mapping[str, str],
    spawn: Spawn | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Attempt 1 then, on non-zero, sleep 300s and attempt 2. Export DIGIQUANT_ATTEMPT."""
    runner = spawn if spawn is not None else _default_spawn
    last = 1
    base = dict(env)
    for index in range(MAX_OUTER_ATTEMPTS):
        sleep(BACKOFF_SECONDS[index])
        child = dict(base)
        child["DIGIQUANT_ATTEMPT"] = str(index + 1)
        code = int(runner(chain_argv(child), child))
        if code == 0:
            return 0
        last = code
    return last


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print(
            "house_chain_step "
            f"MAX_OUTER_ATTEMPTS={MAX_OUTER_ATTEMPTS} "
            f"BACKOFF_SECONDS={BACKOFF_SECONDS[0]},{BACKOFF_SECONDS[1]} "
            f"ATTEMPT_TIMEOUT_SECONDS={ATTEMPT_TIMEOUT_SECONDS} "
            f"SIGKILL_GRACE_SECONDS={SIGKILL_GRACE_SECONDS}"
        )
        return 0
    if args:
        raise SystemExit("usage: house_chain_step.py [--help]")
    return run_attempts(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
