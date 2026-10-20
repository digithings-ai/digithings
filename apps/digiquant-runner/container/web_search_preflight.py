"""Six attempts of `python -m digiquant web-search healthcheck`.

Exit 1 when every attempt fails. The catalog step is fatal; wake is not.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable

ATTEMPTS = 6
SLEEP_SECONDS = 10

Healthcheck = Callable[[], int]


def digiquant_healthcheck() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "digiquant", "web-search", "healthcheck"],
        check=False,
    )
    return int(completed.returncode)


def run_preflight(
    healthcheck: Healthcheck,
    *,
    attempts: int = ATTEMPTS,
    sleep_seconds: float = SLEEP_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    for index in range(attempts):
        if healthcheck() == 0:
            return 0
        if index < attempts - 1:
            sleep(sleep_seconds)
    return 1


def main() -> int:
    return run_preflight(digiquant_healthcheck)


if __name__ == "__main__":
    raise SystemExit(main())
