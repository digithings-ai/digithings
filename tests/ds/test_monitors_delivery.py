"""Phase C monitor delivery (#4065, Task 5).

Pins §4.5 + R7h/R8/R13: EXA-identical ``validate_delivery`` codes (required +
private per webhook and slack), the signed webhook/slack POST
(``X-digi-signature: sha256=<HMAC-SHA256 over the exact body bytes>``, httpx,
2 attempts, linear backoff), the stdlib-``smtplib`` email leg driven by
``DIGISEARCH_SMTP_*``, exactly one receipt per target, per-target failure
isolation (nothing escapes ``deliver``), and the secret never appearing in a
receipt. Offline only: ``httpx.MockTransport`` and injected SMTP fakes — no
socket is ever opened.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
import ssl
from email import message_from_string

import httpx
import pytest
from digisearch.monitors import delivery as mod
from digisearch.monitors.delivery import DeliveryConfigError, validate_delivery
from digisearch.monitors.models import DeliveryConfig, DeliveryReceipt, MonitorRun, Watch

_WEBHOOK_URL = "https://hooks.example.com/x"

# An address literal keeps validation offline: getaddrinfo answers from the
# literal itself and never leaves the host.
_PUBLIC_URL = "https://93.184.216.34/hook"


@pytest.mark.unit
def test_poll_needs_no_targets():
    validate_delivery(DeliveryConfig(mode="poll"))


@pytest.mark.unit
def test_webhook_without_targets_is_required():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(DeliveryConfig(mode="webhook", targets=[]))
    assert ei.value.code == "webhook_url_required"
    assert "[webhook]: Required" in str(ei.value)


@pytest.mark.unit
def test_private_urls_rejected():
    for bad in [
        "http://127.0.0.1:3000/hook",
        "https://localhost/hook",
        "https://192.168.1.10/hook",
        "https://10.0.0.5/hook",
    ]:
        with pytest.raises(DeliveryConfigError) as ei:
            validate_delivery(
                DeliveryConfig(mode="webhook", targets=[{"kind": "webhook", "url": bad}])
            )
        assert ei.value.code == "webhook_url_private"


@pytest.mark.unit
def test_deliver_posts_run_json(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode()[:50])
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))
    watch = Watch.model_validate(
        {
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {
                "mode": "webhook",
                "targets": [{"kind": "webhook", "url": "https://hooks.example.com/x"}],
            },
        }
    )
    run = MonitorRun.model_validate(
        {
            "run_id": "r1",
            "watch_id": "w1",
            "status": "ok",
            "trigger": "manual",
            "started_at": "2026-09-14T00:00:00Z",
            "finished_at": "2026-09-14T00:01:00Z",
            "query_snapshot": {"query": "etf flows"},
            "results_all": [],
            "results_new": [],
            "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0},
        }
    )
    receipts = mod.deliver(run, watch, delivery_secret="s3cr3t")
    assert receipts[0].ok is True and receipts[0].status_code == 200
    assert seen and "r1" in seen[0]


@pytest.mark.unit
def test_deliver_signs_webhook_hmac(monkeypatch):
    seen_headers: list[dict] = []
    seen_body: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        seen_body.append(request.read())
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))
    watch = Watch.model_validate(
        {
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {
                "mode": "webhook",
                "targets": [{"kind": "webhook", "url": "https://hooks.example.com/x"}],
            },
        }
    )
    run = MonitorRun.model_validate(
        {
            "run_id": "r9",
            "watch_id": "w9",
            "status": "ok",
            "trigger": "manual",
            "started_at": "2026-09-14T00:00:00Z",
            "finished_at": "2026-09-14T00:01:00Z",
            "query_snapshot": {"query": "etf flows"},
            "results_all": [],
            "results_new": [],
            "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0},
        }
    )
    mod.deliver(run, watch, delivery_secret="s3cr3t")
    sig = seen_headers[0].get("x-digi-signature", "")
    assert sig.startswith("sha256=")
    expect = hmac.new(b"s3cr3t", seen_body[0], hashlib.sha256).hexdigest()
    assert sig == f"sha256={expect}"


@pytest.mark.unit
def test_watch_has_no_secret_field():
    # R8: the delivery secret lives only in create/rotate responses
    assert "delivery_secret" not in Watch.model_fields


@pytest.mark.unit
def test_delivery_only_on_ok_runs(monkeypatch, tmp_path):
    """R13: no_change/failed runs never reach deliver()."""
    from digisearch.monitors import runner as rmod
    from digisearch.monitors.store import MonitorStore
    from digisearch.web_exa import WebSearchData

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    # The brief's version of this test omitted the delivery config + stored
    # secret, which leaves the watch in poll mode with no secret; the landed
    # runner's R13 gate (mode != poll) and its loud secret-missing failure
    # would both fire before deliver() — so the call could never be observed.
    # This is the same intent with the runner's real preconditions.
    w = store.create_watch(
        Watch.model_validate(
            {
                "name": "etf",
                "query": "etf flows",
                "schedule": {"mode": "interval", "interval_seconds": 3600},
                "delivery": {
                    "mode": "webhook",
                    "targets": [{"kind": "webhook", "url": _WEBHOOK_URL}],
                },
            }
        )
    )
    store.set_delivery_secret(w.watch_id, "s3cr3t")
    monkeypatch.setattr(
        rmod,
        "_invoke_shallow_recall",
        lambda **k: WebSearchData.model_validate(
            {"results": [{"url": "https://a.com/1", "title": "A", "text": "alpha"}]}
        ),
    )
    delivered: list[str] = []
    monkeypatch.setattr(rmod, "deliver", lambda run, watch, **k: delivered.append(run.status) or [])
    rmod.run_watch(w.watch_id, trigger="manual", store=store)  # ok -> delivered
    rmod.run_watch(w.watch_id, trigger="schedule", store=store)  # no_change -> skipped
    assert delivered == ["ok"]


# --- extended coverage -------------------------------------------------------


def _webhook_watch(*urls: str, kind: str = "webhook") -> Watch:
    return Watch.model_validate(
        {
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {
                "mode": "webhook",
                "targets": [{"kind": kind, "url": url} for url in urls],
            },
        }
    )


def _email_watch(*addresses: str) -> Watch:
    return Watch.model_validate(
        {
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {
                "mode": "webhook",
                "targets": [{"kind": "email", "email_to": list(addresses)}],
            },
        }
    )


def _ok_run(**overrides) -> MonitorRun:
    body: dict = {
        "run_id": "r1",
        "watch_id": "w1",
        "status": "ok",
        "trigger": "manual",
        "started_at": "2026-09-14T00:00:00Z",
        "finished_at": "2026-09-14T00:01:00Z",
        "query_snapshot": {"query": "etf flows"},
        "results_all": [],
        "results_new": [],
        "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0},
    }
    body.update(overrides)
    return MonitorRun.model_validate(body)


def _patch_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record backoff sleeps instead of sleeping them."""
    recorded: list[float] = []
    monkeypatch.setattr(mod, "_sleep", recorded.append)
    return recorded


@pytest.fixture(autouse=True)
def _clear_smtp_env(monkeypatch):
    """Hermetic SMTP config: tests opt in by setting the DIGISEARCH_SMTP_* vars."""
    for name in (
        "DIGISEARCH_SMTP_HOST",
        "DIGISEARCH_SMTP_PORT",
        "DIGISEARCH_SMTP_USER",
        "DIGISEARCH_SMTP_PASS",
        "DIGISEARCH_SMTP_FROM",
    ):
        monkeypatch.delenv(name, raising=False)


class _FakeSMTP:
    """Records the smtplib calls the email leg makes; never touches a socket."""

    def __init__(
        self, *, fail_with: Exception | None = None, starttls_available: bool = True
    ) -> None:
        self.fail_with = fail_with
        self.starttls_available = starttls_available
        self.calls: list[object] = []
        self.sent: list[tuple[str, list[str], str]] = []
        self.starttls_context: ssl.SSLContext | None = None

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def has_extn(self, name: str) -> bool:
        return name == "starttls" and self.starttls_available

    def starttls(self, *, context: ssl.SSLContext | None = None) -> None:
        self.calls.append("starttls")
        self.starttls_context = context

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user, password))

    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append("sendmail")
        self.sent.append((sender, list(recipients), message))

    def quit(self) -> None:
        self.calls.append("quit")


@pytest.mark.unit
def test_public_https_target_accepted():
    validate_delivery(
        DeliveryConfig(mode="webhook", targets=[{"kind": "webhook", "url": _PUBLIC_URL}])
    )


@pytest.mark.unit
def test_email_target_needs_no_url():
    validate_delivery(
        DeliveryConfig(
            mode="webhook",
            targets=[{"kind": "email", "email_to": ["ops@example.com"]}],
        )
    )


@pytest.mark.unit
def test_userinfo_url_rejected():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(
            DeliveryConfig(
                mode="webhook",
                targets=[{"kind": "webhook", "url": "https://token@93.184.216.34/hook"}],
            )
        )
    assert ei.value.code == "webhook_url_private"
    assert "cannot point to localhost" in str(ei.value)


@pytest.mark.unit
def test_malformed_urls_rejected_like_private():
    for bad in ["https://[::1/hook", "https://host:notaport/hook", "https:///hook"]:
        with pytest.raises(DeliveryConfigError) as ei:
            validate_delivery(
                DeliveryConfig(mode="webhook", targets=[{"kind": "webhook", "url": bad}])
            )
        assert ei.value.code == "webhook_url_private"


@pytest.mark.unit
def test_webhook_target_without_url_is_required():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(DeliveryConfig(mode="webhook", targets=[{"kind": "webhook"}]))
    assert ei.value.code == "webhook_url_required"


@pytest.mark.unit
def test_slack_target_required_and_private_codes():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(DeliveryConfig(mode="webhook", targets=[{"kind": "slack"}]))
    assert ei.value.code == "slack_url_required"
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(
            DeliveryConfig(mode="webhook", targets=[{"kind": "slack", "url": "https://10.0.0.5/h"}])
        )
    assert ei.value.code == "slack_url_private"


@pytest.mark.unit
def test_fanout_without_targets_is_required():
    with pytest.raises(DeliveryConfigError) as ei:
        validate_delivery(DeliveryConfig(mode="fanout"))
    assert ei.value.code == "webhook_url_required"
    assert "[webhook]: Required" in str(ei.value)


@pytest.mark.unit
def test_webhook_retries_transport_error_then_succeeds(monkeypatch, sleeps):
    attempts: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.read())
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, json={"ok": True})

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(run_id="r2"), _webhook_watch(_WEBHOOK_URL), delivery_secret="s3")

    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert receipts == [DeliveryReceipt(target_kind="webhook", ok=True, status_code=200)]
    assert sleeps == [mod._WEBHOOK_BACKOFF_S]


@pytest.mark.unit
def test_webhook_failure_receipt_redacts_url_without_trailing_slash(monkeypatch, sleeps):
    target_url = "https://hooks.example.com/x/"

    def handler(request: httpx.Request) -> httpx.Response:
        # Transport errors may echo the URL without the trailing slash.
        raise httpx.ConnectError("cannot reach https://hooks.example.com/x", request=request)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(), _webhook_watch(target_url), delivery_secret="s3")

    assert receipts[0].ok is False
    assert "hooks.example.com" not in (receipts[0].error or "")


@pytest.mark.unit
def test_webhook_failure_receipt_redacts_secret_and_url(monkeypatch, sleeps):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError(f"cannot reach {request.url} with s3cr3t", request=request)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(), _webhook_watch(_WEBHOOK_URL), delivery_secret="s3cr3t")

    assert len(attempts) == 2
    assert sleeps == [mod._WEBHOOK_BACKOFF_S]
    receipt = receipts[0]
    assert receipt.ok is False
    assert receipt.status_code is None
    assert "ConnectError" in receipt.error
    assert "s3cr3t" not in receipt.error
    assert _WEBHOOK_URL not in receipt.error


@pytest.mark.unit
@pytest.mark.parametrize("status", [429, 500])
def test_webhook_retryable_status_retries_then_records_status(monkeypatch, sleeps, status):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(status)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(), _webhook_watch(_WEBHOOK_URL), delivery_secret="s3")

    assert len(attempts) == 2
    assert sleeps == [mod._WEBHOOK_BACKOFF_S]
    assert receipts == [
        DeliveryReceipt(target_kind="webhook", ok=False, status_code=status, error=f"HTTP {status}")
    ]


@pytest.mark.unit
def test_webhook_non_retryable_4xx_fails_fast(monkeypatch, sleeps):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(), _webhook_watch(_WEBHOOK_URL), delivery_secret="s3")

    assert len(attempts) == 1
    assert sleeps == []
    assert receipts == [
        DeliveryReceipt(target_kind="webhook", ok=False, status_code=404, error="HTTP 404")
    ]


@pytest.mark.unit
def test_deliver_isolates_target_failures_and_keeps_order(monkeypatch, sleeps):
    bad_url = "https://bad.example.com/x"
    good_url = "https://good.example.com/x"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == bad_url:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(204)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(_ok_run(), _webhook_watch(bad_url, good_url), delivery_secret="s3cr3t")

    assert [r.target_kind for r in receipts] == ["webhook", "webhook"]
    assert [r.ok for r in receipts] == [False, True]
    assert receipts[1].status_code == 204
    assert calls == [bad_url, bad_url, good_url]
    assert sleeps == [mod._WEBHOOK_BACKOFF_S]


@pytest.mark.unit
def test_deliver_without_targets_returns_no_receipts(monkeypatch):
    calls: list[int] = []
    _patch_transport(monkeypatch, lambda request: calls.append(1) or httpx.Response(200))
    receipts = mod.deliver(
        _ok_run(),
        Watch.model_validate(
            {
                "name": "etf",
                "query": "etf flows",
                "schedule": {"mode": "interval", "interval_seconds": 3600},
            }
        ),
        delivery_secret="s3cr3t",
    )
    assert receipts == []
    assert calls == []


@pytest.mark.unit
def test_slack_target_posts_signed_run_json(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        seen["headers"] = dict(request.headers)
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    receipts = mod.deliver(
        _ok_run(run_id="r7"),
        _webhook_watch(_WEBHOOK_URL, kind="slack"),
        delivery_secret="s3cr3t",
    )

    assert receipts == [DeliveryReceipt(target_kind="slack", ok=True, status_code=200)]
    expect = hmac.new(b"s3cr3t", seen["body"], hashlib.sha256).hexdigest()
    assert seen["headers"]["x-digi-signature"] == f"sha256={expect}"
    assert json.loads(seen["body"])["run_id"] == "r7"


@pytest.mark.unit
def test_email_without_relay_env_is_a_failed_receipt(monkeypatch):
    def no_client(host, port, timeout_s):
        raise AssertionError("SMTP must not be constructed without relay env")

    monkeypatch.setattr(mod, "_smtp_client", no_client)
    receipts = mod.deliver(_ok_run(), _email_watch("alerts@example.com"), delivery_secret="s3")

    assert receipts == [DeliveryReceipt(target_kind="email", ok=False, error="smtp_not_configured")]


@pytest.mark.unit
def test_email_without_recipients_is_a_failed_receipt(monkeypatch):
    def no_client(host, port, timeout_s):
        raise AssertionError("SMTP must not be constructed without recipients")

    monkeypatch.setattr(mod, "_smtp_client", no_client)
    receipts = mod.deliver(_ok_run(), _email_watch(), delivery_secret="s3")

    assert receipts == [
        DeliveryReceipt(target_kind="email", ok=False, error="email_recipients_missing")
    ]


@pytest.mark.unit
def test_email_sends_run_summary_via_smtp(monkeypatch):
    fake = _FakeSMTP()
    connections: list[tuple[str, int, float]] = []

    def factory(host, port, timeout_s):
        connections.append((host, port, timeout_s))
        return fake

    monkeypatch.setattr(mod, "_smtp_client", factory)
    monkeypatch.setenv("DIGISEARCH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DIGISEARCH_SMTP_PORT", "2525")
    monkeypatch.setenv("DIGISEARCH_SMTP_USER", "apikey")
    monkeypatch.setenv("DIGISEARCH_SMTP_PASS", "hunter2")
    monkeypatch.setenv("DIGISEARCH_SMTP_FROM", "monitors@example.com")
    run = _ok_run(
        results_all=[{"url": "https://a.com/1", "title": "A"}],
        results_new=[{"url": "https://a.com/1", "title": "A"}],
    )

    receipts = mod.deliver(run, _email_watch("alerts@example.com"), delivery_secret="s3cr3t")

    assert receipts == [DeliveryReceipt(target_kind="email", ok=True)]
    assert connections == [("smtp.example.com", 2525, 10.0)]
    assert "starttls" in fake.calls
    # STARTTLS must use a verified context, never smtplib's CERT_NONE default.
    assert isinstance(fake.starttls_context, ssl.SSLContext)
    assert fake.starttls_context.verify_mode == ssl.CERT_REQUIRED
    assert fake.starttls_context.check_hostname is True
    assert ("login", "apikey", "hunter2") in fake.calls
    assert fake.calls[-1] == "quit"
    sender, recipients, raw = fake.sent[0]
    assert sender == "monitors@example.com"
    assert recipients == ["alerts@example.com"]
    parsed = message_from_string(raw)
    assert "etf" in parsed["Subject"]
    body = parsed.get_payload(decode=True).decode("utf-8")
    assert "https://a.com/1" in body
    assert "s3cr3t" not in raw


@pytest.mark.unit
def test_email_without_starttls_refuses_credentials(monkeypatch):
    fake = _FakeSMTP(starttls_available=False)
    monkeypatch.setattr(mod, "_smtp_client", lambda host, port, timeout_s: fake)
    monkeypatch.setenv("DIGISEARCH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DIGISEARCH_SMTP_USER", "apikey")
    monkeypatch.setenv("DIGISEARCH_SMTP_PASS", "hunter2")
    monkeypatch.setenv("DIGISEARCH_SMTP_FROM", "monitors@example.com")

    receipts = mod.deliver(_ok_run(), _email_watch("alerts@example.com"), delivery_secret="s3")

    assert receipts == [
        DeliveryReceipt(target_kind="email", ok=False, error="smtp_tls_unavailable")
    ]
    assert "starttls" not in fake.calls
    assert not any(isinstance(call, tuple) and call[0] == "login" for call in fake.calls)
    assert "sendmail" not in fake.calls
    assert fake.calls[-1] == "quit"


@pytest.mark.unit
def test_email_without_starttls_and_without_credentials_sends_in_clear(monkeypatch):
    fake = _FakeSMTP(starttls_available=False)
    monkeypatch.setattr(mod, "_smtp_client", lambda host, port, timeout_s: fake)
    monkeypatch.setenv("DIGISEARCH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DIGISEARCH_SMTP_FROM", "monitors@example.com")

    receipts = mod.deliver(_ok_run(), _email_watch("alerts@example.com"), delivery_secret="s3")

    assert receipts == [DeliveryReceipt(target_kind="email", ok=True)]
    assert "starttls" not in fake.calls
    assert "sendmail" in fake.calls


@pytest.mark.unit
def test_email_malformed_port_is_a_failed_receipt(monkeypatch):
    def no_client(host, port, timeout_s):
        raise AssertionError("SMTP must not be constructed with a malformed port")

    monkeypatch.setattr(mod, "_smtp_client", no_client)
    monkeypatch.setenv("DIGISEARCH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DIGISEARCH_SMTP_PORT", "not-a-port")
    monkeypatch.setenv("DIGISEARCH_SMTP_FROM", "monitors@example.com")

    receipts = mod.deliver(_ok_run(), _email_watch("alerts@example.com"), delivery_secret="s3")

    assert receipts == [DeliveryReceipt(target_kind="email", ok=False, error="smtp_not_configured")]


@pytest.mark.unit
def test_email_smtp_failure_is_a_failed_receipt(monkeypatch):
    fake = _FakeSMTP(fail_with=smtplib.SMTPServerDisconnected("relay down"))
    monkeypatch.setattr(mod, "_smtp_client", lambda host, port, timeout_s: fake)
    monkeypatch.setenv("DIGISEARCH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DIGISEARCH_SMTP_FROM", "monitors@example.com")

    receipts = mod.deliver(_ok_run(), _email_watch("alerts@example.com"), delivery_secret="s3")

    assert receipts[0].ok is False
    assert "SMTPServerDisconnected" in receipts[0].error
    assert fake.calls[-1] == "quit"
