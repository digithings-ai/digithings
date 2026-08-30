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
from digiquant.olympus.kairos.staging_e2e import (
    OBSERVER_HOPS,
    REMAINING_LIVE_HOPS,
    HopExpectation,
    format_remaining_hops_failure,
    hop_ok,
    remaining_hops_unproven,
    resolve_staging_jwt,
    run_observer_hops,
    run_staging_e2e,
)
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "http", "code", "expected"),
    (
        (HopExpectation.READ_OK, 200, None, True),
        (HopExpectation.READ_OK, 401, "UNAUTHENTICATED", False),
        (HopExpectation.TIER_FORBIDDEN, 403, "TIER_FORBIDDEN", True),
        (HopExpectation.TIER_FORBIDDEN, 200, None, False),
        (HopExpectation.TIER_FORBIDDEN, 404, "NOT_FOUND", False),
        (HopExpectation.PRICE_OR_SESSION, 500, "PRICE_NOT_CONFIGURED", True),
        (HopExpectation.PRICE_OR_SESSION, 500, "STRIPE_NOT_CONFIGURED", True),
        (HopExpectation.PRICE_OR_SESSION, 500, "APP_URL_NOT_CONFIGURED", True),
        (HopExpectation.PRICE_OR_SESSION, 200, None, True),
        (HopExpectation.PRICE_OR_SESSION, 403, "TIER_FORBIDDEN", False),
        (HopExpectation.NOT_FOUND, 404, "NOT_FOUND", True),
        (HopExpectation.NOT_FOUND, 403, "TIER_FORBIDDEN", False),
    ),
)
def test_observer_hop_ok(kind: HopExpectation, http: int, code: str | None, expected: bool) -> None:
    assert hop_ok(kind, http, code) is expected


class _FakeHttp:
    """Method+path canned responses — never a live network."""

    def __init__(self, by_key: dict[tuple[str, str], tuple[int, dict[str, object]]]) -> None:
        self.by_key = by_key

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        del headers, body
        matches: list[tuple[int, tuple[int, dict[str, object]]]] = []
        for (m, suffix), payload in self.by_key.items():
            if m == method and url.rstrip("/").endswith(suffix):
                matches.append((len(suffix), payload))
        if not matches:
            return 599, {"code": "MISSING_FAKE"}
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]


def _observer_ok_fakes() -> dict[tuple[str, str], tuple[int, dict[str, object]]]:
    forbidden = (403, {"code": "TIER_FORBIDDEN"})
    return {
        ("GET", "/settings/profile"): (200, {"workspace_id": "ws"}),
        ("GET", "/settings/notifications"): (200, {"workspace_id": "ws"}),
        ("GET", "/settings/brokers"): (200, {"connections": []}),
        ("GET", "/settings/keys"): (200, {"keys": []}),
        ("PATCH", "/settings/profile"): forbidden,
        ("POST", "/settings/brokers/connect"): forbidden,
        ("POST", "/settings/keys/connect"): forbidden,
        ("POST", "/create-checkout-session"): (500, {"code": "PRICE_NOT_CONFIGURED"}),
        ("POST", "/settings/brokers"): (404, {"code": "NOT_FOUND"}),
    }


@pytest.mark.unit
def test_observer_hops_pass_on_core_contract() -> None:
    results = run_observer_hops(
        http=_FakeHttp(_observer_ok_fakes()),
        jwt="test-jwt",
        anon_key="anon",
        functions_base="https://example.test/functions/v1",
    )
    assert all(row.ok for row in results)
    forbidden = [row for row in results if row.kind is HopExpectation.TIER_FORBIDDEN]
    assert len(forbidden) == 3


@pytest.mark.unit
def test_observer_hops_fail_when_connect_is_not_forbidden() -> None:
    fakes = _observer_ok_fakes()
    fakes[("POST", "/settings/brokers/connect")] = (200, {"id": "should-not-seal"})
    results = run_observer_hops(
        http=_FakeHttp(fakes),
        jwt="test-jwt",
        anon_key=None,
        functions_base="https://example.test/functions/v1",
    )
    connect = next(row for row in results if row.label == "POST /settings/brokers/connect")
    assert connect.ok is False


@pytest.mark.unit
def test_run_staging_e2e_observer_pass_then_missing_secrets_exits_2() -> None:
    logs: list[str] = []
    rc = run_staging_e2e(
        http=_FakeHttp(_observer_ok_fakes()),
        environ={"KAIROS_STAGING_USER_JWT": "test-jwt"},
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == 2
    assert any("TIER_FORBIDDEN" in line or "Observer hops" in line for line in logs)
    assert any("STRIPE_SECRET_KEY" in line for line in logs)
    blob = "\n".join(logs)
    assert "KAIROS_STAGING_E2E_REMAINING_HOPS:" in blob
    assert "browser_stripe_checkout" in blob
    assert "digest_email_received" in blob


@pytest.mark.unit
def test_run_staging_e2e_observer_regression_exits_3() -> None:
    fakes = _observer_ok_fakes()
    fakes[("GET", "/settings/profile")] = (401, {"code": "UNAUTHENTICATED"})
    rc = run_staging_e2e(
        http=_FakeHttp(fakes),
        environ={"KAIROS_STAGING_USER_JWT": "test-jwt"},
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 3


@pytest.mark.unit
def test_resolve_staging_jwt_prefers_env_token() -> None:
    resolved = resolve_staging_jwt(
        http=_FakeHttp({}),
        environ={"KAIROS_STAGING_USER_JWT": "  abc  "},
    )
    assert resolved.token == "abc"
    assert resolved.attempted_grant is False


@pytest.mark.unit
def test_remaining_hops_unproven_filters_proven_map() -> None:
    assert remaining_hops_unproven() == REMAINING_LIVE_HOPS
    leftover = remaining_hops_unproven({"browser_stripe_checkout": True})
    assert leftover == REMAINING_LIVE_HOPS[1:]


@pytest.mark.unit
@pytest.mark.parametrize(
    "webhook",
    (
        (400, {"code": "SIGNATURE_INVALID"}),
        (200, {"received": True}),
        (502, {"code": "UPSTREAM"}),
        (400, {}),
    ),
)
def test_run_staging_e2e_checkout_url_is_not_complete_exits_4(
    webhook: tuple[int, dict[str, object]],
) -> None:
    """Secrets + checkout URL + any non-unconfigured webhook ≠ EPIC.md E2E complete."""
    wh_http, wh_body = webhook
    fakes = _observer_ok_fakes()
    fakes[("POST", "/create-checkout-session")] = (
        200,
        {"url": "https://checkout.stripe.test/cs_test"},
    )
    fakes[("POST", "/stripe-webhook")] = (wh_http, wh_body)
    environ = {name: f"test-placeholder-{name}" for name in KAIROS_STAGING_REQUIRED_SECRETS}
    environ["KAIROS_STAGING_USER_JWT"] = "test-jwt"
    logs: list[str] = []
    rc = run_staging_e2e(
        http=_FakeHttp(fakes),
        environ=environ,
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == 4
    assert rc != 0
    blob = "\n".join(logs)
    assert "KAIROS_STAGING_E2E_REMAINING_HOPS:" in blob
    for hop in (
        "browser_stripe_checkout",
        "alpaca_paper_oauth_connect",
        "overlay_daily_claimed",
        "paper_fill_mirrored",
        "digest_email_received",
    ):
        assert hop in blob


@pytest.mark.unit
def test_run_staging_e2e_password_grant_failure_exits_3() -> None:
    rc = run_staging_e2e(
        http=_FakeHttp(
            {("POST", "/auth/v1/token?grant_type=password"): (400, {"error": "invalid"})}
        ),
        environ={
            "KAIROS_STAGING_EMAIL": "user@example.test",
            "KAIROS_STAGING_PASSWORD": "not-logged",
            "CORE_SUPABASE_ANON_KEY": "anon",
        },
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 3


@pytest.mark.unit
def test_observer_connect_hops_omit_secret_fields() -> None:
    connect = [hop for hop in OBSERVER_HOPS if hop.kind is HopExpectation.TIER_FORBIDDEN]
    for hop in connect:
        body = hop.body or {}
        assert "secret" not in body
        assert "key_id" not in body


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
    # Remaining hops (browser Checkout, Alpaca OAuth, overlay, fill, digest)
    # are still unproven. Passing this mark after checkout would fake EPIC.md E2E.
    pytest.fail(
        format_remaining_hops_failure(remaining_hops_unproven())
        + f" (checkout HTTP {status}; webhook HTTP {wh_status})"
    )
