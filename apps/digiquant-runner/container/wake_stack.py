"""Wake digikey and digisearch before the house chain.

Twelve attempts, 10s timeout, 5s between tries. Always exits 0: a down
dependency is a warning, not a failed job. No curl.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

ATTEMPTS = 12
TIMEOUT_SECONDS = 10
SLEEP_SECONDS = 5
KEY_HEALTH = "https://key.digithings.ai/healthz"
SEARCH_HEALTH = "https://search.digithings.ai/healthz"
URLS = (KEY_HEALTH, SEARCH_HEALTH)

Opener = Callable[[str, float], int]


def default_opener(url: str, timeout: float) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def wake(
    urls: tuple[str, ...] = URLS,
    *,
    attempts: int = ATTEMPTS,
    timeout: float = TIMEOUT_SECONDS,
    sleep_seconds: float = SLEEP_SECONDS,
    opener: Opener = default_opener,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, bool]:
    """Return the last probe for each URL. True means HTTP 200."""
    last = {url: False for url in urls}
    for index in range(attempts):
        last = {url: opener(url, timeout) == 200 for url in urls}
        if all(last.values()):
            return last
        if index < attempts - 1:
            sleep(sleep_seconds)
    return last


def format_wake(result: Mapping[str, bool]) -> str:
    key = str(result.get(KEY_HEALTH, False)).lower()
    search = str(result.get(SEARCH_HEALTH, False)).lower()
    return f"wake key.digithings.ai/healthz={key} search.digithings.ai/healthz={search}"


def main() -> int:
    print(format_wake(wake()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
