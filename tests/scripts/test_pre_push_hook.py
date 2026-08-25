"""Pytest entry for tests/scripts/test_pre_push_hook.sh (#2468 / #2483).

The shell suite is the source of truth (real temp-repo cases against
``scripts/hooks/pre-push.sh``). This wrapper makes it run under the existing
``pytest tests/scripts/`` CI lane without editing the protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_pre_push_hook.sh"


@pytest.mark.unit
def test_pre_push_hook_live_trading_and_deletion_suite() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"pre-push suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
