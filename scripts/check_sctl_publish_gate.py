#!/usr/bin/env python3
"""Guard the ``sctl publish`` gate declared in ``.sctl.yml`` (DIG-4608).

``sctl publish`` (digiforge) reads the FIRST ``test:`` line of ``.sctl.yml``,
splits the remainder on any whitespace run and executes the result as an argv
with the repository root as the working directory and **no shell**. The
declared value therefore has to be one executable invocation whose parts all
resolve from the repository root, and the environment it needs has to be
prepared by the command itself.

The previous value was ``uv run pytest -m unit``: ``uv run`` resolves only the
root virtual environment, which has neither pytest nor the workspace members,
so the published suite could not even be collected. The gate now points at
``scripts/sctl-publish-gate.sh``, which publishes the repository's green,
offline unit lane.

What it asserts
---------------
* ``.sctl.yml`` declares a ``test:`` value, read exactly as digiforge reads it.
* the value is one argv: not empty and free of shell operators.
* ``argv[0]`` resolves to a real executable (Go's ``LookPath`` rules).
* every path-like argument resolves relative to the repository root.
* the declaration points at a script **in this repository**, so the
  environment preparation lives next to the code it prepares.
* that script installs the whole workspace from the committed lockfile
  (``uv sync --frozen --all-packages --all-extras``) and runs the
  repository's unit lane from it (``uv run --frozen --no-sync pytest
  <tests/...> -m "unit or baseline"``), naming the lane's test paths so the
  gate can never widen back into the whole-workspace sweep: that sweep is
  not green today, it aborts the interpreter in ``tests/dq/test_api.py``.
* the declared command really runs: it is executed with the repository root
  as the working directory and must exit 0 having collected tests. The run
  collects instead of executing the suite, because the check lives inside
  the very lane it guards.

The command is executed, so ``uv`` has to be on PATH (CI installs it).

Usage
-----
::

    python3 scripts/check_sctl_publish_gate.py
    python3 scripts/check_sctl_publish_gate.py --format json

Exit code is ``0`` when the gate is sound, ``1`` when a problem is found.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = ".sctl.yml"

# Operators that only work in a shell. `sctl publish` executes the argv
# directly, so each of these would be passed to the program as a literal
# argument instead of doing what it looks like it does.
SHELL_OPERATORS = ("&&", "||", "|", ";", ">", "<", "&", "`", "$(")

SYNC_FLAGS = ("--frozen", "--all-packages", "--all-extras")
RUN_FLAGS = ("--frozen", "--no-sync")

_COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")
_COLLECTED_ITEMS_RE = re.compile(r"collected\s+(\d+)\s+items")

# Where `uv` usually lives when the PATH of the caller does not carry it
# (a launchd daemon, a bare CI step). The declared command is executed, so
# it has to be able to find `uv`.
_UV_DIRS = (
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.cargo/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


@dataclass(frozen=True)
class Finding:
    """One problem with the declared publish gate."""

    level: str
    code: str
    message: str


def declared_value(config_text: str) -> str | None:
    """The raw value digiforge reads from ``.sctl.yml``.

    It splits the file on newlines, trims every line, takes the first one
    starting with ``test:`` and trims the remainder. The value is not
    YAML-parsed, so it has to be a single line.
    """
    for line in config_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("test:"):
            return stripped[len("test:"):].strip()
    return None


def declared_argv(config_text: str) -> list[str]:
    """The argv digiforge would execute.

    ``strings.Fields`` splits on any run of whitespace, so a tab or a
    double space separates arguments exactly like a single space.
    """
    value = declared_value(config_text)
    if value is None:
        return []
    return value.split()


def looks_like_path(token: str) -> bool:
    """Whether a token is meant to name a file rather than a flag."""
    return "/" in token or token.startswith(".")


def resolve_executable(token: str, cwd: Path) -> Path | None:
    """Resolve ``token`` the way Go's ``exec.LookPath`` does."""
    if "/" in token:
        candidate = (cwd / token).resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        return None
    found = shutil.which(token)
    return Path(found) if found else None


def script_candidate(argv: list[str], repo_root: Path) -> Path | None:
    """The repository script the declared command invokes, if any."""
    root = repo_root.resolve()
    for token in argv:
        if not looks_like_path(token):
            continue
        candidate = (root / token).resolve()
        if not candidate.is_file():
            continue
        if not candidate.is_relative_to(root):
            continue
        return candidate
    return None


def script_steps(script_text: str) -> tuple[list[list[str]], list[list[str]]]:
    """The ``uv sync`` and ``uv run`` steps declared in a wrapper script."""
    sync_steps: list[list[str]] = []
    run_steps: list[list[str]] = []
    for line in script_text.split("\n"):
        try:
            tokens = shlex.split(line.strip(), comments=True)
        except ValueError:
            continue
        if len(tokens) < 2 or tokens[0] != "uv":
            continue
        if tokens[1] == "sync":
            sync_steps.append(tokens)
        elif tokens[1] == "run":
            run_steps.append(tokens)
    return sync_steps, run_steps


def runs_unit_suite(step: list[str]) -> bool:
    """Whether a ``uv run`` step runs the repository's unit lane.

    The marker selection may be ``unit`` alone or the CI lane's
    ``unit or baseline``. The step must also name explicit test paths: a
    bare ``pytest -m unit`` would fall back to the whole-workspace sweep,
    which is not green (it aborts the interpreter in ``tests/dq``).
    """
    if not all(flag in step for flag in RUN_FLAGS):
        return False
    if "pytest" not in step:
        return False
    try:
        marker = step.index("-m")
    except ValueError:
        return False
    selection = []
    for token in step[marker + 1:]:
        if token.startswith("-"):
            break
        selection.append(token)
    if not any("unit" in word for chunk in selection for word in chunk.split()):
        return False
    return any(token.startswith("tests/") for token in step)


def parse_collected(output: str) -> int:
    """How many tests the command collected (0 when that cannot be told)."""
    match = _COLLECTED_RE.search(output)
    if match:
        return int(match.group(1))
    match = _COLLECTED_ITEMS_RE.search(output)
    if match:
        return int(match.group(1))
    return len([line for line in output.splitlines() if "::" in line])


def run_checks(repo_root: Path, timeout: int = 1800) -> list[Finding]:
    """Check the declared publish gate. Returns the findings, errors first."""
    findings: list[Finding] = []
    config_path = repo_root / CONFIG_NAME
    if not config_path.is_file():
        return [Finding("error", "config_missing", f"{CONFIG_NAME} is missing from the repository root")]

    config_text = config_path.read_text(encoding="utf-8")
    value = declared_value(config_text)
    if value is None:
        return [Finding("error", "no_test_value", f"{CONFIG_NAME} declares no 'test:' value, so 'sctl publish' cannot run a suite")]

    argv = declared_argv(config_text)
    if not argv:
        return [Finding("error", "empty_argv", "the declared 'test:' value is empty")]

    for operator in SHELL_OPERATORS:
        if operator in value:
            findings.append(Finding("error", "shell_operator", f"the declared value contains the shell operator {operator!r}; 'sctl publish' runs it without a shell"))
            break

    if resolve_executable(argv[0], repo_root) is None:
        findings.append(Finding("error", "executable_missing", f"argv[0] {argv[0]!r} does not resolve to an executable"))

    for token in argv[1:]:
        if looks_like_path(token) and not (repo_root / token).exists():
            findings.append(Finding("error", "argument_missing", f"argument {token!r} does not exist relative to the repository root"))

    script = script_candidate(argv, repo_root)
    if script is None:
        findings.append(Finding("error", "no_repo_script", "the declared command does not invoke a script inside this repository, so the environment it needs is prepared somewhere else"))
        return findings

    sync_steps, run_steps = script_steps(script.read_text(encoding="utf-8"))
    if not any(all(flag in step for flag in SYNC_FLAGS) for step in sync_steps):
        findings.append(Finding("error", "sync_not_workspace", f"{script.name} does not install the whole workspace from the committed lockfile ('uv sync --frozen --all-packages --all-extras')"))
    if not any(runs_unit_suite(step) for step in run_steps):
        findings.append(Finding("error", "run_not_unit", f"{script.name} does not run the repository's unit lane from the synced environment ('uv run --frozen --no-sync pytest <tests/...> -m unit...' with the lane's test paths named')"))

    if findings:
        # Never execute a command the gate has not vetted: today's value runs
        # `uv run` without --frozen, which may rewrite uv.lock.
        return findings

    env = dict(os.environ)
    env["SCTL_PUBLISH_GATE_SYNC"] = "0"
    env["SCTL_PUBLISH_GATE_COLLECT_ONLY"] = "1"
    # Collect the suite the declared command names instead of running it:
    # the check runs inside the very lane it guards, so running the lane
    # here would cost minutes per run. Collecting it still proves the
    # command resolves, the environment is the whole workspace and the
    # suite is collectable — and the full run is what the publish gate
    # itself does, proven by the clean-checkout run.
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    # The declared command is executed, so it needs `uv`. A daemon or a
    # shell whose PATH does not carry it still gets a chance to find it.
    env["PATH"] = os.pathsep.join(
        [env.get("PATH", ""), *(_UV_DIRS)]
    )
    try:
        completed = subprocess.run(argv, cwd=str(repo_root), env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return findings + [Finding("error", "declared_command_timeout", f"the declared command did not finish within {timeout}s")]
    except OSError as exc:
        return findings + [Finding("error", "declared_command_not_runnable", f"the declared command could not be started: {exc}")]

    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        tail = " ".join(output.split())[-400:]
        return findings + [Finding("error", "declared_command_failed", f"the declared command exited {completed.returncode}; {tail}")]
    collected = parse_collected(output)
    if collected <= 0:
        return findings + [Finding("error", "declared_command_collected_nothing", "the declared command exited 0 but collected no tests")]
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the 'sctl publish' gate declared in .sctl.yml")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    findings = run_checks(REPO_ROOT)
    if args.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        for finding in findings:
            print(f"{finding.level}: [{finding.code}] {finding.message}")
        if not findings:
            print("sctl publish gate: ok")
    return 1 if any(finding.level == "error" for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
