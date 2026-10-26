"""The deploy step retries a Cloudflare API timeout, and nothing else.

WHY THIS IS A TEST AND NOT A COMMENT. The retry exists because run 39488465235
(main, 2026-10-20 20:01Z) failed with `Error modifying application
"digithings-stack-digistackcontainer": Request timeout` AFTER the image had
built and pushed, and the next promotion 14 minutes later was green. The narrow
part is the point: an auth failure (wranger code 10000), a config error or a
build failure must still fail on the FIRST attempt with its own log, because
retrying those delays the diagnosis and can hide a broken credential behind
three identical errors.

So these tests run the REAL `run:` block from
`.github/workflows/deploy-digithings-stack-cloudflare.yml` against a stub `npm`
and a stub `sleep`:

- a timeout then a success  -> exit 0, two attempts, one 20s pause;
- three timeouts            -> exit 1, three attempts, the last log kept;
- an auth error             -> exit 1 on the first attempt, no pause;
- a non-timeout error        -> exit 1 on the first attempt, no pause.

The stub `sleep` keeps the suite at milliseconds: the step's real pauses are 20s
and 60s, and a test that waited them out would be a 80-second test that nobody
runs.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-digithings-stack-cloudflare.yml"
STEP_NAME = "Deploy stack container"

TIMEOUT_LOG = (
    'Error modifying application "digithings-stack-digistackcontainer": Request timeout\n'
    "npm error Lifecycle script `deploy` failed with error:\n"
    "npm error code 1\n"
)
AUTH_LOG = (
    "✘ [ERROR] A request to the Cloudflare API failed.\n"
    "  Authentication error [code: 10000]\n"
    "npm error code 1\n"
)
CONFIG_LOG = (
    "Error: Cannot find module '/repo/apps/digithings-stack-cloudflare/scripts/deploy.mjs'\n"
)


def _deploy_step() -> dict[str, Any]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["deploy"]["steps"]
    for step in steps:
        if step.get("name") == STEP_NAME:
            assert "run" in step, f"the `{STEP_NAME}` step is no longer a script: {step}"
            return step
    raise AssertionError(f"no step named `{STEP_NAME}` in the deploy job — update this test")


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def run_step(tmp_path: Path):
    """Run the lane's deploy script; return (exit code, output, npm call count, pauses)."""

    def _run(
        log: str, *, exit_code: int = 1, succeed_on: int = 99
    ) -> tuple[int, str, int, list[str]]:
        stub_dir = tmp_path / "stub"
        stub_dir.mkdir(exist_ok=True)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        (tmp_path / "runner").mkdir(exist_ok=True)

        # One output for every failing attempt; `succeed_on` is the attempt that
        # exits 0 instead, so a transient failure is followed by a green retry.
        _stub(
            bin_dir,
            "npm",
            'count=$(( $(cat "$STUB_DIR/count" 2>/dev/null || echo 0) + 1 ))\n'
            'printf "%s\\n" "$count" > "$STUB_DIR/count"\n'
            'if [ "$count" -ge "${STUB_SUCCEED_ON:-99}" ]; then\n'
            '  echo "deployed on attempt $count"\n'
            "  exit 0\n"
            "fi\n"
            'printf "%s" "$STUB_OUTPUT" >&2\n'
            'exit "${STUB_EXIT:-1}"\n',
        )
        _stub(bin_dir, "sleep", 'printf "%s\\n" "$1" >> "$STUB_DIR/slept"\n')

        environment = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "RUNNER_TEMP": str(tmp_path / "runner"),
            "STUB_DIR": str(stub_dir),
            "STUB_OUTPUT": log,
            "STUB_EXIT": str(exit_code),
            "STUB_SUCCEED_ON": str(succeed_on),
        }
        result = subprocess.run(
            ["/bin/bash", "-c", _deploy_step()["run"]],
            capture_output=True,
            text=True,
            env=environment,
            timeout=60,
        )
        calls = (
            int((stub_dir / "count").read_text().strip()) if (stub_dir / "count").exists() else 0
        )
        slept = (stub_dir / "slept").read_text().split() if (stub_dir / "slept").exists() else []
        return result.returncode, result.stdout + result.stderr, calls, slept

    return _run


def test_a_timeout_is_retried_once_and_the_retry_converges(run_step) -> None:
    code, out, calls, slept = run_step(TIMEOUT_LOG, succeed_on=2)
    assert code == 0, out
    assert calls == 2, f"a timeout must be retried, and only once here: {out}"
    assert slept == ["20"], f"the first pause is 20s: {slept}\n{out}"
    assert "retrying in 20s" in out, out


def test_three_timeouts_fail_with_the_last_log_and_the_attempt_count(run_step) -> None:
    code, out, calls, slept = run_step(TIMEOUT_LOG)
    assert code != 0, out
    assert calls == 3, f"at most 3 attempts: {out}"
    assert slept == ["20", "60"], f"20s then 60s, and nothing after the last attempt: {slept}"
    assert "on all 3 attempts" in out, out
    # The log of the failing attempt is reproduced, so the step is diagnosable.
    assert "Request timeout" in out, out


def test_an_auth_error_is_not_retried(run_step) -> None:
    code, out, calls, slept = run_step(AUTH_LOG)
    assert code != 0, out
    assert calls == 1, f"an auth failure must exit on the first attempt: {out}"
    assert slept == [], f"nothing may sleep before an auth failure is reported: {slept}"
    assert "authentication error" in out.lower(), out
    assert "Not retrying" in out, out


def test_an_auth_error_that_also_says_timeout_is_not_retried(run_step) -> None:
    """The fatal check runs FIRST, so a log carrying both is never retried.

    This is the case that makes the two regexes safe together: wrangler prints
    its API wrapper line and whatever the request did, so a bad credential can
    land in a log that also mentions a timeout. Order of the two greps is the
    whole property, and a test on the auth log alone cannot see it - it would
    pass through the non-timeout branch even if the fatal branch were deleted.
    """
    mixed = AUTH_LOG + TIMEOUT_LOG
    code, out, calls, slept = run_step(mixed)
    assert code != 0, out
    assert calls == 1, f"an auth failure must not be retried even beside a timeout: {out}"
    assert slept == [], f"no pause may happen before an auth failure is reported: {slept}"
    assert "authentication error" in out.lower(), out


def test_a_non_timeout_error_is_not_retried(run_step) -> None:
    code, out, calls, slept = run_step(CONFIG_LOG)
    assert code != 0, out
    assert calls == 1, f"a config error must exit on the first attempt: {out}"
    assert slept == [], f"nothing may sleep before a config error is reported: {slept}"
    assert "non-timeout error" in out, out


def test_the_step_keeps_pipefail_and_a_captured_log(run_step) -> None:
    """`tee` must not mask a failing deploy, and the log must be a file, not a rerun."""
    script = _deploy_step()["run"]
    assert "set -euo pipefail" in script, "`tee` would mask a failing `npm run deploy`"
    assert 'log="$RUNNER_TEMP/' in script, "the signature is matched from a captured log"
    assert 'tee "$log"' in script, script
    # And the script is valid bash: a syntax error would only show up in production.
    check = subprocess.run(["/bin/bash", "-n"], input=script, capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
