"""Pytest entry for tests/scripts/test_dt_routine_watch.sh (DIG-1220).

The shell suite is the source of truth: 15 checks, no network, driving the canonical
``~/paperclip-workspace/kit/bin/dt-routine-watch`` with fixture files standing in for the
routines API.
This wrapper makes it run under the existing ``pytest tests/scripts/`` CI lane
without editing the protected ``ci.yml``.

The script under test is host-resident and its kit has no git remote: Paperclip is
loopback-only, so the observer has to live on the host that runs it. A CI runner cannot
obtain it. Rather than fail the lane over a file the runner could never have had, this
wrapper skips there, and says so out loud (board decision on DIG-2618).

The skip is deliberately narrow. It applies only on a CI runner. On any other host a
missing script is a real fault and still fails loudly, because a host that owns the
observer yet cannot find it has lost its only regression guard. A skip there would be
exactly the vacuously satisfied guard this change exists to remove.

The candidate list below mirrors the one in the shell suite's header block; keep the two
in step, or a third candidate added there will not be honoured here.

Marked ``unit`` because it reads and writes only a temp dir: it files nothing and
touches no real boundary.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_dt_routine_watch.sh"

# Mirrors the shell suite's own candidate loop. Keep in step with it.
_CANDIDATES = (
    _SCRIPT.parent.parent / "bin" / "dt-routine-watch",
    Path.home() / "paperclip-workspace" / "kit" / "bin" / "dt-routine-watch",
)


@pytest.mark.unit
def test_routine_watch_boundary_silence_suite() -> None:
    if not any(path.is_file() for path in _CANDIDATES):
        looked = ", ".join(str(path) for path in _CANDIDATES)
        if os.environ.get("CI"):
            print(
                "SKIP dt-routine-watch: kit copy not present on this host; "
                f"looked in {looked}"
            )
            pytest.skip(
                "kit copy not present on this host: the 15 checks are host-local "
                "and run on the observer's own host, not in CI (DIG-2618)"
            )
        pytest.fail(
            "dt-routine-watch is missing on a non-CI host. That host runs the "
            "observer, so losing the script silently retires its 15 checks. "
            f"Looked in: {looked}"
        )

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