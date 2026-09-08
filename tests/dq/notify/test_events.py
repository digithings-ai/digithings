"""Holding-change and execution-alert event detectors."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.notify.events import (
    detect_execution_alerts,
    detect_holding_changes,
    holding_weight_change,
)
from digiquant.notify.mailgun import MailgunConfig

from tests.dq.notify.conftest import FakeSupabase

pytestmark = pytest.mark.unit

_CONFIG = MailgunConfig(
    api_key="k",
    domain="mg.example.com",
    from_address="n@example.com",
    unsubscribe_base="https://example.com/settings",
)


def test_holding_weight_change_semantics() -> None:
    assert holding_weight_change(10.0, None) == ("new", None)
    assert holding_weight_change(None, 5.0) == ("gone", None)
    assert holding_weight_change(12.0, 10.0)[0] == "increased"
    assert holding_weight_change(8.0, 10.0)[0] == "decreased"
    assert holding_weight_change(10.0, 10.0) == ("unchanged", 0.0)


def test_detect_holding_changes_new_and_trim() -> None:
    sb = FakeSupabase(
        tables={
            "positions": [
                {"workspace_id": "w1", "date": "2026-08-29", "ticker": "SPY", "weight_pct": 30.0},
                {"workspace_id": "w1", "date": "2026-08-30", "ticker": "SPY", "weight_pct": 35.0},
                {"workspace_id": "w1", "date": "2026-08-30", "ticker": "TLT", "weight_pct": 10.0},
            ],
        }
    )
    events = detect_holding_changes(sb, "w1", date(2026, 8, 30), _CONFIG)
    kinds = {e.ticker: e.change_kind for e in events}
    assert kinds["SPY"] == "increased"
    assert kinds["TLT"] == "new"


def test_detect_execution_alerts_from_mirror() -> None:
    sb = FakeSupabase(
        tables={
            "broker_executions": [
                {
                    "id": "fill-1",
                    "workspace_id": "w1",
                    "broker_order_id": "ord-1",
                    "symbol": "SPY",
                    "quantity": "10",
                    "price": "450.25",
                    "executed_at": "2026-08-30T14:00:00+00:00",
                    "recorded_at": "2026-08-30T14:00:01+00:00",
                }
            ],
            "broker_orders": [{"id": "ord-1", "side": "buy"}],
        }
    )
    events = detect_execution_alerts(sb, "w1", date(2026, 8, 30), _CONFIG)
    assert len(events) == 1
    assert events[0].event_key == "execution:fill-1"
    assert events[0].symbol == "SPY"
    assert "workspace=w1" in events[0].unsubscribe_url
