#!/usr/bin/env python3
"""Agent-runnable Kairos staging E2E gate (core Supabase).

Phase A: Observer Settings hops when a JWT (or email/password) is present —
reads 200, Custom writes ``TIER_FORBIDDEN``. Does not require vendor secrets.

Phase B: fails loudly with **named** missing secrets when Stripe / Mailgun /
Alpaca OAuth are unset. Never substitutes paper-fakes for staging acceptance.

Phase C: once secrets are present, checkout must return a session URL.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py

Exit codes:
  0 — required secrets present and checkout probe cleared config errors
  2 — named required secrets missing (or JWT missing after secrets present)
  3 — Observer hop regression, or secrets present but core EF misconfigured
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.olympus.kairos.staging_e2e import run_staging_e2e  # noqa: E402


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            payload = json.loads(raw) if raw else {}
            return int(resp.status), payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        return int(exc.code), payload if isinstance(payload, dict) else {}


def main() -> int:
    return run_staging_e2e(
        http=_http_json,
        environ=os.environ,
        log=lambda msg: print(msg, flush=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
