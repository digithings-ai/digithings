"""Unit tests for scripts/check_example_credentials.py and its CI wiring (DIG-3148).

The guard only earns its keep if it is actually invoked, so these tests pin the
call site in ``.github/workflows/ci.yml`` (unconditional job + required-checks
needs entry) as well as the verdict logic. A guard that is never run detects
nothing -- the same argument that ``test_check_gloomberb_ci_guard.py`` makes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"
_CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
_JOB = "example-credentials-guard"

# A synthetic credential-shaped value. 32 alnum chars hit both the
# `^[A-Za-z0-9]{32,}$` arm and the generic 32+ arm; it is invented here and
# matches no real credential.
_FAKE_CRED_32 = "Ab3dEf7hIj2kLm5nOp9qRs4tUv6wXy8z"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_example_credentials", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> Any:
    return _load_module()


# ── Verdict logic ────────────────────────────────────────────────────────────


def test_placeholder_values_pass(guard: Any) -> None:
    for v in (
        "replace-with-your-fred-api-key",
        "CHANGEME",
        "<insert-key-here>",
        "your_api_key_here",
        "example_value",
        "",
        "localhost",
    ):
        assert guard.is_placeholder(v), f"{v!r} must read as a placeholder"
    # NOTE (batch fold of #5523): this list carried "digichat" on develop.
    # The batch product-name rule (folded from #5032, pinned in
    # test_check_example_credentials_product_names.py) reports a product name
    # under a credential-shaped variable, so "digichat" is no longer a bare
    # placeholder. It stays clean under non-credential names via the length
    # floor, which test_generic_placeholder_password_is_not_detected pins.


def test_realistic_credential_value_is_not_a_placeholder(guard: Any) -> None:
    assert not guard.is_placeholder(_FAKE_CRED_32)
    # Control: the placeholder detector fires on the row above, so a False
    # here is a measurement, not a dead detector.
    assert guard.is_placeholder("replace-me")


def test_cred_var_matching(guard: Any) -> None:
    assert guard.looks_cred_var("COINGECKO_API_KEY")
    assert guard.looks_cred_var("db_password")
    assert not guard.looks_cred_var("SEC_EDGAR_USER_AGENT")
    assert not guard.looks_cred_var("LOG_LEVEL")


def test_cred_value_matching(guard: Any) -> None:
    assert guard.looks_cred_val(_FAKE_CRED_32)
    assert guard.looks_cred_val("sk-" + "a" * 24)
    assert not guard.looks_cred_val("replace-with-your-coingecko-api-key")
    assert not guard.looks_cred_val("short")


def test_script_fails_on_a_committed_credential_shape(tmp_path: Path) -> None:
    """Positive control: a tracked .example file carrying a credential-shaped
    value fails the script. Run in a non-git dir so the script takes its
    rglob fallback over exactly these files."""
    (tmp_path / "svc.env.example").write_text(
        f"COINGECKO_API_KEY={_FAKE_CRED_32}\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "svc.env.example" in proc.stderr


def test_script_passes_on_placeholders_only(tmp_path: Path) -> None:
    (tmp_path / "svc.env.example").write_text(
        "COINGECKO_API_KEY=replace-with-your-coingecko-api-key\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_script_passes_on_the_live_tree() -> None:
    """The tree this test runs on must be clean -- the same verdict the new
    CI job will publish."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ── CI wiring: a guard that is never invoked detects nothing ─────────────────


def _ci() -> dict[str, Any]:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def test_ci_has_the_guard_job_and_calls_the_script() -> None:
    jobs = _ci()["jobs"]
    assert _JOB in jobs, f"ci.yml must define the {_JOB} job"
    steps = jobs[_JOB]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    assert "scripts/check_example_credentials.py" in runs


def test_ci_guard_job_is_unconditional() -> None:
    """The guard scans .example files anywhere in the tree, so a path filter
    or a needs-gate would blind it to values committed outside its own paths."""
    job = _ci()["jobs"][_JOB]
    assert "needs" not in job, "the guard job must not wait on another job"
    assert "if" not in job, "the guard job must not be path-filtered"


def test_ci_guard_job_needs_no_install_step() -> None:
    """Stdlib-only: the job must not need pip or npm to run."""
    steps = _ci()["jobs"][_JOB]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    for banned in ("pip install", "npm ci", "npm install", "uv run"):
        assert banned not in runs, f"the guard is stdlib-only; {banned!r} must not appear"


def test_guard_job_is_in_required_checks_needs() -> None:
    """Otherwise the guard can go red and still merge."""
    needs = _ci()["jobs"]["required-checks"]["needs"]
    flat: list[str] = []
    for item in needs:
        flat.extend(item if isinstance(item, list) else [item])
    assert _JOB in flat, f"{_JOB} must be in required-checks needs; got {flat}"
