"""Exchange a DigiKey machine API key for a short-lived JWT (heartbeat / automation)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def digikey_bearer_token() -> str | None:
    """Return ``Authorization`` bearer JWT, or ``None`` if no API key is configured."""
    api_key = (os.environ.get("DIGICLAW_DIGIKEY_API_KEY") or os.environ.get("DIGIKEY_API_KEY") or "").strip()
    if not api_key:
        return None
    base = os.environ.get("DIGIKEY_URL", "http://127.0.0.1:8005").rstrip("/")
    body = json.dumps(
        {
            "grant_type": "api_key",
            "api_key": api_key,
            "requested_scopes": ["digiquant:backtest", "digiquant:optimize"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{base}/v1/oauth/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError:
        return None
    token = data.get("access_token")
    return str(token).strip() if token else None
