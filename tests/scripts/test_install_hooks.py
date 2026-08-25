"""Pytest entry for tests/scripts/test_install_hooks.sh (#2502).

The shell suite is the source of truth (scratch repo + linked worktree against
``scripts/install-hooks.sh``). This wrapper makes it run under the existing
``pytest tests/scripts/`` CI lane without editing the protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_install_hooks.sh"


@pytest.mark.unit
def test_install_hooks_fail_closed_and_worktree_safe() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"install-hooks suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
