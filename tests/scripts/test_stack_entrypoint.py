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
    REPO_ROOT / "apps" / "digithings-stack-cloudflare" / "container" / "entrypoint.sh"
)
EXEC_LINE = "exec /usr/bin/supervisord"

# Commands whose failure is fatal on the boot path: they write to the filesystem
# and can fail on a read-only, full, or mispermissioned volume. Matched at the
# start of a command (not as a substring, so "zammad-mcp host" is not a `cp`).
RISKY = (
    "mkdir",
    "cp ",
    "mv ",
    "rm ",
    "install ",
    "dd ",
    "tee ",
    "truncate ",
    "sed ",
    "ln ",
    "chmod",
    "touch",
)
# Redirect targets that are not durable writes, so an unguarded `>`/`>>` to them
# is fine (e.g. `>/dev/null`).
_SAFE_REDIRECT_TARGETS = ("/dev/null",)


def _pre_exec_lines() -> list[str]:
    """Code lines before the final `exec`, with `\\` continuations joined.

    Joining matters: a guard placed on the continuation line (`cmd \\` then
    `|| echo WARN`) is invisible to a per-line scan otherwise. Full-line comments
    are dropped first, so prose mentioning the exec line is not mistaken for it.
    """
    code = [
        line for line in ENTRYPOINT.read_text().splitlines() if not line.lstrip().startswith("#")
    ]
    joined = "\n".join(code).replace("\\\n", " ")
    assert EXEC_LINE in joined, f"entrypoint no longer ends in `{EXEC_LINE}` — update this test"
    # Last occurrence: anything before the final exec is boot path.
    return [line.strip() for line in joined.rsplit(EXEC_LINE, 1)[0].splitlines() if line.strip()]


def _command_text(line: str) -> str:
    """The command a line runs, without `if !` / `command ` / an absolute path."""
    command = line.removeprefix("if ! ").removeprefix("command ").strip()
    if command.startswith("/"):
        command = command.rsplit("/", 1)[-1]
    return command


def _runs_risky_command(line: str) -> bool:
    return any(_command_text(line).startswith(token) for token in RISKY)


def _has_unguarded_write(line: str) -> bool:
    """The #4149 shape: a `>>` write to a durable path."""
    if ">>" not in line:
        return False
    target = line.split(">>", 1)[1].strip().split(" ", 1)[0]
    return target not in _SAFE_REDIRECT_TARGETS


def _is_condition(line: str) -> bool:
    """True for an `if`/`if !` condition, which `set -e` exempts.

    A failure there selects the `else` branch; it cannot abort the boot. The
    zammad alias relies on exactly that (`if printf … >> /etc/hosts; then … else
    echo WARN … fi`), which is why this is not an offender.
    """
    return line.startswith("if ") or line.startswith("if!")


def _boot_path_block(start_index: int) -> list[str]:
    """Lines from `start_index` through the block's closing `fi`."""
    block: list[str] = []
    for line in _pre_exec_lines()[start_index:]:
        block.append(line)
        if line == "fi":
            break
    return block


def test_required_data_dirs_fail_fast_deliberately():
    """Creating the required dirs may abort the boot — but on purpose, legibly.

    Unlike the optional vault seed, the stack cannot serve without these, so
    fail-fast is the intended behaviour here; what is not acceptable is `set -e`
    killing PID 1 with a bare shell error.
    """
    lines = _pre_exec_lines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith("if !") and "mkdir -p" in line and "DATA_CHROMA" in line
    ]
    assert len(starts) == 1, f"expected exactly one required-dirs check, found {len(starts)}"
    block = _boot_path_block(starts[0])
    assert any("FATAL cannot create required data dirs" in line for line in block), block
    assert "exit 1" in block, f"required-dirs branch must exit non-zero: {block}"


def test_vault_seed_copies_are_best_effort():
    """A failed seed copy degrades the vault; it must not kill the container."""
    copies = [line for line in _pre_exec_lines() if line.startswith("cp ")]
    assert copies, "expected the vault seed copy commands"
    for line in copies:
        assert "||" in line, f"vault seed copy is unguarded: {line}"
        assert "digithings-stack: WARN" in line, f"vault seed copy guard must warn: {line}"


def test_vault_client_dir_creation_is_best_effort():
    mkdirs = [line for line in _pre_exec_lines() if "mkdir -p" in line and "clients" in line]
    assert mkdirs, "expected the vault client-dir mkdir"
    for line in mkdirs:
        assert "||" in line, f"vault client-dir mkdir is unguarded: {line}"
        assert "digithings-stack: WARN" in line, f"vault client-dir guard must warn: {line}"


def test_no_unguarded_risky_command_before_exec():
    """A floor on the boot-path class, not a proof.

    Conservative by construction: it matches a list of writing commands at line
    start (plus unguarded `>>` writes) and joins `\\` continuations. A fatal
    command spelled another way — a helper script, a pipe, a command inside a
    quoted program — slips through, so widen this rather than trusting it.
    """
    offenders = [
        line
        for line in _pre_exec_lines()
        if (_runs_risky_command(line) or _has_unguarded_write(line))
        and "||" not in line
        and not _is_condition(line)
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
