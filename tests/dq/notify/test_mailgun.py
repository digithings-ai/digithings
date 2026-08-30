"""Mailgun client fail-soft and suppression behavior."""

from __future__ import annotations

import pytest
from digiquant.notify.dispatch import _send_if_allowed
from digiquant.notify.mailgun import MailgunConfig, MailgunTransportError, unsubscribe_url

pytestmark = pytest.mark.unit


class _RaisingClient:
    def is_suppressed(self, email: str) -> bool:
        return False

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        raise MailgunTransportError("transport down")


class _SuppressedClient:
    def is_suppressed(self, email: str) -> bool:
        return True

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        raise AssertionError("must not send when suppressed")


def test_send_if_allowed_transport_error_propagates() -> None:
    with pytest.raises(MailgunTransportError):
        _send_if_allowed(_RaisingClient(), "user@example.com", "s", "t", "h")


def test_suppressed_address_skipped() -> None:
    assert _send_if_allowed(_SuppressedClient(), "user@example.com", "s", "t", "h") is False


def test_unsubscribe_url_placeholder() -> None:
    cfg = MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://digiquant.io/olympus/settings/notifications",
    )
    url = unsubscribe_url("abc-workspace", cfg)
    assert url == "https://digiquant.io/olympus/settings/notifications?workspace=abc-workspace"


def test_dispatch_fail_soft_on_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raising transport ⇒ dispatch returns cleanly (no exception)."""
    from digiquant.notify import dispatch as dispatch_mod

    class _BrokenInner:
        def is_suppressed(self, email: str) -> bool:
            return False

        def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
            raise MailgunTransportError("boom")

    cfg = MailgunConfig(
        api_key="k",
        domain="mg.example.com",
        from_address="n@example.com",
        unsubscribe_base="https://example.com/settings",
    )

    from tests.dq.notify.conftest import FakeSupabase

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
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral"}}}
            ],
        }
    )

    monkeypatch.setattr(dispatch_mod, "build_digiquant_client", lambda: sb)
    monkeypatch.setattr(dispatch_mod.MailgunConfig, "from_env", lambda: cfg)
    monkeypatch.setattr(dispatch_mod, "build_mailgun_client", lambda: _BrokenInner())

    dispatch_mod.dispatch_notifications(
        run_date=__import__("datetime").date(2026, 8, 30), hour_utc=None
    )
