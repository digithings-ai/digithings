"""Cloudflare Email Sending client fail-soft, HTTP shape, and env behavior."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.error import HTTPError

import pytest
from digiquant.notify import cloudflare_email as cf_mod
from digiquant.notify.cloudflare_email import (
    CloudflareEmailClient,
    CloudflareEmailConfig,
    EmailSuppressedError,
    EmailTransportError,
    NotifyNotConfiguredError,
    format_notify_not_configured,
    missing_notify_env_names,
    split_from_address,
    unsubscribe_url,
)
from digiquant.notify.dispatch import _is_suppressed, _send_message

pytestmark = pytest.mark.unit


def _config(**overrides: object) -> CloudflareEmailConfig:
    base: dict[str, object] = {
        "api_token": "token-test",
        "account_id": "acct-123",
        "from_address": "noreply@example.com",
        "unsubscribe_base": "https://example.com/settings",
        "from_name": None,
    }
    base.update(overrides)
    return CloudflareEmailConfig(**base)  # type: ignore[arg-type]


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _Capture:
    """Stand-in for ``urlopen`` that records the request and returns 200 success."""

    def __init__(self, body: bytes = b'{"success": true}') -> None:
        self.body = body
        self.request: object | None = None

    def __call__(self, req: object, timeout: int | None = None) -> _FakeResponse:
        del timeout
        self.request = req
        return _FakeResponse(200, self.body)


class _RaisingClient:
    def is_suppressed(self, email: str) -> bool:
        return False

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        raise EmailTransportError("transport down")


class _SuppressedClient:
    def is_suppressed(self, email: str) -> bool:
        return True

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        raise AssertionError("must not send when suppressed")


def test_send_message_transport_error_propagates() -> None:
    with pytest.raises(EmailTransportError):
        _send_message(_RaisingClient(), "user@example.com", "s", "t", "h")


def test_suppressed_address_detected() -> None:
    assert _is_suppressed(_SuppressedClient(), "user@example.com") is True


def test_is_suppressed_is_service_side_no_op() -> None:
    assert CloudflareEmailClient(_config()).is_suppressed("user@example.com") is False


def test_unsubscribe_url_placeholder() -> None:
    cfg = _config(
        from_address="n@example.com",
        unsubscribe_base="https://digiquant.io/dashboard/settings/notifications",
    )
    url = unsubscribe_url("abc-workspace", cfg)
    assert url == "https://digiquant.io/dashboard/settings/notifications?workspace=abc-workspace"


def test_split_from_address_named_and_bare() -> None:
    assert split_from_address("Digiquant <noreply@example.com>") == (
        "noreply@example.com",
        "Digiquant",
    )
    assert split_from_address("noreply@example.com") == ("noreply@example.com", None)


def test_send_posts_cloudflare_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _Capture()
    monkeypatch.setattr(cf_mod, "urlopen", captured)
    CloudflareEmailClient(_config()).send_message(
        to="user@example.com",
        subject="Hi",
        text_body="plain",
        html_body="<p>html</p>",
    )
    req = captured.request
    assert req is not None
    assert req.full_url == (  # type: ignore[attr-defined]
        "https://api.cloudflare.com/client/v4/accounts/acct-123/email/sending/send"
    )
    assert req.get_method() == "POST"  # type: ignore[attr-defined]
    assert req.get_header("Authorization") == "Bearer token-test"  # type: ignore[attr-defined]
    assert req.get_header("Content-type") == "application/json"  # type: ignore[attr-defined]
    payload = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
    assert payload == {
        "to": "user@example.com",
        "from": "noreply@example.com",
        "subject": "Hi",
        "text": "plain",
        "html": "<p>html</p>",
    }


def test_from_field_named_sends_object_bare_sends_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _Capture()
    monkeypatch.setattr(cf_mod, "urlopen", captured)
    named = _config(from_address="noreply@example.com", from_name="Digiquant")
    CloudflareEmailClient(named).send_message("u@example.com", "s", "t", "h")
    payload = json.loads(captured.request.data)  # type: ignore[attr-defined]
    assert payload["from"] == {"address": "noreply@example.com", "name": "Digiquant"}

    bare = _config(from_address="noreply@example.com", from_name=None)
    CloudflareEmailClient(bare).send_message("u@example.com", "s", "t", "h")
    payload = json.loads(captured.request.data)  # type: ignore[attr-defined]
    assert payload["from"] == "noreply@example.com"


def test_200_with_success_false_raises_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {"success": False, "errors": [{"code": 10102, "message": "forbidden"}]}
    ).encode()
    monkeypatch.setattr(cf_mod, "urlopen", _Capture(body))
    with pytest.raises(EmailTransportError) as ei:
        CloudflareEmailClient(_config()).send_message("u@example.com", "s", "t", "h")
    assert "10102" in str(ei.value)


def test_http_error_raises_transport_error_with_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {"success": False, "errors": [{"code": 10102, "message": "forbidden"}]}
    ).encode()

    def _raise(req: object, timeout: int | None = None) -> _FakeResponse:
        del timeout
        url = str(getattr(req, "full_url", "https://api.cloudflare.com"))
        raise HTTPError(url, 403, "Forbidden", None, BytesIO(body))

    monkeypatch.setattr(cf_mod, "urlopen", _raise)
    with pytest.raises(EmailTransportError) as ei:
        CloudflareEmailClient(_config()).send_message("u@example.com", "s", "t", "h")
    assert "403" in str(ei.value)
    assert "10102" in str(ei.value)


def test_dispatch_fail_soft_on_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raising transport ⇒ dispatch returns cleanly (no exception)."""
    from digiquant.notify import dispatch as dispatch_mod

    class _BrokenInner:
        def is_suppressed(self, email: str) -> bool:
            return False

        def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
            raise EmailTransportError("boom")

    cfg = _config(unsubscribe_base="https://example.com/settings")

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
    monkeypatch.setattr(dispatch_mod.CloudflareEmailConfig, "from_env", lambda: cfg)
    monkeypatch.setattr(dispatch_mod, "build_email_client", lambda: _BrokenInner())

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

    cfg = _config(unsubscribe_base="https://example.com/settings")
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


def test_missing_notify_env_names_empty_and_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.notify.cloudflare_email import NOTIFY_NOT_CONFIGURED

    monkeypatch.delenv("CLOUDFLARE_EMAIL_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("NOTIFY_FROM", raising=False)
    missing = missing_notify_env_names({})
    assert missing == ["CLOUDFLARE_EMAIL_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "NOTIFY_FROM"]

    monkeypatch.setenv("CLOUDFLARE_EMAIL_API_TOKEN", "EMPTY")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("NOTIFY_FROM", "n@example.com")
    assert missing_notify_env_names() == ["CLOUDFLARE_EMAIL_API_TOKEN"]

    msg = format_notify_not_configured(["CLOUDFLARE_EMAIL_API_TOKEN"])
    assert NOTIFY_NOT_CONFIGURED in msg
    assert "CLOUDFLARE_EMAIL_API_TOKEN" in msg
    with pytest.raises(NotifyNotConfiguredError) as ei:
        CloudflareEmailConfig.require_from_env()
    assert ei.value.code == NOTIFY_NOT_CONFIGURED
    assert "CLOUDFLARE_EMAIL_API_TOKEN" in ei.value.missing


def test_cli_require_notify_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from digiquant.notify import dispatch as dispatch_mod
    from digiquant.notify.cloudflare_email import NOTIFY_NOT_CONFIGURED

    monkeypatch.delenv("CLOUDFLARE_EMAIL_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("NOTIFY_FROM", raising=False)
    code = dispatch_mod.main(["--require-notify"])
    assert code == 2
    err = capsys.readouterr().err
    assert NOTIFY_NOT_CONFIGURED in err
    assert "CLOUDFLARE_EMAIL_API_TOKEN" in err


def test_cli_require_notify_ok_when_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from digiquant.notify import dispatch as dispatch_mod

    monkeypatch.setenv("CLOUDFLARE_EMAIL_API_TOKEN", "token-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("NOTIFY_FROM", "n@example.com")
    code = dispatch_mod.main(["--check"])
    assert code == 0
    assert "notify env present" in capsys.readouterr().out


def test_suppressed_recipients_on_success_raises_suppressed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 2xx that drops the recipient must not look like a delivered send."""
    body = json.dumps(
        {"success": True, "result": {"suppressed_recipients": ["user@example.com"]}}
    ).encode()
    monkeypatch.setattr(cf_mod, "urlopen", _Capture(body))
    with pytest.raises(EmailSuppressedError) as ei:
        CloudflareEmailClient(_config()).send_message("user@example.com", "s", "t", "h")
    assert ei.value.recipient == "user@example.com"
    assert isinstance(ei.value, EmailTransportError)


def test_read_timeout_becomes_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(req: object, timeout: int | None = None) -> _FakeResponse:
        del req, timeout
        raise TimeoutError("read timed out")

    monkeypatch.setattr(cf_mod, "urlopen", _timeout)
    with pytest.raises(EmailTransportError):
        CloudflareEmailClient(_config()).send_message("u@example.com", "s", "t", "h")


def test_suppressed_send_releases_claim_so_retry_can_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A service-suppressed send must not burn the dedupe slot (#4370 review)."""
    from datetime import date

    from digiquant.notify.dispatch import dispatch_workspace

    from tests.dq.notify.conftest import FakeSupabase

    cfg = _config(unsubscribe_base="https://example.com/settings")
    pref = {
        "workspace_id": "w1",
        "email": "ops@example.com",
        "daily_digest": True,
        "holding_change_alerts": False,
        "execution_alerts": False,
        "digest_hour_utc": 12,
    }
    sb = FakeSupabase(
        tables={
            "notification_prefs": [pref],
            "workspaces": [{"id": "w1", "plan_tier": "free", "name": "House"}],
            "daily_snapshots": [
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral", "summary": "ok"}}}
            ],
            "notification_log": [],
        }
    )
    client = CloudflareEmailClient(cfg)
    run_date = date(2026, 8, 30)

    dropped = json.dumps(
        {"success": True, "result": {"suppressed_recipients": ["ops@example.com"]}}
    ).encode()
    monkeypatch.setattr(cf_mod, "urlopen", _Capture(dropped))
    dispatch_workspace(sb, client, cfg, pref, run_date, 12, force_digest=True)
    assert sb.tables["notification_log"] == []

    monkeypatch.setattr(cf_mod, "urlopen", _Capture())
    dispatch_workspace(sb, client, cfg, pref, run_date, 12, force_digest=True)
    assert len(sb.tables["notification_log"]) == 1


def _pref() -> dict[str, object]:
    return {
        "workspace_id": "w1",
        "email": "ops@example.com",
        "daily_digest": True,
        "holding_change_alerts": False,
        "execution_alerts": False,
        "digest_hour_utc": 12,
    }


def _store() -> Any:
    from tests.dq.notify.conftest import FakeSupabase

    return FakeSupabase(
        tables={
            "notification_prefs": [_pref()],
            "workspaces": [{"id": "w1", "plan_tier": "free", "name": "House"}],
            "daily_snapshots": [
                {"date": "2026-08-30", "snapshot": {"regime": {"bias": "neutral", "summary": "ok"}}}
            ],
            "notification_claim": [],
            "notification_log": [],
        }
    )


def test_successful_send_claims_then_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real send leaves the mutable claim *and* the append-only record (#4384)."""
    from datetime import date

    from digiquant.notify.dispatch import dispatch_workspace

    cfg = _config(unsubscribe_base="https://example.com/settings")
    sb = _store()
    monkeypatch.setattr(cf_mod, "urlopen", _Capture())
    dispatch_workspace(
        sb, CloudflareEmailClient(cfg), cfg, _pref(), date(2026, 8, 30), 12, force_digest=True
    )
    assert len(sb.tables["notification_claim"]) == 1
    assert len(sb.tables["notification_log"]) == 1


def test_existing_claim_dedupes_without_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    """The claim, not the log, is what stops a second send the same day."""
    from datetime import date

    from digiquant.notify.dispatch import dispatch_workspace

    cfg = _config(unsubscribe_base="https://example.com/settings")
    sb = _store()
    sb.tables["notification_claim"].append(
        {"workspace_id": "w1", "event_key": "digest:2026-08-30", "sent_date": "2026-08-30"}
    )
    capture = _Capture()
    monkeypatch.setattr(cf_mod, "urlopen", capture)
    dispatch_workspace(
        sb, CloudflareEmailClient(cfg), cfg, _pref(), date(2026, 8, 30), 12, force_digest=True
    )
    assert capture.request is None
    assert sb.tables["notification_log"] == []


def test_suppressed_send_releases_claim_without_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suppression is not a send: the claim must go, and no log row appears (#4384)."""
    from datetime import date

    from digiquant.notify.dispatch import dispatch_workspace

    cfg = _config(unsubscribe_base="https://example.com/settings")
    sb = _store()
    dropped = json.dumps(
        {"success": True, "result": {"suppressed_recipients": ["ops@example.com"]}}
    ).encode()
    monkeypatch.setattr(cf_mod, "urlopen", _Capture(dropped))
    dispatch_workspace(
        sb, CloudflareEmailClient(cfg), cfg, _pref(), date(2026, 8, 30), 12, force_digest=True
    )
    assert sb.tables["notification_claim"] == []
    assert sb.tables["notification_log"] == []


def test_migration_133_grants_the_claim_delete_and_keeps_the_log_append_only() -> None:
    """The #4384 split, pinned: DELETE on the claim, never on the log."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "digiquant" / "supabase" / "migrations"
    claim = (root / "133_notification_claim.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS public.notification_claim" in claim
    assert "GRANT SELECT, INSERT, DELETE ON public.notification_claim TO service_role" in claim
    assert "reject_notification_claim" not in claim

    canonical = (root / "106_notification_prefs_align_canonical.sql").read_text()
    assert "GRANT SELECT, INSERT ON public.notification_log TO service_role" in canonical
    assert "reject_notification_log_mutation" in canonical
    log_grants = [
        line
        for line in canonical.splitlines()
        if line.strip().startswith("GRANT") and "notification_log" in line
    ]
    assert not any("DELETE" in line for line in log_grants)
