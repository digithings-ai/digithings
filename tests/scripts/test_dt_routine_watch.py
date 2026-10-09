"""Pytest entry for tests/scripts/test_dt_routine_watch.sh (DIG-1220).

The shell suite is the source of truth: 15 checks, no network, driving the canonical
``~/paperclip-workspace/kit/bin/dt-routine-watch`` with fixture files standing in for the
routines API.
This wrapper makes it run under the existing ``pytest tests/scripts/`` CI lane
without editing the protected ``ci.yml``.

Marked ``unit`` because it reads and writes only a temp dir: it files nothing and
touches no real boundary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_dt_routine_watch.sh"


@pytest.mark.unit
def test_routine_watch_boundary_silence_suite() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"dt-routine-watch suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
