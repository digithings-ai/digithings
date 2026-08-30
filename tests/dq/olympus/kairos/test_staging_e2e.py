"""Kairos staging E2E harness — loud fail on missing vendor secrets.

Unit tests always exercise the inventory (no network). The ``staging_e2e``
marked test refuses fakes: if required secrets are empty it ``pytest.fail``s
with named missing keys; when secrets are present it probes core Edge
Functions (checkout past PRICE_NOT_CONFIGURED, webhook past
STRIPE_NOT_CONFIGURED) and documents remaining live hops.

Not a substitute for paper-fakes ``tests/integration/test_kairos_tenancy_chain.py``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import pytest
from digiquant.olympus.kairos.staging_secrets import (
    KAIROS_STAGING_OPTIONAL_SECRETS,
    KAIROS_STAGING_REQUIRED_SECRETS,
    format_missing_secrets_failure,
    missing_kairos_staging_secrets,
)

CORE_FUNCTIONS_BASE = (
    os.environ.get("KAIROS_STAGING_FUNCTIONS_BASE")
    or "https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1"
)


@pytest.mark.unit
def test_staging_secret_inventory_lists_vendor_blockers() -> None:
    """Inventory must name every vendor secret that blocks EPIC staging E2E."""
    required = set(KAIROS_STAGING_REQUIRED_SECRETS)
    assert "STRIPE_SECRET_KEY" in required
    assert "STRIPE_WEBHOOK_SECRET" in required
    assert "STRIPE_PRICE_BASELINE_MONTHLY" in required
    assert "STRIPE_PRICE_CUSTOM_MONTHLY" in required
    assert "MAILGUN_API_KEY" in required
    assert "MAILGUN_DOMAIN" in required
    assert "NOTIFY_FROM" in required
    assert "ALPACA_OAUTH_CLIENT_ID" in required
    assert "ALPACA_OAUTH_CLIENT_SECRET" in required
    # Optional must not silently satisfy required.
    assert not set(KAIROS_STAGING_OPTIONAL_SECRETS) & required


@pytest.mark.unit
def test_missing_secrets_reports_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in KAIROS_STAGING_REQUIRED_SECRETS:
        monkeypatch.delenv(name, raising=False)
    missing = missing_kairos_staging_secrets()
    assert missing == list(KAIROS_STAGING_REQUIRED_SECRETS)
    msg = format_missing_secrets_failure(missing)
    assert "STRIPE_SECRET_KEY" in msg
    assert "MAILGUN_API_KEY" in msg
    assert "ALPACA_OAUTH_CLIENT_SECRET" in msg
    # Never embed placeholder values.
    assert "sk_test" not in msg
    assert "whsec_" not in msg


@pytest.mark.unit
def test_missing_secrets_empty_when_all_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in KAIROS_STAGING_REQUIRED_SECRETS:
        monkeypatch.setenv(name, f"test-placeholder-{name}")
    assert missing_kairos_staging_secrets() == []


@pytest.mark.unit
def test_empty_and_placeholder_values_count_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in KAIROS_STAGING_REQUIRED_SECRETS:
        monkeypatch.setenv(name, "placeholder")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MAILGUN_API_KEY", "EMPTY")
    monkeypatch.setenv("NOTIFY_FROM", "null")
    missing = missing_kairos_staging_secrets()
    assert "STRIPE_SECRET_KEY" in missing
    assert "MAILGUN_API_KEY" in missing
    assert "NOTIFY_FROM" in missing


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            payload = json.loads(raw) if raw else {}
            return resp.status, payload if isinstance(payload, dict) else {"raw": payload}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload if isinstance(payload, dict) else {"raw": payload}


@pytest.mark.staging_e2e
def test_kairos_core_staging_e2e_refuses_fakes() -> None:
    """Live core E2E gate — fails with named missing secrets; never paper-fakes.

    Run explicitly::

        pytest -m staging_e2e tests/dq/olympus/kairos/test_staging_e2e.py

    Or::

        PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
    """
    missing = missing_kairos_staging_secrets()
    if missing:
        pytest.fail(format_missing_secrets_failure(missing))

    jwt = (os.environ.get("KAIROS_STAGING_USER_JWT") or "").strip()
    if not jwt:
        pytest.fail(
            format_missing_secrets_failure(["KAIROS_STAGING_USER_JWT"])
            + " (Agentmail/GitHub Auth session JWT for create-checkout-session)"
        )

    checkout_url = f"{CORE_FUNCTIONS_BASE}/create-checkout-session"
    status, body = _http_json(
        "POST",
        checkout_url,
        headers={"Authorization": f"Bearer {jwt}"},
        body={"tier": "baseline", "interval": "monthly"},
    )
    code = str(body.get("code") or "")
    if status >= 500 and code in {"PRICE_NOT_CONFIGURED", "STRIPE_NOT_CONFIGURED"}:
        pytest.fail(
            "Checkout still reports billing misconfig after secrets were nonempty "
            f"in process env — ensure the same names are set on core EF secrets "
            f"(HTTP {status} code={code} message={body.get('message')!s}). "
            "Values never logged."
        )
    if status not in {200, 201}:
        pytest.fail(
            f"create-checkout-session unexpected HTTP {status} code={code} "
            f"(expected 200 with session url once Stripe prices + secret are on EF)"
        )
    if not body.get("url"):
        pytest.fail("create-checkout-session 200 without Checkout url")

    # Webhook must clear STRIPE_NOT_CONFIGURED once STRIPE_WEBHOOK_SECRET is on EF.
    # Unsigned body → signature failure is progress vs not-configured.
    wh_status, wh_body = _http_json(
        "POST",
        f"{CORE_FUNCTIONS_BASE}/stripe-webhook",
        body={"id": "evt_staging_probe"},
    )
    wh_code = str(wh_body.get("code") or "")
    if wh_code == "STRIPE_NOT_CONFIGURED":
        pytest.fail(
            "stripe-webhook still STRIPE_NOT_CONFIGURED — set STRIPE_WEBHOOK_SECRET "
            "on core EF secrets and redeploy stripe-webhook"
        )
    # Remaining hops (browser Checkout, Alpaca OAuth, overlay, digest) need
    # interactive Stripe + Mailgun accept — CLI documents them for the agent.
    assert status == 200
    assert wh_status != 0  # contacted
