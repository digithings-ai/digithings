"""Pytest entry for tests/scripts/test_check_litellm_vendor_boundary.sh (DIG-1780).

The shell suite is the source of truth: it runs against a scratch git fixture so the
live tree is never mutated, and it covers the cases a real PR would hit — a vendor
image returning to a compose file, to a workflow, or to prose; a moving tag; a
Dockerfile pin bumped without the gate; and an `enterprise/` directory planted in the
image. This wrapper makes it run under ``pytest tests/scripts/`` without editing the
protected ``ci.yml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_check_litellm_vendor_boundary.sh"


@pytest.mark.unit
def test_check_litellm_vendor_boundary() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check_litellm_vendor_boundary suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
