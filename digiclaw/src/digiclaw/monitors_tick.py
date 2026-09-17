"""digiclaw → digisearch scheduled-tick caller (Phase C, #4065 Task 8d).

The ``web-watch-tick`` agent wakes digisearch every 60 seconds (see
``digiclaw/agents/web-watch-tick.yaml``); this module POSTs
``/v1/monitors/tick`` so digisearch runs every due watch (§4.8). The request
carries a digikey service JWT minted through :mod:`digibase.service_auth` from
the heartbeat's provisioned ``DIGICLAW_DIGIKEY_API_KEY`` (consumed, never
re-implemented — R11). The JWT import is deliberately lazy and fully qualified
inside :func:`run_due_monitors` so importing this module needs neither
credentials nor the digibase module, and the stable patch target
``digibase.service_auth.get_service_jwt`` keeps working for tests.

Transport and auth failures raise: the scheduler persists them as the agent's
``last_error`` (never a silent successful tick), and the ``digiclaw schedule
tick`` CLI prints the failed outcome.
"""

# score:allow untyped any
# digisearch tick responses are dynamic JSON payloads; Any is the honest annotation.
from __future__ import annotations

import os
from typing import Any

import httpx

__all__ = ["run_due_monitors"]

_DEFAULT_DIGISEARCH_URL = "http://127.0.0.1:8002"
_TICK_PATH = "/v1/monitors/tick"

# One tick runs every due watch sequentially; the read budget is generous enough
# for a burst of due watches and still bounded so a hung server surfaces as a
# scheduler error instead of a wedged supervisor.
_TIMEOUT_S = 120.0


def _post(url: str, token: str) -> dict[str, Any]:
    """POST ``url`` with the service bearer token; raise on transport/HTTP failure."""
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        response = client.post(url, headers={"authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()


def run_due_monitors(
    *,
    digisearch_url: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, int]:
    """Run every due digisearch watch once; return ``{"runs": n, "failed": m}``.

    The base URL resolves as explicit ``digisearch_url`` → ``DIGISEARCH_URL``
    env → ``http://127.0.0.1:8002``. When no ``bearer_token`` is passed the
    service JWT is minted with the heartbeat's key env and the landed
    ``("digisearch:query",)`` scope tuple; either failure mode raises rather
    than returning an empty tick.
    """
    base = (digisearch_url or os.environ.get("DIGISEARCH_URL") or "").strip()
    url = f"{(base or _DEFAULT_DIGISEARCH_URL).rstrip('/')}{_TICK_PATH}"
    token = bearer_token
    if token is None:
        from digibase.service_auth import get_service_jwt

        token = get_service_jwt(
            key_env="DIGICLAW_DIGIKEY_API_KEY",
            digikey_url_env="DIGIKEY_URL",
            scopes=("digisearch:query",),
        )
    payload = _post(url, token)
    runs = payload.get("runs") or []
    failed = sum(1 for run in runs if run.get("status") == "failed")
    return {"runs": len(runs), "failed": failed}
