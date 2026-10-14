"""Pytest entry for tests/scripts/test_create_pr_component_regex.sh (#2433).

The shell suite pins the COMPONENT extraction in ``scripts/create_pr.sh``
(portable match class for macOS bash 3.2, no ``\\w``). This wrapper makes it
run under the existing ``pytest tests/scripts/`` CI lane without editing the
protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_create_pr_component_regex.sh"


@pytest.mark.unit
def test_create_pr_component_regex_suite() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"create_pr component regex suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
