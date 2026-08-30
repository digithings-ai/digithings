"""Dedupe and dispatch integration tests."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.notify.dispatch import (
    dispatch_workspace,
    format_digest_dry_run,
    main,
    plan_digest_dispatch,
    try_claim_send_slot,
)
from digiquant.notify.mailgun import MailgunConfig

from tests.dq.notify.conftest import FakeSupabase

pytestmark = pytest.mark.unit


class _RecordingClient:
    def __init__(self, suppressed: bool = False) -> None:
        self.suppressed = suppressed
        self.sent: list[str] = []

    def is_suppressed(self, email: str) -> bool:
        return self.suppressed

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        self.sent.append(subject)


def test_try_claim_send_slot_dedupes() -> None:
    sb = FakeSupabase(tables={"notification_log": []})
    d = date(2026, 8, 30)
    assert try_claim_send_slot(sb, "w1", "digest:2026-08-30", d) is True
    assert try_claim_send_slot(sb, "w1", "digest:2026-08-30", d) is False


def test_dispatch_retry_is_noop() -> None:
    cfg = MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://example.com/settings",
    )
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": True,
                    "holding_change_alerts": False,
                    "execution_alerts": False,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": "free", "name": "House"}],
            "daily_snapshots": [
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral", "summary": "ok"}}}
            ],
            "notification_log": [
                {
                    "workspace_id": "w1",
                    "event_key": "digest:2026-08-30",
                    "sent_date": "2026-08-30",
                }
            ],
        }
    )
    client = _RecordingClient()
    pref = sb.tables["notification_prefs"][0]
    dispatch_workspace(sb, client, cfg, pref, date(2026, 8, 30), hour_utc=12, force_digest=True)
    assert client.sent == []


def test_force_digest_bypasses_hour_gate() -> None:
    cfg = MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://example.com/settings",
    )
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": True,
                    "holding_change_alerts": False,
                    "execution_alerts": False,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": "free", "name": "House"}],
            "daily_snapshots": [
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral", "summary": "ok"}}}
            ],
            "notification_log": [],
        }
    )
    client = _RecordingClient()
    pref = sb.tables["notification_prefs"][0]
    # Hour 8 ≠ digest_hour 12 — without force_digest, no send.
    dispatch_workspace(sb, client, cfg, pref, date(2026, 8, 30), hour_utc=8, force_digest=False)
    assert client.sent == []
    dispatch_workspace(sb, client, cfg, pref, date(2026, 8, 30), hour_utc=8, force_digest=True)
    assert len(client.sent) == 1


def test_cron_hour_gate_blocks_wrong_hour() -> None:
    cfg = MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://example.com/settings",
    )
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": True,
                    "holding_change_alerts": False,
                    "execution_alerts": False,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": "free", "name": "House"}],
            "daily_snapshots": [
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral", "summary": "ok"}}}
            ],
            "notification_log": [],
        }
    )
    client = _RecordingClient()
    pref = sb.tables["notification_prefs"][0]
    dispatch_workspace(sb, client, cfg, pref, date(2026, 8, 30), hour_utc=12, force_digest=False)
    assert len(client.sent) == 1


def test_plan_digest_dispatch_matches_workspace_gate() -> None:

    plan = plan_digest_dispatch(
        [
            {
                "workspace_id": "observer",
                "email": "obs@example.com",
                "daily_digest": True,
            },
            {
                "workspace_id": "off",
                "email": "off@example.com",
                "daily_digest": False,
            },
            {"workspace_id": "blank", "email": "", "daily_digest": True},
        ],
        mailgun_configured=False,
    )
    assert plan.considered == 3
    assert plan.digest_on == 1
    assert plan.skipped_prefs_off == 1
    assert plan.skipped_no_email == 1
    assert plan.mailgun_configured is False
    line = format_digest_dry_run(plan)
    assert "digest_on=1" in line
    assert "mailgun_configured=0" in line
    assert "@" not in line

    filtered = plan_digest_dispatch(
        [
            {
                "workspace_id": "observer",
                "email": "obs@example.com",
                "daily_digest": True,
            },
            {
                "workspace_id": "off",
                "email": "off@example.com",
                "daily_digest": False,
            },
        ],
        mailgun_configured=False,
        workspace_id="observer",
    )
    assert filtered.considered == 1
    assert filtered.digest_on == 1

    captured: list[str] = []
    rc = main(
        ["--dry-run", "--workspace-id", "observer"],
        prefs=[
            {
                "workspace_id": "observer",
                "email": "obs@example.com",
                "daily_digest": True,
            }
        ],
        mailgun_configured=False,
        log=captured.append,
    )
    assert rc == 0
    assert captured == [
        "notify dry-run considered=1 digest_on=1 skipped_prefs_off=0 skipped_no_email=0 mailgun_configured=0"
    ]


def test_dry_run_never_dispatches_or_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not dispatch or claim notification_log")

    monkeypatch.setattr("digiquant.notify.dispatch._dispatch_with_client", boom)
    monkeypatch.setattr("digiquant.notify.dispatch.try_claim_send_slot", boom)
    rc = main(
        ["--dry-run", "--workspace-id", "observer"],
        prefs=[
            {
                "workspace_id": "observer",
                "email": "obs@example.com",
                "daily_digest": True,
            }
        ],
        mailgun_configured=True,
        log=lambda _line: None,
    )
    assert rc == 0
