"""DIG-42: the example-credential guard must run on every pull request.

`scripts/check_example_credentials.py` reached `develop` in PR #5030, and as of
`ed210dc4c` no workflow invokes it: a search across `.github/workflows/*.yml`,
`*.yaml`, every Makefile and every Python file finds no reference to it outside the
script itself. The guard therefore ran only when a human remembered to run it, and a
real credential value committed into a tracked `.example` file passed CI silently.

These tests pin two things.

* `.github/workflows/ci.yml` runs the guard, unconditionally, and inside the
  required-checks aggregate.
* The guard's own verdict is safe to publish — it names the file and the variable and
  never the value — and it fails on a non-zero exit. A guard that prints `ERROR` and
  exits 0 is worse than no guard, because it looks like a check.

The unconditional part is not a preference. `check_example_credentials.py` enumerates
with `git ls-files` and scans every tracked `.example` / `.template` file regardless of
the diff, exactly like `check_frontend_canon.py`; the comment above the `frontend-canon`
job in ci.yml (lines 225-239) already records why gating such a job on a path filter is
structurally wrong rather than merely incomplete.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GUARD = "scripts/check_example_credentials.py"
RUN = f"python3 {GUARD}"


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_under_test", REPO_ROOT / GUARD
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _guard_jobs() -> dict[str, dict]:
    """Every ci.yml job that has a step invoking the guard, keyed by job id.

    Asserts non-empty on purpose. A discovery helper that returns ``{}`` when the
    guard is absent would let every per-job assertion below pass vacuously forever,
    which is the same false-green shape the guard itself is being wired to remove.
    """
    found: dict[str, dict] = {}
    for name, job in (_ci().get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if GUARD in str(step.get("run", "")):
                found[name] = job
                break
    assert found, (
        f"no job in .github/workflows/ci.yml runs `{RUN}`. Today the guard is "
        "invoked by nothing outside the script itself, so a credential committed "
        "into a tracked .example file passes CI silently."
    )
    return found


def test_ci_runs_the_example_credential_guard() -> None:
    for name, job in _guard_jobs().items():
        runs = "\n".join(str(step.get("run", "")) for step in job.get("steps") or [])
        assert RUN in runs, f"{name}: expected the guard invoked as `{RUN}`"


def test_ci_runs_on_pull_request() -> None:
    on = _ci().get("on", _ci().get(True))
    assert isinstance(on, dict), "ci.yml is missing on:"
    assert "pull_request" in on, "the guard only helps if ci.yml runs on pull_request"


def test_the_guard_job_is_not_path_gated() -> None:
    """The guard's scope is the whole tree, so a diff-shaped gate is the wrong shape."""
    for name, job in _guard_jobs().items():
        assert "if" not in job, (
            f"{name} is path-gated. The guard scans every tracked .example/.template "
            "file, so gating it on the diff lets a PR whose diff falls outside the "
            "filter skip a check whose scope was never the diff."
        )
        assert "needs" not in job, f"{name} depends on another job and can be skipped"


def test_the_guard_job_is_in_required_checks_needs() -> None:
    needs = (_ci().get("jobs", {}).get("required-checks") or {}).get("needs") or []
    for name in _guard_jobs():
        assert name in needs, (
            f"{name} is not in required-checks.needs, so the aggregator cannot see it "
            "and the job cannot gate a merge."
        )


def test_the_guard_job_fails_on_a_non_zero_exit() -> None:
    for name, job in _guard_jobs().items():
        for step in job.get("steps") or []:
            assert not step.get("continue-on-error"), (
                f"{name}: continue-on-error hides a red guard behind a green check"
            )
        runs = "\n".join(str(step.get("run", "")) for step in job.get("steps") or [])
        for escape in ("|| true", "set +e", "|| :"):
            assert escape not in runs, (
                f"{name}: `{escape}` swallows the guard's exit code. The script exits 1 "
                "on a finding and that must fail the job."
            )


def test_ci_documents_running_the_guard_locally() -> None:
    raw = CI.read_text(encoding="utf-8").splitlines()
    documented = [
        line
        for line in raw
        if line.strip().startswith("#") and RUN in line
    ]
    assert documented, (
        f"no comment in .github/workflows/ci.yml tells a developer how to run "
        f"`{RUN}` locally"
    )


def test_planted_credential_is_named_and_never_quoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DIG-42 acceptance: the red verdict carries the file and the variable, not the value."""
    guard = _load_guard()
    # Synthetic. Never copy a value out of git history into a fixture.
    planted = "Qx7Vb2Nm4Kz8Pr3Tw6Yh1Js5Df9Gu0Ce"
    assert len(planted) >= 32, "the fixture must be long enough to look like a key"
    (tmp_path / ".env.example").write_text(
        f"FRED_API_KEY={planted}\n", encoding="utf-8"
    )
    # Exercise the same enumeration path CI uses: a real checkout, tracked files.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    assert guard.main() == 1

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert ".env.example" in output, output
    assert "FRED_API_KEY" in output, output
    assert planted not in output, "the guard must never print the value it found"