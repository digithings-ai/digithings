"""Tier gates for holding-change and execution-alert dispatch."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.notify.dispatch import dispatch_workspace
from digiquant.notify.entitlements import PlanTier
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


def _cfg() -> MailgunConfig:
    return MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://example.com/settings",
    )


def test_observer_skips_holding_and_execution_alerts() -> None:
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": False,
                    "holding_change_alerts": True,
                    "execution_alerts": True,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": PlanTier.FREE.value, "name": "House"}],
            "positions": [
                {"workspace_id": "w1", "date": "2026-08-29", "ticker": "SPY", "weight_pct": 10.0},
                {"workspace_id": "w1", "date": "2026-08-30", "ticker": "SPY", "weight_pct": 15.0},
            ],
            "broker_executions": [
                {
                    "id": "fill-1",
                    "workspace_id": "w1",
                    "broker_order_id": "ord-1",
                    "symbol": "SPY",
                    "quantity": "1",
                    "price": "100",
                    "executed_at": "2026-08-30T14:00:00+00:00",
                    "recorded_at": "2026-08-30T14:00:01+00:00",
                }
            ],
            "broker_orders": [{"id": "ord-1", "side": "buy"}],
            "notification_log": [],
        }
    )
    client = _RecordingClient()
    dispatch_workspace(
        sb,
        client,
        _cfg(),
        sb.tables["notification_prefs"][0],
        date(2026, 8, 30),
        hour_utc=12,
    )
    assert client.sent == []


def test_baseline_gets_holding_change_not_execution() -> None:
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": False,
                    "holding_change_alerts": True,
                    "execution_alerts": True,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": PlanTier.BASELINE.value, "name": "House"}],
            "positions": [
                {"workspace_id": "w1", "date": "2026-08-29", "ticker": "SPY", "weight_pct": 10.0},
                {"workspace_id": "w1", "date": "2026-08-30", "ticker": "SPY", "weight_pct": 15.0},
            ],
            "broker_executions": [
                {
                    "id": "fill-1",
                    "workspace_id": "w1",
                    "broker_order_id": "ord-1",
                    "symbol": "SPY",
                    "quantity": "1",
                    "price": "100",
                    "executed_at": "2026-08-30T14:00:00+00:00",
                    "recorded_at": "2026-08-30T14:00:01+00:00",
                }
            ],
            "broker_orders": [{"id": "ord-1", "side": "buy"}],
            "notification_log": [],
        }
    )
    client = _RecordingClient()
    dispatch_workspace(
        sb,
        client,
        _cfg(),
        sb.tables["notification_prefs"][0],
        date(2026, 8, 30),
        hour_utc=12,
    )
    assert len(client.sent) == 1
    assert "Holding change" in client.sent[0]


def test_custom_gets_execution_alerts() -> None:
    sb = FakeSupabase(
        tables={
            "notification_prefs": [
                {
                    "workspace_id": "w1",
                    "email": "ops@example.com",
                    "daily_digest": False,
                    "holding_change_alerts": False,
                    "execution_alerts": True,
                    "digest_hour_utc": 12,
                }
            ],
            "workspaces": [{"id": "w1", "plan_tier": PlanTier.CUSTOM.value, "name": "House"}],
            "broker_executions": [
                {
                    "id": "fill-1",
                    "workspace_id": "w1",
                    "broker_order_id": "ord-1",
                    "symbol": "SPY",
                    "quantity": "1",
                    "price": "100",
                    "executed_at": "2026-08-30T14:00:00+00:00",
                    "recorded_at": "2026-08-30T14:00:01+00:00",
                }
            ],
            "broker_orders": [{"id": "ord-1", "side": "buy"}],
            "notification_log": [],
        }
    )
    client = _RecordingClient()
    dispatch_workspace(
        sb,
        client,
        _cfg(),
        sb.tables["notification_prefs"][0],
        date(2026, 8, 30),
        hour_utc=12,
        execution_alerts_only=True,
    )
    assert len(client.sent) == 1
    assert "Execution alert" in client.sent[0]
