"""Pytest entry for tests/scripts/test_check_pandas_boundary.sh (#3107).

The shell suite is the source of truth (scratch digiquant tree + missing-rg
fail-closed). This wrapper makes it run under ``pytest tests/scripts/`` without
editing the protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_check_pandas_boundary.sh"


@pytest.mark.unit
def test_check_pandas_boundary_rg_missing_and_allowlist() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check_pandas_boundary suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
