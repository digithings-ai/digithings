"""Mailgun client fail-soft and suppression behavior."""

from __future__ import annotations

import pytest
from digiquant.notify.dispatch import _is_suppressed, _send_message
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


def test_send_message_transport_error_propagates() -> None:
    with pytest.raises(MailgunTransportError):
        _send_message(_RaisingClient(), "user@example.com", "s", "t", "h")


def test_suppressed_address_detected() -> None:
    assert _is_suppressed(_SuppressedClient(), "user@example.com") is True


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
        run_date=__import__("datetime").date(2026, 8, 30),
        hour_utc=12,
        force_digest=True,
    )


def test_suppression_before_claim_allows_retry() -> None:
    """Suppressed skip must not insert notification_log — unsuppress + retry can send."""
    from datetime import date

    from digiquant.notify.dispatch import dispatch_workspace

    from tests.dq.notify.conftest import FakeSupabase

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

    class _ToggleClient:
        def __init__(self) -> None:
            self.suppressed = True
            self.sent: list[str] = []

        def is_suppressed(self, email: str) -> bool:
            return self.suppressed

        def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
            self.sent.append(subject)

    client = _ToggleClient()
    pref = sb.tables["notification_prefs"][0]
    d = date(2026, 8, 30)
    dispatch_workspace(sb, client, cfg, pref, d, hour_utc=12, force_digest=True)
    assert client.sent == []
    assert sb.tables["notification_log"] == []

    client.suppressed = False
    dispatch_workspace(sb, client, cfg, pref, d, hour_utc=12, force_digest=True)
    assert len(client.sent) == 1
    assert len(sb.tables["notification_log"]) == 1


def test_missing_mailgun_env_names_empty_and_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.notify.mailgun import MAILGUN_NOT_CONFIGURED, missing_mailgun_env_names

    monkeypatch.delenv("MAILGUN_API_KEY", raising=False)
    monkeypatch.delenv("MAILGUN_DOMAIN", raising=False)
    monkeypatch.delenv("NOTIFY_FROM", raising=False)
    missing = missing_mailgun_env_names({})
    assert missing == ["MAILGUN_API_KEY", "MAILGUN_DOMAIN", "NOTIFY_FROM"]

    monkeypatch.setenv("MAILGUN_API_KEY", "EMPTY")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setenv("NOTIFY_FROM", "n@example.com")
    assert missing_mailgun_env_names() == ["MAILGUN_API_KEY"]

    from digiquant.notify.mailgun import MailgunNotConfiguredError, format_mailgun_not_configured

    msg = format_mailgun_not_configured(["MAILGUN_API_KEY"])
    assert MAILGUN_NOT_CONFIGURED in msg
    assert "MAILGUN_API_KEY" in msg
    with pytest.raises(MailgunNotConfiguredError) as ei:
        from digiquant.notify.mailgun import MailgunConfig

        MailgunConfig.require_from_env()
    assert ei.value.code == MAILGUN_NOT_CONFIGURED
    assert "MAILGUN_API_KEY" in ei.value.missing


def test_cli_require_mailgun_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from digiquant.notify import dispatch as dispatch_mod
    from digiquant.notify.mailgun import MAILGUN_NOT_CONFIGURED

    monkeypatch.delenv("MAILGUN_API_KEY", raising=False)
    monkeypatch.delenv("MAILGUN_DOMAIN", raising=False)
    monkeypatch.delenv("NOTIFY_FROM", raising=False)
    code = dispatch_mod.main(["--require-mailgun"])
    assert code == 2
    err = capsys.readouterr().err
    assert MAILGUN_NOT_CONFIGURED in err
    assert "MAILGUN_API_KEY" in err


def test_cli_require_mailgun_ok_when_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from digiquant.notify import dispatch as dispatch_mod

    monkeypatch.setenv("MAILGUN_API_KEY", "key-test")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setenv("NOTIFY_FROM", "n@example.com")
    code = dispatch_mod.main(["--check"])
    assert code == 0
    assert "Mailgun env present" in capsys.readouterr().out
