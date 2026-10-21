"""Pin the ``sctl publish`` gate declared in ``.sctl.yml`` (DIG-4608).

``sctl publish`` executes the value of the first ``test:`` line of
``.sctl.yml`` as an argv, with the repository root as the working directory
and without a shell. The value used to be ``uv run pytest -m unit``, which
resolves only the root virtual environment, so the published suite could
not even be collected and every publish failed with "publish: suite
failed".

These cases pin the gate that ``scripts/check_sctl_publish_gate.py``
enforces, one per defect it has to catch:

* a missing ``test:`` line (the command does not exist at all);
* an ``argv[0]`` that is not a real executable;
* an argument that names a script that is not there;
* today's value, which prepares no environment;
* a wrapper that installs only the root environment;
* a wrapper that runs pytest without ``--frozen --no-sync``;
* a wrapper that falls back to the whole-workspace sweep, which aborts;
* a value carrying a shell operator, which the runner cannot honour;
* a value separated by a tab or a double space, which must parse the same;
* a declared command that exits non-zero, and one that collects nothing;
* and that the declared command is really executed at all.

The real tree is never mutated: every case builds its own repository under
``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_sctl_publish_gate.py"

pytestmark = pytest.mark.unit

# A wrapper that satisfies every structural rule but never touches uv, so
# the cases stay fast and offline. The uv steps live in a branch that is
# never taken at runtime.
_SOUND_WRAPPER = """#!/usr/bin/env bash
set -euo pipefail
if [ "${SCTL_PUBLISH_GATE_NEVER:-0}" = "1" ]; then
  uv sync --frozen --all-packages --all-extras
  uv run --frozen --no-sync pytest tests/scripts/ tests/config/ -m "unit or baseline"
fi
echo "42 tests collected in 0.42s"
"""

_RUNNING_WRAPPER = _SOUND_WRAPPER.replace(
    'echo "42 tests collected in 0.42s"',
    'echo ran > declared-command.marker\necho "42 tests collected in 0.42s"',
)


def _load_module():
    spec = importlib.util.spec_from_file_location("check_sctl_publish_gate", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _fake_repo(tmp_path: Path, value: str | None, wrapper: str | None = None) -> Path:
    """A throwaway repository with its own ``.sctl.yml`` and wrapper.

    ``value=None`` writes a config that has no ``test:`` line at all.
    """
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    config = "# a comment\n" if value is None else f"# a comment\ntest: {value}\n"
    (root / ".sctl.yml").write_text(config, encoding="utf-8")
    if wrapper is not None:
        (root / "scripts" / "gate.sh").write_text(wrapper, encoding="utf-8")
    return root


def _codes(gate, findings) -> set[str]:
    return {finding.code for finding in findings}


def test_repository_gate_is_sound(gate) -> None:
    """The repository's own declared gate passes every rule and runs."""
    findings = gate.run_checks(REPO_ROOT)
    assert _codes(gate, findings) == set(), findings


def test_value_is_parsed_the_way_digiforge_parses_it(gate) -> None:
    """A tab or a double space separates arguments exactly like a space."""
    spaced = "# comment\ntest: bash scripts/gate.sh\n"
    tabbed = "# comment\ntest:\tbash\tscripts/gate.sh\n"
    doubled = "# comment\ntest: bash  scripts/gate.sh\n"
    assert gate.declared_argv(tabbed) == gate.declared_argv(spaced)
    assert gate.declared_argv(doubled) == gate.declared_argv(spaced)
    assert gate.declared_argv(spaced) == ["bash", "scripts/gate.sh"]


def test_missing_test_line_is_reported(gate, tmp_path) -> None:
    """No 'test:' line means 'sctl publish' has no suite to run."""
    root = _fake_repo(tmp_path, None)
    codes = _codes(gate, gate.run_checks(root))
    assert "no_test_value" in codes


def test_missing_executable_is_reported(gate, tmp_path) -> None:
    """argv[0] has to resolve to a real executable."""
    root = _fake_repo(tmp_path, "digithings-publish-gate-not-a-program")
    codes = _codes(gate, gate.run_checks(root))
    assert "executable_missing" in codes


def test_missing_script_is_reported(gate, tmp_path) -> None:
    """An argument that names a script that is not there is a broken gate."""
    root = _fake_repo(tmp_path, "bash scripts/does-not-exist.sh")
    codes = _codes(gate, gate.run_checks(root))
    assert "argument_missing" in codes
    assert "no_repo_script" in codes


def test_todays_value_is_rejected(gate, tmp_path) -> None:
    """`uv run pytest -m unit` prepares no environment and is refused."""
    root = _fake_repo(tmp_path, "uv run pytest -m unit")
    codes = _codes(gate, gate.run_checks(root))
    assert "no_repo_script" in codes


def test_wrapper_that_syncs_only_the_root_env_is_rejected(gate, tmp_path) -> None:
    """The whole workspace has to be installed from the committed lockfile."""
    wrapper = _SOUND_WRAPPER.replace("uv sync --frozen --all-packages --all-extras", "uv sync --frozen")
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", wrapper)
    codes = _codes(gate, gate.run_checks(root))
    assert "sync_not_workspace" in codes


def test_wrapper_without_frozen_no_sync_is_rejected(gate, tmp_path) -> None:
    """The suite has to run from the locked environment it just installed."""
    wrapper = _SOUND_WRAPPER.replace(
        'uv run --frozen --no-sync pytest tests/scripts/ tests/config/ -m "unit or baseline"',
        'uv run pytest tests/scripts/ tests/config/ -m "unit or baseline"',
    )
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", wrapper)
    codes = _codes(gate, gate.run_checks(root))
    assert "run_not_unit" in codes


def test_wrapper_that_falls_back_to_the_whole_workspace_sweep_is_rejected(gate, tmp_path) -> None:
    """The lane's test paths must be named: the whole-workspace sweep aborts."""
    wrapper = _SOUND_WRAPPER.replace(
        'pytest tests/scripts/ tests/config/ -m "unit or baseline"',
        "pytest -m unit",
    )
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", wrapper)
    codes = _codes(gate, gate.run_checks(root))
    assert "run_not_unit" in codes


def test_shell_operator_in_the_value_is_rejected(gate, tmp_path) -> None:
    """The runner has no shell, so `&&` would be a literal argument."""
    root = _fake_repo(tmp_path, "bash scripts/gate.sh && echo done", _SOUND_WRAPPER)
    codes = _codes(gate, gate.run_checks(root))
    assert "shell_operator" in codes


def test_failing_declared_command_is_reported(gate, tmp_path) -> None:
    """A declared command that exits non-zero is a broken publish gate."""
    wrapper = _SOUND_WRAPPER.replace('echo "42 tests collected in 0.42s"', "exit 1")
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", wrapper)
    codes = _codes(gate, gate.run_checks(root))
    assert "declared_command_failed" in codes


def test_declared_command_must_collect_tests(gate, tmp_path) -> None:
    """A gate that collects nothing does not prove the suite runs."""
    wrapper = _SOUND_WRAPPER.replace('echo "42 tests collected in 0.42s"', "true")
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", wrapper)
    codes = _codes(gate, gate.run_checks(root))
    assert "declared_command_collected_nothing" in codes


def test_declared_command_is_actually_executed(gate, tmp_path) -> None:
    """The guard runs the command it declares, in the repository root."""
    root = _fake_repo(tmp_path, "bash scripts/gate.sh", _RUNNING_WRAPPER)
    gate.run_checks(root)
    assert (root / "declared-command.marker").exists()
