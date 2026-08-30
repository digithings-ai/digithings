#!/usr/bin/env python3
"""Agent-runnable Kairos staging E2E gate (core Supabase).

Fails loudly with **named** missing secrets when Stripe / Mailgun / Alpaca
OAuth are unset. Never substitutes paper-fakes for staging acceptance.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py

Exit codes:
  0 — required secrets present and checkout probe cleared config errors
  2 — named required secrets missing (or JWT missing)
  3 — secrets present but core EF still misconfigured / unexpected HTTP
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

from digiquant.olympus.kairos.staging_secrets import (  # noqa: E402
    KAIROS_STAGING_REQUIRED_SECRETS,
    format_missing_secrets_failure,
    missing_kairos_staging_secrets,
)

CORE_FUNCTIONS_BASE = (
    os.environ.get("KAIROS_STAGING_FUNCTIONS_BASE")
    or "https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1"
)


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
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
    missing = missing_kairos_staging_secrets()
    print("kairos_staging_e2e: checking required secret *names* (values never printed)")
    print(f"  inventory_count={len(KAIROS_STAGING_REQUIRED_SECRETS)}")
    if missing:
        print(format_missing_secrets_failure(missing), file=sys.stderr)
        return 2

    jwt = (os.environ.get("KAIROS_STAGING_USER_JWT") or "").strip()
    if not jwt:
        print(
            format_missing_secrets_failure(["KAIROS_STAGING_USER_JWT"]),
            file=sys.stderr,
        )
        return 2

    status, body = _http_json(
        "POST",
        f"{CORE_FUNCTIONS_BASE}/create-checkout-session",
        headers={"Authorization": f"Bearer {jwt}"},
        body={"tier": "baseline", "interval": "monthly"},
    )
    code = str(body.get("code") or "")
    print(f"  checkout_http={status} code={code or 'ok'}")
    if status >= 500 and code in {"PRICE_NOT_CONFIGURED", "STRIPE_NOT_CONFIGURED"}:
        print(
            "Checkout still misconfigured on core EF — set the same secret names "
            f"via `supabase secrets set` (code={code}).",
            file=sys.stderr,
        )
        return 3
    if status not in {200, 201} or not body.get("url"):
        print(
            f"Unexpected checkout response HTTP {status} code={code}",
            file=sys.stderr,
        )
        return 3

    wh_status, wh_body = _http_json(
        "POST",
        f"{CORE_FUNCTIONS_BASE}/stripe-webhook",
        body={"id": "evt_staging_probe"},
    )
    wh_code = str(wh_body.get("code") or "")
    print(f"  webhook_http={wh_status} code={wh_code or 'ok'}")
    if wh_code == "STRIPE_NOT_CONFIGURED":
        print(
            "stripe-webhook still STRIPE_NOT_CONFIGURED on core EF.",
            file=sys.stderr,
        )
        return 3

    print(
        "kairos_staging_e2e: checkout cleared config errors. "
        "Complete browser Checkout → Alpaca OAuth → overlay → digest manually; "
        "Mailgun MCP / notify.dispatch still required for digest proof."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
