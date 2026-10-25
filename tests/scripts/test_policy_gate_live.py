"""Unit tests for scripts/policy_gate_live.py (DIG-5536).

The wrapper exists because the live read needs a human-only credential and must
never sit on the PR path. Its whole value is the *honesty* of four outcomes, so
that is what these tests pin:

* no credential — exit 0 with a loud SKIPPED, and no API call attempted;
* the guard agreed — exit 0 and a citable GREEN (timestamp + host/run);
* the guard found drift — exit 1 and the guard's red output is preserved;
* the guard crashed — exit 2, never exit 1.

The last one is the regression these tests were written for. Python exits 1 on
an uncaught exception, which is the drift code, so a guard that died on an
import was reported as a policy finding until the wrapper learned to require
the guard's own verdict marker.

The end-to-end tests at the bottom run the *real* guard against a fake `gh` on
PATH. That keeps the conversation between the two scripts under test while
removing only the network: the reconciliation, the writer coupling and the red
output are all the production code.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "policy_gate_live.py"
GUARD = REPO_ROOT / "scripts" / "check_required_policy_checks.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "policy-gate-live.yml"

#: The three contexts the committed snapshot names. A "green" fake `gh` returns
#: exactly these, so the green run is the repository's own expected state.
LIVE_CONTEXTS = ["Required checks passed", "doc-links + agents-init", "mypy — digibase + digikey"]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("policy_gate_live_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pgl = _load()


class _Runner:
    """A subprocess double that records what it was asked to run."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command: list[str] = []
        self.kwargs: dict[str, Any] = {}
        self.called = False

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.called = True
        self.command = command
        self.kwargs = kwargs
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def _env(**overrides: str) -> dict[str, str]:
    """A minimal environment, so a developer's real GITHUB_* cannot leak in."""
    base = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    base.update(overrides)
    return base


def _verdict(word: str) -> str:
    return f"{pgl.GUARD_VERDICT_PREFIX} {word}\n"


# ── a skip is not a green ────────────────────────────────────────────────────


def test_a_missing_token_skips_loudly_without_running_the_guard(capsys: pytest.CaptureFixture) -> None:
    runner = _Runner(0)
    code = pgl.main([], env=_env(), runner=runner)

    captured = capsys.readouterr()
    assert code == 0
    assert not runner.called, "an absent credential must not reach the API"
    assert "SKIPPED" in captured.err
    assert "was NOT read" in captured.err
    assert "proves nothing about drift" in captured.err
    assert "::warning::" in captured.out
    assert "GREEN" not in captured.err


def test_a_whitespace_token_is_a_missing_token(capsys: pytest.CaptureFixture) -> None:
    runner = _Runner(0)
    code = pgl.main([], env=_env(POLICY_CHECK_READER_TOKEN="   "), runner=runner)

    assert code == 0
    assert not runner.called
    assert "SKIPPED" in capsys.readouterr().err


def test_the_cli_skips_on_a_host_with_no_token() -> None:
    """The same contract through the real CLI, not only through main()."""
    env = _env()
    env.pop("POLICY_CHECK_READER_TOKEN", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SKIPPED" in proc.stderr


# ── the credential is handed over without being exposed ──────────────────────


def test_a_green_run_passes_the_token_only_in_the_child_environment(
    capsys: pytest.CaptureFixture,
) -> None:
    runner = _Runner(0, stdout=_verdict("agree"))
    code = pgl.main(
        ["--repo", "digithings-ai/digithings", "--branch", "develop"],
        env=_env(GITHUB_TOKEN="checkout-token", POLICY_CHECK_READER_TOKEN="secret-value"),
        runner=runner,
    )

    assert code == 0
    assert runner.command == [
        sys.executable,
        str(GUARD),
        "--live",
        "--repo",
        "digithings-ai/digithings",
        "--branch",
        "develop",
    ]
    assert "secret-value" not in runner.command, "the token must never be an argv value"
    assert runner.kwargs["env"]["GH_TOKEN"] == "secret-value"
    assert "GITHUB_TOKEN" not in runner.kwargs["env"], (
        "two credentials in one environment is how a read becomes the wrong identity"
    )
    assert runner.kwargs["capture_output"] is True
    assert runner.kwargs["text"] is True

    captured = capsys.readouterr()
    assert f"{pgl.GUARD_VERDICT_PREFIX} agree" in captured.out, "the guard output is echoed"
    assert "GREEN at" in captured.err
    assert "secret-value" not in captured.out + captured.err


def test_the_verdict_line_carries_a_timestamp_and_the_host(
    capsys: pytest.CaptureFixture,
) -> None:
    runner = _Runner(0, stdout=_verdict("agree"))
    pgl.main([], env=_env(POLICY_CHECK_READER_TOKEN="t"), runner=runner)

    line = next(s for s in capsys.readouterr().err.splitlines() if "GREEN" in s)
    assert "GREEN at " in line
    assert "T" in line and "Z on " in line, line
    assert "digithings-ai/digithings@develop" in line


def test_inside_actions_the_identity_names_the_run(
    capsys: pytest.CaptureFixture,
) -> None:
    runner = _Runner(0, stdout=_verdict("agree"))
    pgl.main(
        [],
        env=_env(
            POLICY_CHECK_READER_TOKEN="t",
            GITHUB_RUN_ID="123456",
            GITHUB_REPOSITORY="digithings-ai/digithings",
            GITHUB_SERVER_URL="https://github.com",
        ),
        runner=runner,
    )

    err = capsys.readouterr().err
    assert "run 123456" in err
    assert "https://github.com/digithings-ai/digithings/actions/runs/123456" in err


# ── drift is red, and a crash is not drift ──────────────────────────────────


def test_drift_is_red_and_keeps_the_guards_evidence(capsys: pytest.CaptureFixture) -> None:
    runner = _Runner(
        1,
        stdout=(
            "1 policy-gate disagreement(s):\n"
            "  ::error::[policy.missing-required] mypy — digibase + digikey: is missing\n"
            + _verdict("drift")
        ),
    )
    code = pgl.run(repo="digithings-ai/digithings", branch="develop", token="t", env=_env(), runner=runner)

    captured = capsys.readouterr()
    assert code == 1
    assert "::error::[policy.missing-required]" in captured.out
    assert "DRIFT at" in captured.err


def test_a_guard_that_crashes_is_not_reported_as_drift(
    capsys: pytest.CaptureFixture,
) -> None:
    """The regression: an uncaught exception exits 1, the drift code.

    Without the verdict marker this printed `DRIFT` and exited 1, which would
    have recorded a missing Python package as a branch-protection finding.
    """
    runner = _Runner(
        1,
        stdout="",
        stderr=(
            "Traceback (most recent call last):\n"
            '  File "check_required_policy_checks.py", line 112, in <module>\n'
            "    import yaml\n"
            "ModuleNotFoundError: No module named 'yaml'\n"
        ),
    )
    code = pgl.run(repo="digithings-ai/digithings", branch="develop", token="t", env=_env(), runner=runner)

    captured = capsys.readouterr()
    assert code == 2
    assert "could not run" in captured.err
    assert "ModuleNotFoundError" in captured.err, "the cause stays visible"
    assert "DRIFT" not in captured.err


def test_exit_zero_without_a_verdict_is_not_green(capsys: pytest.CaptureFixture) -> None:
    runner = _Runner(0, stdout="something unexpected\n")
    code = pgl.run(repo="digithings-ai/digithings", branch="develop", token="t", env=_env(), runner=runner)

    assert code == 2
    assert "GREEN" not in capsys.readouterr().err


def test_drift_without_the_marker_is_not_drift(capsys: pytest.CaptureFixture) -> None:
    """Exit 1 alone is not enough: the marker is the verdict."""
    runner = _Runner(1, stdout="partial output, then died\n")
    code = pgl.run(repo="digithings-ai/digithings", branch="develop", token="t", env=_env(), runner=runner)

    assert code == 2
    assert "DRIFT" not in capsys.readouterr().err


# ── the Actions summary is where a dispatch is read ─────────────────────────


def test_the_step_summary_carries_the_verdict_identity_and_no_token(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    runner = _Runner(0, stdout=_verdict("agree"))

    pgl.main([], env=_env(POLICY_CHECK_READER_TOKEN="secret-value"), runner=runner)

    text = summary.read_text(encoding="utf-8")
    assert "policy-gate-live: GREEN" in text
    assert "on " in text and "T" in text
    assert "secret-value" not in text
    capsys.readouterr()


# ── the workflow that will carry this, pinned as a contract ─────────────────


def test_the_workflow_is_dispatch_only_and_declares_the_cron_environment() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = doc.get("on") or doc.get(True)
    assert isinstance(on, dict), "a bare trigger would make the shape unreadable"
    assert set(on) == {"workflow_dispatch"}, (
        "the live read may not ride pull_request/push (it would put a human-only "
        "credential on the merge path) and may not carry on.schedule (cost lock)"
    )
    assert "schedule" not in on

    job = doc["jobs"]["live"]
    assert job["environment"] == "cron", (
        "the PAT is environment-scoped; without this the name resolves to empty"
    )
    assert doc["permissions"] == {"contents": "read"}

    steps = job["steps"]
    run_step = next(step for step in steps if "policy_gate_live.py" in step.get("run", ""))
    assert run_step["env"]["POLICY_CHECK_READER_TOKEN"] == (
        "${{ secrets.POLICY_CHECK_READER_TOKEN }}"
    )
    assert "check_required_policy_checks.py --live" not in WORKFLOW.read_text(encoding="utf-8"), (
        "go through the wrapper: it owns the skip and the crash-vs-drift contract"
    )


# ── the guard and the wrapper, end to end, with only the network faked ─────


def _fake_gh(tmp_path: Path, contexts: list[str]) -> Path:
    """A `gh` that answers the one endpoint the guard reads.

    Only the API boundary is simulated. The guard loads the real inventory and
    snapshot, executes the real writer, reconciles, and emits the real verdict.
    """
    import json

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    payload = json.dumps({"required_status_checks": {"contexts": contexts}})
    gh.write_text(
        "#!/bin/sh\n"
        "cat <<'JSON'\n"
        f"{payload}\n"
        "JSON\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _integration_env(tmp_path: Path, contexts: list[str]) -> dict[str, str]:
    bin_dir = _fake_gh(tmp_path, contexts)
    return _env(
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        POLICY_CHECK_READER_TOKEN="simulated-token",
    )


def test_end_to_end_green_against_the_real_guard(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    pytest.importorskip("yaml")
    code = pgl.main([], env=_integration_env(tmp_path, LIVE_CONTEXTS))

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "policy-gate-verdict: agree" in captured.out
    assert "GREEN at" in captured.err


def test_end_to_end_drift_when_the_live_set_loses_a_required_context(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The DoD mutation: live is missing one snapshot context, so the gate is red.

    `mypy — digibase + digikey` is the one dropped, because it is `required` in
    the inventory; dropping an advisory context would be a different finding.
    """
    pytest.importorskip("yaml")
    mutated = [c for c in LIVE_CONTEXTS if not c.startswith("mypy")]
    code = pgl.main([], env=_integration_env(tmp_path, mutated))

    captured = capsys.readouterr()
    assert code == 1, captured.out + captured.err
    assert "policy.missing-required" in captured.out
    assert "mypy — digibase + digikey" in captured.out
    assert "policy-gate-verdict: drift" in captured.out
    assert "DRIFT at" in captured.err
    assert "GREEN" not in captured.err
