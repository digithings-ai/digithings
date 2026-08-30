"""Dedupe and dispatch integration tests."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.notify.dispatch import dispatch_workspace, try_claim_send_slot
from digiquant.notify.mailgun import MailgunConfig

from tests.dq.notify.conftest import FakeSupabase

pytestmark = pytest.mark.unit


class _RecordingClient:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def is_suppressed(self, email: str) -> bool:
        return False

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        self.sent.append(subject)


def test_try_claim_send_slot_dedupes() -> None:
    sb = FakeSupabase(tables={"notification_log": []})
    d = date(2026, 8, 30)
    assert try_claim_send_slot(sb, "w1", "digest:2026-08-30", d) is True
    assert try_claim_send_slot(sb, "w1", "digest:2026-08-30", d) is False


def test_dispatch_retry_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
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
    dispatch_workspace(sb, client, cfg, pref, date(2026, 8, 30), hour_utc=None)
    assert client.sent == []
