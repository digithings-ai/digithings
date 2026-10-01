"""The real runner: argv in, exit code and output out, no shell."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from digivoice.runner import error_tail, run_command

pytestmark = pytest.mark.unit

ECHO = [sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])"]


def test_runs_an_argv_and_captures_stdout() -> None:
    result = run_command(ECHO + ["hello"])
    assert result.code == 0
    assert result.stdout == "hello"
    assert result.argv == ECHO + ["hello"]


def test_argv_is_a_list_so_no_shell_can_be_injected() -> None:
    result = run_command([sys.executable, "-c", "import sys; print(sys.argv[1])", "a; echo b"])
    assert result.stdout.strip() == "a; echo b"


def test_a_missing_binary_is_exit_127_not_a_traceback(tmp_path: Path) -> None:
    result = run_command([str(tmp_path / "absent")])
    assert result.code == 127
    assert "not found" in result.stderr


def test_a_hanging_child_is_killed_at_the_timeout() -> None:
    result = run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert result.code == 124
    assert "timed out" in result.stderr


def test_stdin_is_routed_and_never_inherited(tmp_path: Path) -> None:
    read = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]
    assert run_command(read, stdin="from stdin").stdout == "from stdin"
    # An empty pipe, not the parent's terminal, so a reader cannot block.
    assert run_command(read).stdout == ""


def test_error_tail_keeps_the_last_lines_and_fits_the_limit() -> None:
    assert error_tail("one\ntwo\nthree\n") == "one | two | three"
    assert error_tail("") == ""
    long = error_tail("x" * 10, limit=5)
    assert len(long) == 5
