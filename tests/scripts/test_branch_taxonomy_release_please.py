"""Pytest entry for tests/scripts/test_branch_taxonomy_release_please.sh (#2557).

The shell suite pins the release-please arm of ``scripts/hooks/pre-push.sh``
against allow/deny cases and the mirrored github-rulesets JSON. This wrapper
makes it run under ``pytest tests/scripts/`` without editing protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_branch_taxonomy_release_please.sh"


@pytest.mark.unit
def test_branch_taxonomy_admits_release_please_refs() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"release-please taxonomy suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
