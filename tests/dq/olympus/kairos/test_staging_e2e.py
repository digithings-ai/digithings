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
from digiquant.olympus.kairos.remaining_hops import (
    RemainingHopEvidence,
    proven_remaining_hops,
    remaining_hop_blockers,
)
from digiquant.olympus.kairos.staging_e2e import (
    OBSERVER_HOPS,
    REDEEM_INVITE_MOUNTED_CODES,
    REMAINING_LIVE_HOPS,
    STAGING_CHECKOUT_BODY,
    STAGING_REDEEM_INVITE_BODY,
    HopExpectation,
    collect_remaining_evidence,
    format_remaining_hops_failure,
    hop_ok,
    public_app_urls_ok,
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
        (HopExpectation.PUBLIC_URLS_OK, 200, None, False),
        (HopExpectation.PREFS_DIGEST_ON, 200, None, False),
        (HopExpectation.PREFS_DIGEST_ON, 403, "TIER_FORBIDDEN", False),
        (HopExpectation.REDEEM_INVITE_MOUNTED, 403, "INVITE_INVALID", True),
        (HopExpectation.REDEEM_INVITE_MOUNTED, 400, "EMAIL_REQUIRED", True),
        (HopExpectation.REDEEM_INVITE_MOUNTED, 404, "NOT_FOUND", False),
        (HopExpectation.REDEEM_INVITE_MOUNTED, 200, None, False),
        (HopExpectation.REDEEM_INVITE_MOUNTED, 429, "INVITE_RATE_LIMIT", False),
    ),
)
def test_observer_hop_ok(kind: HopExpectation, http: int, code: str | None, expected: bool) -> None:
    assert hop_ok(kind, http, code) is expected


@pytest.mark.unit
def test_prefs_digest_on_requires_daily_digest_true() -> None:
    assert hop_ok(HopExpectation.PREFS_DIGEST_ON, 200, None, {"daily_digest": True}) is True
    assert hop_ok(HopExpectation.PREFS_DIGEST_ON, 200, None, {"daily_digest": False}) is False
    assert hop_ok(HopExpectation.PREFS_DIGEST_ON, 200, None, {}) is False


@pytest.mark.unit
def test_staging_checkout_is_custom_not_baseline() -> None:
    """Broker/overlay/fill remaining hops are Custom+; Baseline would dead-end Observer."""
    assert STAGING_CHECKOUT_BODY == {"tier": "custom", "interval": "monthly"}
    hop = next(row for row in OBSERVER_HOPS if row.path == "/create-checkout-session")
    assert hop.body == STAGING_CHECKOUT_BODY
    assert hop.body is not None
    assert hop.body.get("tier") != "baseline"


@pytest.mark.unit
def test_redeem_invite_hop_uses_short_code_without_secrets() -> None:
    """Short dummy must not grant, hash, or count toward INVITE_MAX_ATTEMPTS."""
    hop = next(row for row in OBSERVER_HOPS if row.path == "/settings/access/redeem-invite")
    assert hop.method == "POST"
    assert hop.kind is HopExpectation.REDEEM_INVITE_MOUNTED
    assert hop.body == STAGING_REDEEM_INVITE_BODY
    code = str(STAGING_REDEEM_INVITE_BODY["code"])
    assert len(code) < 10
    assert hop.body is not None
    assert set(hop.body) == {"code"}
    assert "INVITE_INVALID" in REDEEM_INVITE_MOUNTED_CODES
    assert "EMAIL_REQUIRED" in REDEEM_INVITE_MOUNTED_CODES


@pytest.mark.unit
def test_observer_hops_fail_when_redeem_invite_is_missing() -> None:
    fakes = _observer_ok_fakes()
    fakes[("POST", "/settings/access/redeem-invite")] = (404, {"code": "NOT_FOUND"})
    results = run_observer_hops(
        http=_FakeHttp(fakes),
        jwt="test-jwt",
        anon_key="anon",
        functions_base="https://example.test/functions/v1",
    )
    redeem = next(row for row in results if row.kind is HopExpectation.REDEEM_INVITE_MOUNTED)
    assert redeem.ok is False
    assert redeem.http == 404


@pytest.mark.unit
def test_run_staging_e2e_redeem_invite_404_exits_3() -> None:
    fakes = _observer_ok_fakes()
    fakes[("POST", "/settings/access/redeem-invite")] = (404, {"code": "NOT_FOUND"})
    logs: list[str] = []
    rc = run_staging_e2e(
        http=_FakeHttp(fakes),
        environ={"KAIROS_STAGING_USER_JWT": "test-jwt"},
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == 3
    blob = "\n".join(logs)
    assert "redeem-invite not mounted" in blob
    assert "POST /settings/access/redeem-invite http=404" in blob


@pytest.mark.unit
def test_public_app_urls_ok_requires_digiquant_origin() -> None:
    good = {
        "alpaca_redirect_uri": "https://digiquant.io/dashboard/settings/brokers/callback/",
        "billing_return_url": "https://digiquant.io/dashboard/settings/?tab=billing",
    }
    assert public_app_urls_ok(200, good) is True
    loopback = {
        **good,
        "alpaca_redirect_uri": "http://127.0.0.1:3001/dashboard/settings/brokers/callback/",
    }
    assert public_app_urls_ok(200, loopback) is False
    named_loopback = {
        **good,
        "billing_return_url": "http://localhost:3001/dashboard/settings/?tab=billing",
    }
    assert public_app_urls_ok(200, named_loopback) is False
    missing_dashboard = {
        **good,
        "billing_return_url": "https://digiquant.io/settings/billing",
    }
    assert public_app_urls_ok(200, missing_dashboard) is False
    extra_public_client = {
        **good,
        "alpaca_oauth_client_id": "cid-public",
    }
    assert public_app_urls_ok(200, extra_public_client) is True
    retired_olympus = {
        "alpaca_redirect_uri": "https://digiquant.io/olympus/settings/brokers/callback/",
        "billing_return_url": "https://digiquant.io/olympus/settings/?tab=billing",
    }
    assert public_app_urls_ok(200, retired_olympus) is False
    mixed_olympus_billing = {
        **good,
        "billing_return_url": "https://digiquant.io/olympus/settings/?tab=billing",
    }
    assert public_app_urls_ok(200, mixed_olympus_billing) is False


class _FakeHttp:
    """Method+path canned responses — never a live network."""

    def __init__(self, by_key: dict[tuple[str, str], tuple[int, dict[str, object]]]) -> None:
        self.by_key = by_key
        self.bodies: list[tuple[str, str, dict[str, object] | None]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        del headers
        self.bodies.append((method, url, body))
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
        ("GET", "/settings/notifications"): (
            200,
            {"workspace_id": "ws", "daily_digest": True},
        ),
        ("GET", "/settings/notifications/log"): (200, {"events": []}),
        ("PATCH", "/settings/notifications"): (200, {"daily_digest": True}),
        ("GET", "/settings/brokers"): (200, {"connections": []}),
        ("GET", "/settings/keys"): (200, {"keys": []}),
        ("GET", "/settings/app-urls"): (
            200,
            {
                "alpaca_redirect_uri": "https://digiquant.io/dashboard/settings/brokers/callback/",
                "billing_return_url": "https://digiquant.io/dashboard/settings/?tab=billing",
            },
        ),
        ("GET", "/settings/jobs"): (200, {"jobs": []}),
        ("GET", "/settings/fills"): (200, {"fills": []}),
        ("PATCH", "/settings/profile"): forbidden,
        ("POST", "/settings/brokers/connect"): forbidden,
        ("POST", "/settings/keys/connect"): forbidden,
        ("POST", "/create-checkout-session"): (500, {"code": "PRICE_NOT_CONFIGURED"}),
        ("POST", "/settings/brokers"): (404, {"code": "NOT_FOUND"}),
        ("POST", "/settings/access/redeem-invite"): (403, {"code": "INVITE_INVALID"}),
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
    assert "blocker=plan_tier_not_custom" in blob
    assert "blocker=no_alpaca_paper_oauth" in blob
    assert "blocker=overlay_not_succeeded" in blob
    assert "blocker=no_paper_fill" in blob
    assert "blocker=no_digest_log" in blob


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
def test_proven_remaining_hops_ops_custom_none_does_not_count_as_stripe() -> None:
    proven = proven_remaining_hops(RemainingHopEvidence(subscription_status="none"))
    assert proven["browser_stripe_checkout"] is False
    assert remaining_hops_unproven(proven) == REMAINING_LIVE_HOPS
    # Live ops-custom workspace is plan_tier=custom with subscription_status=none
    # and no Stripe ids — grant/ops custom must not prove checkout.
    grant = proven_remaining_hops(
        RemainingHopEvidence(
            plan_tier="custom",
            subscription_status="none",
            has_stripe_subscription=False,
        )
    )
    assert grant["browser_stripe_checkout"] is False


@pytest.mark.unit
def test_proven_remaining_hops_house_active_without_stripe_does_not_count() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(subscription_status="active", has_stripe_subscription=False)
    )
    assert proven["browser_stripe_checkout"] is False


@pytest.mark.unit
def test_proven_remaining_hops_baseline_stripe_does_not_count() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(
            subscription_status="active",
            has_stripe_subscription=True,
            plan_tier="baseline",
        )
    )
    assert proven["browser_stripe_checkout"] is False
    custom = proven_remaining_hops(
        RemainingHopEvidence(
            subscription_status="active",
            has_stripe_subscription=True,
            plan_tier="custom",
        )
    )
    assert custom["browser_stripe_checkout"] is True


@pytest.mark.unit
def test_proven_remaining_hops_digest_log_without_inbox_is_not_received() -> None:
    proven = proven_remaining_hops(RemainingHopEvidence(digest_event_keys=("digest:2026-08-31",)))
    assert proven["digest_email_received"] is False


@pytest.mark.unit
def test_proven_remaining_hops_digest_requires_pref_on() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(
            digest_event_keys=("digest:2026-08-31",),
            digest_inbox_confirmed=True,
            daily_digest_enabled=False,
        )
    )
    assert proven["digest_email_received"] is False
    on = proven_remaining_hops(
        RemainingHopEvidence(
            digest_event_keys=("digest:2026-08-31",),
            digest_inbox_confirmed=True,
            daily_digest_enabled=True,
        )
    )
    assert on["digest_email_received"] is True


@pytest.mark.unit
def test_proven_remaining_hops_skipped_overlay_is_not_claimed() -> None:
    skipped = proven_remaining_hops(RemainingHopEvidence(jobs=(("overlay_daily", "skipped"),)))
    assert skipped["overlay_daily_claimed"] is False
    not_entitled = proven_remaining_hops(
        RemainingHopEvidence(jobs=(("overlay_daily", "not_entitled"),))
    )
    assert not_entitled["overlay_daily_claimed"] is False
    running = proven_remaining_hops(RemainingHopEvidence(jobs=(("overlay_daily", "running"),)))
    assert running["overlay_daily_claimed"] is False
    persist_disabled = proven_remaining_hops(
        RemainingHopEvidence(jobs=(("overlay_daily", "persist_disabled"),))
    )
    assert persist_disabled["overlay_daily_claimed"] is False
    succeeded = proven_remaining_hops(RemainingHopEvidence(jobs=(("overlay_daily", "succeeded"),)))
    assert succeeded["overlay_daily_claimed"] is True


@pytest.mark.unit
def test_proven_remaining_hops_alpaca_live_does_not_count_as_paper() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(connections=(("alpaca", "live", "active", "oauth"),))
    )
    assert proven["alpaca_paper_oauth_connect"] is False


@pytest.mark.unit
def test_proven_remaining_hops_alpaca_api_key_does_not_count_as_oauth() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(connections=(("alpaca", "paper", "active", "api_key"),))
    )
    assert proven["alpaca_paper_oauth_connect"] is False


@pytest.mark.unit
def test_proven_remaining_hops_fill_without_oauth_is_not_mirrored() -> None:
    api_key_fill = proven_remaining_hops(
        RemainingHopEvidence(
            connections=(("alpaca", "paper", "active", "api_key"),),
            fill_count=1,
        )
    )
    assert api_key_fill["paper_fill_mirrored"] is False
    assert api_key_fill["alpaca_paper_oauth_connect"] is False
    fill_only = proven_remaining_hops(RemainingHopEvidence(fill_count=1))
    assert fill_only["paper_fill_mirrored"] is False
    oauth_fill = proven_remaining_hops(
        RemainingHopEvidence(
            connections=(("alpaca", "paper", "active", "oauth"),),
            fill_count=1,
        )
    )
    assert oauth_fill["paper_fill_mirrored"] is True
    assert oauth_fill["alpaca_paper_oauth_connect"] is True


@pytest.mark.unit
def test_proven_remaining_hops_all_five_from_product_state() -> None:
    proven = proven_remaining_hops(
        RemainingHopEvidence(
            subscription_status="active",
            has_stripe_subscription=True,
            plan_tier="custom",
            connections=(("alpaca", "paper", "active", "oauth"),),
            jobs=(("overlay_daily", "succeeded"),),
            fill_count=1,
            digest_event_keys=("digest:2026-08-31",),
            digest_inbox_confirmed=True,
            daily_digest_enabled=True,
        )
    )
    assert remaining_hops_unproven(proven) == ()
    assert all(proven[name] for name in REMAINING_LIVE_HOPS)
    assert (
        remaining_hop_blockers(
            RemainingHopEvidence(
                subscription_status="active",
                has_stripe_subscription=True,
                plan_tier="custom",
                connections=(("alpaca", "paper", "active", "oauth"),),
                jobs=(("overlay_daily", "succeeded"),),
                fill_count=1,
                digest_event_keys=("digest:2026-08-31",),
                digest_inbox_confirmed=True,
                daily_digest_enabled=True,
            )
        )
        == {}
    )


@pytest.mark.unit
def test_remaining_hop_blockers_observer_and_house_gates() -> None:
    observer = remaining_hop_blockers(
        RemainingHopEvidence(
            plan_tier="free",
            subscription_status="none",
            connections=(("alpaca", "paper", "active", "api_key"),),
            fill_count=1,
            digest_event_keys=("digest:2026-08-31",),
            daily_digest_enabled=True,
        )
    )
    assert observer["browser_stripe_checkout"] == "plan_tier_not_custom"
    assert observer["alpaca_paper_oauth_connect"] == "alpaca_api_key_not_oauth"
    assert observer["overlay_daily_claimed"] == "overlay_not_succeeded"
    assert observer["paper_fill_mirrored"] == "fill_without_oauth"
    assert observer["digest_email_received"] == "digest_inbox_unconfirmed"
    house = remaining_hop_blockers(
        RemainingHopEvidence(
            plan_tier="enterprise",
            subscription_status="active",
            has_stripe_subscription=False,
        )
    )
    assert house["browser_stripe_checkout"] == "missing_stripe_ids"
    grant = remaining_hop_blockers(
        RemainingHopEvidence(
            plan_tier="custom",
            subscription_status="none",
            has_stripe_subscription=False,
        )
    )
    assert grant["browser_stripe_checkout"] == "missing_stripe_ids"
    persist = remaining_hop_blockers(
        RemainingHopEvidence(jobs=(("overlay_daily", "persist_disabled"),))
    )
    assert persist["overlay_daily_claimed"] == "overlay_persist_disabled"


@pytest.mark.unit
def test_collect_remaining_evidence_reads_member_scoped_settings() -> None:
    fakes = _observer_ok_fakes()
    fakes[("GET", "/settings/profile")] = (
        200,
        {"workspace_id": "ws", "subscription_status": "none", "plan_tier": "ops-custom"},
    )
    evidence = collect_remaining_evidence(
        http=_FakeHttp(fakes),
        jwt="test-jwt",
        anon_key=None,
        functions_base="https://example.test/functions/v1",
    )
    assert evidence.subscription_status == "none"
    assert evidence.plan_tier == "ops-custom"
    assert evidence.has_stripe_subscription is False
    assert evidence.fill_count == 0
    assert evidence.daily_digest_enabled is True
    assert evidence.surface_http_ok is True
    assert proven_remaining_hops(evidence)["browser_stripe_checkout"] is False


@pytest.mark.unit
def test_collect_remaining_evidence_ignores_fills_without_symbol() -> None:
    fakes = _observer_ok_fakes()
    fakes[("GET", "/settings/fills")] = (200, {"fills": [{}, {"symbol": ""}]})
    evidence = collect_remaining_evidence(
        http=_FakeHttp(fakes),
        jwt="test-jwt",
        anon_key=None,
        functions_base="https://example.test/functions/v1",
    )
    assert evidence.fill_count == 0


@pytest.mark.unit
def test_run_staging_e2e_remaining_hop_surface_503_exits_3() -> None:
    fakes = _observer_ok_fakes()
    fakes[("GET", "/settings/jobs")] = (503, {"code": "NOT_READY"})
    rc = run_staging_e2e(
        http=_FakeHttp(fakes),
        environ={"KAIROS_STAGING_USER_JWT": "test-jwt"},
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 3


@pytest.mark.unit
def test_run_staging_e2e_exit_0_when_product_state_proves_remaining_hops() -> None:
    fakes = _observer_ok_fakes()
    fakes[("GET", "/settings/profile")] = (
        200,
        {
            "workspace_id": "ws",
            "subscription_status": "active",
            "plan_tier": "custom",
            "has_stripe_subscription": True,
        },
    )
    fakes[("GET", "/settings/brokers")] = (
        200,
        {
            "connections": [
                {"broker": "alpaca", "env": "paper", "status": "active", "auth_kind": "oauth"}
            ]
        },
    )
    fakes[("GET", "/settings/jobs")] = (
        200,
        {"jobs": [{"job_type": "overlay_daily", "status": "succeeded"}]},
    )
    fakes[("GET", "/settings/fills")] = (200, {"fills": [{"id": "f1", "symbol": "AAPL"}]})
    fakes[("GET", "/settings/notifications/log")] = (
        200,
        {"events": [{"event_key": "digest:2026-08-31"}]},
    )
    logs: list[str] = []
    rc = run_staging_e2e(
        http=_FakeHttp(fakes),
        environ={
            "KAIROS_STAGING_USER_JWT": "test-jwt",
            "KAIROS_STAGING_DIGEST_INBOX_CONFIRMED": "1",
        },
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == 0
    blob = "\n".join(logs)
    assert "all remaining hops proven" in blob
    assert "KAIROS_STAGING_E2E_REMAINING_HOPS:" not in blob


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
    fake = _FakeHttp(fakes)
    rc = run_staging_e2e(
        http=fake,
        environ=environ,
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == 4
    assert rc != 0
    checkout_bodies = [
        body
        for method, url, body in fake.bodies
        if method == "POST" and url.rstrip("/").endswith("/create-checkout-session")
    ]
    assert checkout_bodies
    assert all(body == STAGING_CHECKOUT_BODY for body in checkout_bodies)
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
        body=STAGING_CHECKOUT_BODY,
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
