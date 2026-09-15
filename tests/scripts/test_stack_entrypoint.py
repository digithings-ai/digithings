"""Boot-path pins for the digithings-stack container entrypoint (#4156).

`entrypoint.sh` is PID 1 and ends in `exec /usr/bin/supervisord`, so any
unguarded command that fails under `set -eu` aborts the container: `:8000` never
opens and the Worker 503s every request (#4149). Every command before the `exec`
must therefore be either deliberately fail-fast or best-effort.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = (
    REPO_ROOT / "cloudflare" / "digithings-stack-cloudflare" / "container" / "entrypoint.sh"
)
EXEC_LINE = "exec /usr/bin/supervisord"

# Commands whose failure is fatal on the boot path: they touch the filesystem
# and can fail on a read-only, full, or mispermissioned volume. Matched at the
# start of a command (not as a substring, so "zammad-mcp host" is not a `cp`).
RISKY = ("mkdir", "cp ", "mv ", "ln ", "chmod", "touch")


def _runs_risky_command(line: str) -> bool:
    command = line.removeprefix("if ! ").strip()
    return any(command.startswith(token) for token in RISKY)


def _pre_exec_lines() -> list[str]:
    """Code lines before the final `exec`, with `\\` continuations joined.

    Joining matters: a guard placed on the continuation line (`cmd \\` then
    `|| echo WARN`) is invisible to a per-line scan otherwise.
    """
    body = ENTRYPOINT.read_text()
    code = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    joined = "\n".join(code).replace("\\\n", " ")
    return [line.strip() for line in joined.split(EXEC_LINE)[0].splitlines() if line.strip()]


def test_required_data_dirs_fail_fast_deliberately():
    """Creating the required dirs may abort the boot — but on purpose, legibly.

    Unlike the optional vault seed, the stack cannot serve without these, so
    fail-fast is the intended behaviour here; what is not acceptable is `set -e`
    killing PID 1 with a bare shell error.
    """
    lines = [line for line in _pre_exec_lines() if "mkdir -p" in line and "DATA_CHROMA" in line]
    assert lines, "expected the required-dirs mkdir"
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("if !"), f"required-dirs mkdir is not an explicit check: {line}"
    body = ENTRYPOINT.read_text()
    assert "FATAL cannot create required data dirs" in body
    assert "exit 1" in body


def test_vault_seed_copies_are_best_effort():
    """A failed seed copy degrades the vault; it must not kill the container."""
    copies = [line for line in _pre_exec_lines() if line.startswith("cp ")]
    assert copies, "expected the vault seed copy commands"
    for line in copies:
        assert "||" in line, f"vault seed copy is unguarded: {line}"


def test_vault_client_dir_creation_is_best_effort():
    mkdirs = [line for line in _pre_exec_lines() if "mkdir -p" in line and "clients" in line]
    assert mkdirs, "expected the vault client-dir mkdir"
    for line in mkdirs:
        assert "||" in line, f"vault client-dir mkdir is unguarded: {line}"


def test_no_unguarded_risky_command_before_exec():
    """Every filesystem command on the boot path is guarded or an explicit check.

    Deliberately conservative: it can miss a fatal command spelled another way
    (a new helper script, a pipe), so it is a floor on this class, not proof.
    """
    offenders = [
        line
        for line in _pre_exec_lines()
        if _runs_risky_command(line) and "||" not in line and not line.startswith("if !")
    ]
    assert not offenders, "unguarded command(s) on the boot path: " + "; ".join(offenders)


def test_a_failing_cp_aborts_set_e_unless_guarded(tmp_path):
    """Pins the shell semantics the guards rely on, so the reasoning cannot rot."""
    missing = tmp_path / "no-such-dir" / "seed.md"
    dest = tmp_path / "dest.md"
    guarded = f"set -eu\ncp {missing} {dest} || echo WARN\necho REACHED\n"
    unguarded = f"set -eu\ncp {missing} {dest}\necho REACHED\n"
    ok = subprocess.run(["sh", "-c", guarded], capture_output=True, text=True)
    aborted = subprocess.run(["sh", "-c", unguarded], capture_output=True, text=True)
    assert ok.returncode == 0 and "REACHED" in ok.stdout
    assert aborted.returncode != 0 and "REACHED" not in aborted.stdout
