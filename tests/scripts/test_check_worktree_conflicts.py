"""Pytest entry for tests/scripts/test_check_worktree_conflicts.sh (#2485 / #2569).

The shell suite is the source of truth (scratch repo + nested/legacy worktrees
against ``scripts/check-worktree-conflicts.sh``). This wrapper makes it run under
the existing ``pytest tests/scripts/`` CI lane without editing the protected
``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_check_worktree_conflicts.sh"


@pytest.mark.unit
def test_check_worktree_conflicts_nested_layout_and_pipefail_drain() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check-worktree-conflicts suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
