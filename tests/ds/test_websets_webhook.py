"""Phase D webset webhook delivery + ``webhook_deliveries`` ledger (#4066, Task 5b).

Pins the delivery half of the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Webhook delivery) — the R13 human-gated task: the first outbound egress to
caller-controlled URLs.

Covered:

- the POST body is ``{event, webset_id, delivered_at}`` and
  ``X-digi-signature: sha256=<hmac(secret, body)>`` is computed over the exact
  observed body bytes by the shared Phase C signing core (byte-identical, R7);
- 3 attempts with the pinned 5s/25s backoff (sleep seam, no real waits) and
  Phase C's retryable-status rule (429/5xx retry, other 4xx fails fast);
- ledger rows in ``webhook_deliveries`` keyed ``(webhook_id, event_id)`` with
  INSERT-or-ignore semantics: a duplicate delivery never double-records and a
  ledger-recorded terminal failure is never re-attempted;
- rotation overlap: the previous secret verifies until ``previous_expires_at``
  and is dropped after; delivery itself always signs with the current secret;
- per-target failure isolation (one bad target cannot abort the rest and
  nothing raises out of the delivery path) plus secret/URL redaction in ledger
  errors;
- the append-only event rows are never mutated by delivery;
- the append-path wiring: ``append_event`` (the single event writer every
  emitter routes through) fans the stored event out to the webset's subscribed
  webhooks — signed POST on subscription, zero egress without one, a failed
  delivery recorded in the ledger without raising, and one failing target not
  aborting the remaining targets.

Offline: ``httpx.MockTransport`` and the ``_sleep`` / ``_client_for`` seams,
real sqlite files under ``tmp_path``. ``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from digisearch.monitors import delivery as phase_c
from digisearch.websets import events as mod
from digisearch.websets.models import (
    VerificationCriterion,
    WebhookConfig,
    Webset,
    WebsetEvent,
    WebsetSearch,
)
from digisearch.websets.store import WebsetStore

pytestmark = pytest.mark.unit

_SECRET = "s3cr3t-current"
_PREVIOUS_SECRET = "s3cr3t-previous"
_ROTATED_SECRET = "s3cr3t-rotated"
_URL_BAD = "https://bad.example.com/hooks/one"
_URL_GOOD = "https://good.example.com/hooks/two"
_T0 = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff without waiting (the delivery module's sleep seam)."""
    recorded: list[float] = []
    monkeypatch.setattr(mod, "_sleep", recorded.append)
    return recorded


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda timeout: httpx.Client(transport=transport))


def _store(tmp_path) -> WebsetStore:
    return WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))


def _webset(store: WebsetStore) -> Webset:
    return store.create_webset(
        Webset(
            criteria=[VerificationCriterion(name="photonics", rule="photonics startup")],
        )
    )


def _event(store: WebsetStore, webset_id: str, kind: str = "webset.idle") -> WebsetEvent:
    search = store.add_search(
        WebsetSearch(
            webset_id=webset_id,
            query="photonics startups",
            criteria=[VerificationCriterion(name="photonics", rule="photonics startup")],
        )
    )
    return store.append_event(WebsetEvent(webset_id=webset_id, type=kind, search_id=search.id))


def _webhook(
    store: WebsetStore,
    webset_id: str,
    url: str,
    *,
    events: tuple[str, ...] = ("webset.idle",),
    secret: str = _SECRET,
) -> WebhookConfig:
    return store.add_webhook(
        webset_id,
        WebhookConfig(url=url, events=list(events), secret=secret),
    )


def _expected_signature(secret: str, body: bytes) -> str:
    return f"sha256={hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()}"


# ── signed body ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_deliver_posts_signed_event_body(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == _URL_GOOD
    assert request.headers["content-type"] == "application/json"
    body = request.read()
    payload = json.loads(body.decode("utf-8"))
    assert payload["webset_id"] == webset.id
    assert payload["delivered_at"] == _T0.isoformat()
    assert payload["event"]["id"] == event.id
    assert payload["event"]["type"] == "webset.idle"
    assert payload["event"]["payload"] == event.payload

    signature = request.headers["x-digi-signature"]
    # R7: byte-identical to the shared Phase C signing core over the observed
    # body bytes — never a second HMAC implementation.
    assert signature == phase_c.sign_webhook_body(_SECRET, body)
    assert signature == _expected_signature(_SECRET, body)
    assert mod.sign_webhook_body is phase_c.sign_webhook_body

    assert [row.webhook_id for row in rows] == [webhook.webhook_id]
    assert rows[0].ok is True and rows[0].status_code == 200
    assert rows[0] == store.get_webhook_delivery(webhook.webhook_id, event.id)


# ── retries + backoff ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("status", [429, 500])
def test_retryable_failure_uses_three_attempts_with_5s_25s_backoff(
    monkeypatch, tmp_path, sleeps, status
):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    attempts: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.read())
        return httpx.Response(status)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert len(attempts) == 3
    assert attempts[0] == attempts[1] == attempts[2]
    assert sleeps == [5.0, 25.0]
    assert rows[0].ok is False
    assert rows[0].status_code == status
    assert rows[0].error == f"HTTP {status}"
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 1


@pytest.mark.unit
def test_backoff_repeats_last_step_when_attempts_grow(monkeypatch, tmp_path, sleeps):
    """Raising ``_WEBHOOK_ATTEMPTS`` must not index past the pinned sequence."""
    monkeypatch.setattr(mod, "_WEBHOOK_ATTEMPTS", 4)
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    _webhook(store, webset.id, _URL_GOOD)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert len(attempts) == 4
    assert sleeps == [5.0, 25.0, 25.0]
    assert rows[0].ok is False and rows[0].status_code == 503


@pytest.mark.unit
def test_real_client_factory_disables_redirects_and_bounds_timeout(monkeypatch):
    """Pin the production httpx config, not just the ``_client_for`` seam.

    A regression to redirect-following would let an approved public target 30x
    the delivery to an internal address (SSRF); the seam monkeypatch in the
    other tests would leave that green.
    """
    captured: dict[str, object] = {}
    real_client = httpx.Client

    def recording_client(**kwargs):
        captured.update(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", recording_client)
    client = mod._client_for(7.5)
    try:
        assert captured == {"timeout": 7.5, "follow_redirects": False}
        assert client.follow_redirects is False
        assert client.timeout.connect == 7.5
        assert client.timeout.read == 7.5
    finally:
        client.close()


@pytest.mark.unit
def test_redaction_helper_is_shared_with_phase_c():
    """One security-relevant redaction implementation across both egresses."""
    assert mod.redact_error is phase_c.redact_error


@pytest.mark.unit
def test_transport_error_retries_then_succeeds(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    attempts: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.read())
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert sleeps == [5.0]
    assert rows[0].ok is True and rows[0].status_code == 200
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 1


@pytest.mark.unit
def test_non_retryable_4xx_fails_fast(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert len(attempts) == 1
    assert sleeps == []
    assert rows[0].ok is False and rows[0].status_code == 404 and rows[0].error == "HTTP 404"
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 1


# ── ledger INSERT-or-ignore ───────────────────────────────────────────────────


@pytest.mark.unit
def test_duplicate_delivery_does_not_double_record(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(202)

    _patch_transport(monkeypatch, handler)
    first = mod.deliver_webhook(store, event, now=_T0)
    second = mod.deliver_webhook(store, event, now=_T0)

    assert len(calls) == 1
    assert first == second
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 1


@pytest.mark.unit
def test_terminal_failure_is_recorded_once_and_not_retried(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("down", request=request)

    _patch_transport(monkeypatch, handler)
    first = mod.deliver_webhook(store, event, now=_T0)
    second = mod.deliver_webhook(store, event, now=_T0)

    assert len(attempts) == 3
    assert sleeps == [5.0, 25.0]
    assert first == second
    assert first[0].ok is False
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 1


# ── rotation overlap ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_rotation_overlap_accepts_previous_secret_until_expiry():
    payload = b'{"event": "x"}'
    webhook = WebhookConfig(
        url=_URL_GOOD,
        events=["webset.idle"],
        secret=_SECRET,
        previous_secret=_PREVIOUS_SECRET,
        previous_expires_at=_T0 + timedelta(hours=24),
    )
    previous_sig = phase_c.sign_webhook_body(_PREVIOUS_SECRET, payload)
    current_sig = phase_c.sign_webhook_body(_SECRET, payload)

    assert mod.verify_webhook_signature(webhook, payload, current_sig, now=_T0) is True
    assert mod.verify_webhook_signature(webhook, payload, previous_sig, now=_T0) is True
    assert (
        mod.verify_webhook_signature(
            webhook, payload, previous_sig, now=_T0 + timedelta(hours=23, minutes=59)
        )
        is True
    )
    # At the expiry instant the previous secret is dropped, not still accepted.
    assert (
        mod.verify_webhook_signature(
            webhook, payload, previous_sig, now=webhook.previous_expires_at
        )
        is False
    )
    expired = webhook.model_copy(update={"previous_expires_at": _T0 - timedelta(seconds=1)})
    assert mod.verify_webhook_signature(expired, payload, previous_sig, now=_T0) is False
    # A previous secret with no expiry would make rotation unbounded: reject it.
    unbounded = webhook.model_copy(update={"previous_expires_at": None})
    assert mod.verify_webhook_signature(unbounded, payload, previous_sig, now=_T0) is False
    # A wrong/garbage signature is never accepted.
    assert mod.verify_webhook_signature(webhook, payload, "sha256=deadbeef", now=_T0) is False


@pytest.mark.unit
def test_delivery_signs_with_current_secret_during_overlap(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    rotated = store.update_webhook(
        webset.id,
        webhook.model_copy(
            update={
                "secret": _ROTATED_SECRET,
                "previous_secret": _SECRET,
                "previous_expires_at": _T0 + timedelta(hours=24),
            }
        ),
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    mod.deliver_webhook(store, event, now=_T0)

    body = seen[0].read()
    signature = seen[0].headers["x-digi-signature"]
    assert signature == phase_c.sign_webhook_body(_ROTATED_SECRET, body)
    assert signature != phase_c.sign_webhook_body(_SECRET, body)
    # A receiver mid-rotation accepts the delivery under either active secret.
    assert mod.verify_webhook_signature(rotated, body, signature, now=_T0) is True


# ── fan-out selection / isolation / redaction ─────────────────────────────────


@pytest.mark.unit
def test_delivery_skips_unsubscribed_and_inactive_webhooks(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    idle_hook = _webhook(store, webset.id, _URL_GOOD, events=("webset.idle",))
    created_hook = _webhook(
        store, webset.id, "https://other.example.com/x", events=("item.created",)
    )
    inactive = _webhook(store, webset.id, "https://inactive.example.com/x")
    store.update_webhook(webset.id, inactive.model_copy(update={"active": False}))
    event = _event(store, webset.id)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert [row.webhook_id for row in rows] == [idle_hook.webhook_id]
    assert calls == [_URL_GOOD]
    assert store.get_webhook_delivery(created_hook.webhook_id, event.id) is None
    assert store.get_webhook_delivery(inactive.webhook_id, event.id) is None


@pytest.mark.unit
def test_no_registered_webhooks_means_no_egress(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    calls: list[int] = []

    _patch_transport(monkeypatch, lambda request: calls.append(1) or httpx.Response(200))
    assert mod.deliver_webhook(store, event, now=_T0) == []
    assert calls == []


@pytest.mark.unit
def test_missing_secret_fails_closed_without_egress(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    webhook = _webhook(store, webset.id, _URL_GOOD, secret="")
    calls: list[int] = []

    _patch_transport(monkeypatch, lambda request: calls.append(1) or httpx.Response(200))
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert calls == []
    assert rows[0].ok is False and rows[0].error == "webhook_secret_missing"
    assert rows[0] == store.get_webhook_delivery(webhook.webhook_id, event.id)


@pytest.mark.unit
def test_per_target_failure_isolation_and_redaction(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    bad_hook = _webhook(store, webset.id, _URL_BAD)
    good_hook = _webhook(store, webset.id, _URL_GOOD)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == _URL_BAD:
            # Hostile failure text embeds both the secret and the target URL.
            raise httpx.ConnectError(f"cannot reach {request.url} with {_SECRET}", request=request)
        return httpx.Response(204)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)

    assert [row.webhook_id for row in rows] == [bad_hook.webhook_id, good_hook.webhook_id]
    assert [row.ok for row in rows] == [False, True]
    assert rows[1].status_code == 204
    assert calls == [_URL_BAD, _URL_BAD, _URL_BAD, _URL_GOOD]
    assert sleeps == [5.0, 25.0]

    failed = store.get_webhook_delivery(bad_hook.webhook_id, event.id)
    assert failed is not None and failed.status_code is None
    assert "ConnectError" in failed.error
    assert _SECRET not in failed.error
    assert _URL_BAD not in failed.error
    assert "bad.example.com" not in failed.error
    assert len(store.list_webhook_deliveries(bad_hook.webhook_id)) == 1
    assert store.get_webhook_delivery(good_hook.webhook_id, event.id).ok is True


@pytest.mark.unit
def test_delivery_never_mutates_event_rows(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    _webhook(store, webset.id, _URL_GOOD)
    before = [row.model_dump(mode="json") for row in store.list_events(webset.id)[0]]

    _patch_transport(monkeypatch, lambda request: httpx.Response(200))
    mod.deliver_webhook(store, event, now=_T0)

    after = [row.model_dump(mode="json") for row in store.list_events(webset.id)[0]]
    assert after == before
    assert store.list_events(webset.id)[0][0].model_dump()["payload"] == {}


# ── store faults (contained, never abort the fan-out) ─────────────────────────


@pytest.mark.unit
def test_store_fault_on_ledger_write_does_not_abort_other_targets(monkeypatch, tmp_path, caplog):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    bad_hook = _webhook(store, webset.id, _URL_BAD)
    good_hook = _webhook(store, webset.id, _URL_GOOD)
    calls: list[str] = []
    real_record = store.record_webhook_delivery

    def flaky_record(webhook_id, event_id, *, ok, status_code=None, error=None):
        if webhook_id == bad_hook.webhook_id:
            # Hostile store fault text embeds both the secret and the URL.
            raise sqlite3.OperationalError(f"database is locked at {_URL_BAD} with {_SECRET}")
        return real_record(webhook_id, event_id, ok=ok, status_code=status_code, error=error)

    monkeypatch.setattr(store, "record_webhook_delivery", flaky_record)
    caplog.set_level(logging.WARNING)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)  # must not raise

    assert calls == [_URL_BAD, _URL_GOOD]
    assert [row.webhook_id for row in rows] == [good_hook.webhook_id]
    assert store.get_webhook_delivery(bad_hook.webhook_id, event.id) is None
    assert store.get_webhook_delivery(good_hook.webhook_id, event.id).ok is True
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "OperationalError" in messages
    assert _SECRET not in messages
    assert _URL_BAD not in messages


@pytest.mark.unit
def test_store_fault_on_ledger_read_fails_closed_without_abort(monkeypatch, tmp_path, caplog):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    bad_hook = _webhook(store, webset.id, _URL_BAD)
    good_hook = _webhook(store, webset.id, _URL_GOOD)
    calls: list[str] = []
    real_get = store.get_webhook_delivery

    def flaky_get(webhook_id, event_id):
        if webhook_id == bad_hook.webhook_id:
            raise sqlite3.OperationalError("database is locked")
        return real_get(webhook_id, event_id)

    monkeypatch.setattr(store, "get_webhook_delivery", flaky_get)
    caplog.set_level(logging.WARNING)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    rows = mod.deliver_webhook(store, event, now=_T0)  # must not raise

    # The bad target is skipped before any POST (no unrecorded egress risk).
    assert calls == [_URL_GOOD]
    assert [row.webhook_id for row in rows] == [good_hook.webhook_id]
    assert store.get_webhook_delivery(good_hook.webhook_id, event.id).ok is True


@pytest.mark.unit
def test_store_fault_listing_webhooks_returns_no_rows(monkeypatch, tmp_path, caplog):
    store = _store(tmp_path)
    webset = _webset(store)
    event = _event(store, webset.id)
    _webhook(store, webset.id, _URL_GOOD)
    calls: list[int] = []

    def broken_list(webset_id):
        raise sqlite3.OperationalError(f"database is locked with {_SECRET}")

    monkeypatch.setattr(store, "list_webhooks", broken_list)
    caplog.set_level(logging.WARNING)

    _patch_transport(monkeypatch, lambda request: calls.append(1) or httpx.Response(200))
    assert mod.deliver_webhook(store, event, now=_T0) == []  # must not raise
    assert calls == []
    # Only the exception class is safe to log before any target is known.
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "OperationalError" in messages
    assert _SECRET not in messages


# ── append-path wiring (delivery fans out from the single event writer) ───────


def _emit_idle(store: WebsetStore, webset_id: str) -> WebsetEvent:
    """Append ``webset.idle`` through the production emitter (not the store)."""
    search = store.add_search(
        WebsetSearch(
            webset_id=webset_id,
            query="photonics startups",
            criteria=[VerificationCriterion(name="photonics", rule="photonics startup")],
        )
    )
    return mod.emit_webset_idle(store, webset_id, search.id)


@pytest.mark.unit
def test_append_event_delivers_to_subscribed_webhook_with_a_verifiable_signature(
    monkeypatch, tmp_path
):
    store = _store(tmp_path)
    webset = _webset(store)
    webhook = _webhook(store, webset.id, _URL_GOOD)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    _patch_transport(monkeypatch, handler)
    event = _emit_idle(store, webset.id)

    assert len(seen) == 1
    assert seen[0].method == "POST"
    body = seen[0].read()
    signature = seen[0].headers["x-digi-signature"]
    assert mod.verify_webhook_signature(webhook, body, signature) is True
    payload = json.loads(body.decode("utf-8"))
    assert payload["webset_id"] == webset.id
    assert payload["event"]["id"] == event.id
    row = store.get_webhook_delivery(webhook.webhook_id, event.id)
    assert row is not None and row.ok is True


@pytest.mark.unit
def test_append_event_without_subscribers_makes_no_request(monkeypatch, tmp_path):
    store = _store(tmp_path)
    webset = _webset(store)
    calls: list[int] = []

    _patch_transport(monkeypatch, lambda request: calls.append(1) or httpx.Response(200))
    _emit_idle(store, webset.id)

    assert calls == []


@pytest.mark.unit
def test_append_event_records_a_failed_delivery_and_does_not_raise(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    webhook = _webhook(store, webset.id, _URL_BAD)

    _patch_transport(monkeypatch, lambda request: httpx.Response(503))
    event = _emit_idle(store, webset.id)  # must not raise

    row = store.get_webhook_delivery(webhook.webhook_id, event.id)
    assert row is not None and row.ok is False and row.status_code == 503
    assert sleeps == [5.0, 25.0]


@pytest.mark.unit
def test_append_event_isolates_one_failing_target_from_the_others(monkeypatch, tmp_path, sleeps):
    store = _store(tmp_path)
    webset = _webset(store)
    bad_hook = _webhook(store, webset.id, _URL_BAD)
    good_hook = _webhook(store, webset.id, _URL_GOOD)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500 if str(request.url) == _URL_BAD else 200)

    _patch_transport(monkeypatch, handler)
    event = _emit_idle(store, webset.id)  # must not raise

    assert store.get_webhook_delivery(bad_hook.webhook_id, event.id).ok is False
    assert store.get_webhook_delivery(good_hook.webhook_id, event.id).ok is True
    assert calls == [_URL_BAD, _URL_BAD, _URL_BAD, _URL_GOOD]
