"""Phase C EXA monitor adapter (#4065/#4123) — live-pinned, offline only.

The adapter is reconciled against the live-pinned shapes captured 2026-09-16
(``.superpowers/sdd/4123-exa-shape-pin/spike-output-3.txt`` +
``signature-check.txt``): the webhook body is a NESTED event envelope and the
signature is a per-monitor ``webhookSecret``-keyed ``t.body`` HMAC. These tests
pin translation, signature verification, and the fail-closed posture only —
they never open a socket: ``httpx.MockTransport`` stubs every request, and the
public webhook URL is an address literal so ``getaddrinfo`` answers without
leaving the host.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest
from digisearch.monitors import exa_adapter as mod
from digisearch.monitors.exa_adapter import (
    ExaAdapterError,
    create_exa_monitor,
    delete_exa_monitor,
    exa_event_is_non_terminal,
    exa_monitor_id_from_payload,
    exa_monitor_secret_from_response,
    exa_run_to_monitor_run,
    verify_exa_signature,
)

pytestmark = pytest.mark.unit

# An address literal keeps validate_delivery's getaddrinfo offline.
_PUBLIC_URL = "https://93.184.216.34/hook"


# --- Live-recorded signature vector (2026-09-16) ----------------------------------
#
# The exact raw body and ``exa-signature`` header of the first delivery the
# Task 8a spike captured, with the per-monitor webhookSecret returned once by
# the create call. The secret belongs to a monitor deleted at the end of the
# spike; the vector only proves the wire scheme (recorded MATCH in
# signature-check.txt). The timestamp is historical, so the vector test runs
# with a tolerance wide enough to accept it.

_LIVE_EVENT_SECRET = "iwz3Z24SKOEHaznoRrHN72YM2kFZYoR8"
_LIVE_EVENT_SIGNATURE = (
    "t=1789559832,v1=b4b259813ea052cbecf92c52195ce1d1df5290be005fb98f8a7d160d51a0508b"
)
_LIVE_EVENT_BODY = (
    b'{"id":"event_01m2n17yp66bs3rqs66bs3rqs6","object":"event",'
    b'"type":"monitor.run.created","data":{"id":"01m2n17ym05s3p4b266b8yfp8c",'
    b'"monitorId":"01m2n17xx29t97bm8jca0x4p9j","status":"running","output":null,'
    b'"failReason":null,"startedAt":"2026-09-16T11:57:11.168Z","completedAt":null,'
    b'"failedAt":null,"cancelledAt":null,"durationMs":null,'
    b'"createdAt":"2026-09-16T11:57:11.168Z","updatedAt":"2026-09-16T11:57:11.170Z",'
    b'"metadata":null},"createdAt":"2026-09-16T11:57:11.000Z"}'
)


def _payload(**run_overrides: object) -> dict:
    """A live-shaped nested completed event; *run_overrides* patch the run."""
    run: dict = {
        "id": "exa_run_9",
        "monitorId": "exa_mon_1",
        "status": "completed",
        "output": {
            "results": [{"url": "https://a.com/1", "title": "A", "id": "https://a.com/1"}],
            "content": "Answer with [1] markers.",
        },
        "failReason": None,
        "startedAt": "2026-09-16T00:00:00Z",
        "completedAt": "2026-09-16T00:05:00Z",
        "failedAt": None,
        "cancelledAt": None,
        "durationMs": 300000,
        "createdAt": "2026-09-16T00:00:00Z",
        "updatedAt": "2026-09-16T00:05:00Z",
        "metadata": None,
    }
    run.update(run_overrides)
    return {
        "id": "event_1",
        "object": "event",
        "type": "monitor.run.completed",
        "data": run,
        "createdAt": "2026-09-16T00:00:00.000Z",
    }


def _patch_client(monkeypatch, handler) -> None:
    """Bind the adapter's httpx seam to a MockTransport *handler*."""
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda: httpx.Client(transport=transport))


def _forbid_http(monkeypatch) -> None:
    """Fail loudly if any HTTP call is attempted."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected EXA call: {request.method} {request.url}")

    _patch_client(monkeypatch, handler)


# --- Signature verification (§ 2) --------------------------------------------------


def test_verify_exa_signature_matches_live_recorded_vector():
    """The recorded delivery verifies byte-for-byte against the live scheme."""
    assert (
        verify_exa_signature(
            header=_LIVE_EVENT_SIGNATURE,
            body=_LIVE_EVENT_BODY,
            secret=_LIVE_EVENT_SECRET,
            tolerance_s=10**9,
        )
        is True
    )


def test_verify_exa_signature_rejects_wrong_secret_and_tampered_body():
    header = _LIVE_EVENT_SIGNATURE
    assert (
        verify_exa_signature(
            header=header,
            body=_LIVE_EVENT_BODY,
            secret="0" * 32,
            tolerance_s=10**9,
        )
        is False
    )
    assert (
        verify_exa_signature(
            header=header,
            body=_LIVE_EVENT_BODY + b" ",
            secret=_LIVE_EVENT_SECRET,
            tolerance_s=10**9,
        )
        is False
    )


def test_verify_exa_signature_enforces_the_timestamp_window():
    now = int(time.time())
    body = b'{"ok":true}'
    secret = "s3cret"
    fresh = _sign(secret, body, now - 290)
    assert verify_exa_signature(header=fresh, body=body, secret=secret, tolerance_s=300) is True
    stale = _sign(secret, body, now - 301)
    assert verify_exa_signature(header=stale, body=body, secret=secret, tolerance_s=300) is False
    future = _sign(secret, body, now + 301)
    assert verify_exa_signature(header=future, body=body, secret=secret, tolerance_s=300) is False


def test_verify_exa_signature_malformed_headers_fail_closed():
    body = b'{"ok":true}'
    secret = "s3cret"
    good = _sign(secret, body, int(time.time()))
    for header in (
        "",
        "nope",
        "t=abc,v1=deadbeef",
        f"t=,v1={good.split('v1=')[1]}",
        "t=1789559832",  # no v1
        "v1=deadbeef",  # no t
        "t=1789559832,v1=",  # empty v1
        "t=1789559832;v1=deadbeef",  # wrong separator
    ):
        assert verify_exa_signature(header=header, body=body, secret=secret) is False
    assert verify_exa_signature(header=good, body=body, secret="") is False
    assert verify_exa_signature(header=good, body=b"\xff\xfe", secret=secret) is False


def _sign(secret: str, body: bytes, t: int) -> str:
    """Build the live scheme's header (``t.body`` HMAC-SHA256, hex)."""
    import hashlib
    import hmac

    v1 = hmac.new(secret.encode(), f"{t}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


# --- Translation against the nested envelope (§ 1) --------------------------------


def test_exa_run_translates_nested_completed_event():
    run = exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload())
    assert run.backend == "exa"
    assert run.status == "ok"
    assert run.watch_id == "w1"
    assert run.run_id == "exa_run_9"  # the run id, never the event id
    assert run.trigger == "exa_webhook"
    assert run.results_all == [{"url": "https://a.com/1", "title": "A", "id": "https://a.com/1"}]
    assert run.results_new == run.results_all  # no newResults key exists
    assert run.dedup_stats == {"seen": 0, "new": 1, "changed": 0, "unchanged": 0}
    assert run.error is None
    assert run.started_at.isoformat() == "2026-09-16T00:00:00+00:00"
    assert run.finished_at.isoformat() == "2026-09-16T00:05:00+00:00"
    # query_snapshot keeps exactly the pinned-available facts; no invented query.
    assert run.query_snapshot == {
        "exa_run_id": "exa_run_9",
        "exa_event_type": "monitor.run.completed",
        "exa_monitor_id": "exa_mon_1",
    }


@pytest.mark.unit
def test_exa_run_completed_without_results_is_no_change():
    for output in (None, {}, {"results": []}, {"content": "no results key"}):
        run = exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(output=output))
        assert run.status == "no_change", output
        assert run.results_all == [] and run.results_new == []
        assert run.dedup_stats == {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}


@pytest.mark.unit
def test_exa_run_failed_uses_fail_reason_and_falls_back():
    run = exa_run_to_monitor_run(
        watch_id="w1",
        exa_payload=_payload(status="failed", failReason="remote recall exploded", output=None),
    )
    assert run.status == "failed"
    assert run.error == "remote recall exploded"
    assert run.results_new == []

    for blank in (None, "", "   "):
        fallback = exa_run_to_monitor_run(
            watch_id="w1",
            exa_payload=_payload(status="failed", failReason=blank, output=None),
        )
        assert fallback.status == "failed"
        assert fallback.error == "exa_run_failed"


@pytest.mark.unit
def test_exa_run_malformed_nested_envelope_fails_closed():
    for field, value in (
        ("data", None),
        ("data", "not-an-object"),
        ("type", None),
        ("type", "   "),
        ("type", 7),
        ("data", {}),
    ):
        payload = _payload()
        if field == "data" and value == {}:
            payload["data"] = {}
        else:
            payload[field] = value
        with pytest.raises(ExaAdapterError) as ei:
            exa_run_to_monitor_run(watch_id="w1", exa_payload=payload)
        assert ei.value.code == "exa_payload_invalid"

    with pytest.raises(ExaAdapterError) as missing:
        exa_run_to_monitor_run(watch_id="w1", exa_payload={"type": "monitor.run.completed"})
    assert missing.value.code == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_run_malformed_status_fails_closed():
    for bad_status in (None, "", "   ", 7):
        with pytest.raises(ExaAdapterError) as ei:
            exa_run_to_monitor_run(
                watch_id="w1", exa_payload=_payload(status=bad_status, output=None)
            )
        assert ei.value.code == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_run_malformed_output_container_fails_closed():
    for bad_output in (
        "not-an-object",
        7,
        {"results": "not-a-list"},
        {"results": [1, 2]},
        {"results": None},
    ):
        with pytest.raises(ExaAdapterError) as ei:
            exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(output=bad_output))
        assert ei.value.code == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_run_non_terminal_status_fails_closed():
    for status in ("running", "cancelled", "queued"):
        with pytest.raises(ExaAdapterError) as ei:
            exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(status=status, output=None))
        assert ei.value.code == "exa_run_status_unknown"


@pytest.mark.unit
def test_exa_event_is_non_terminal_reads_the_nested_run():
    """Non-terminal is exclusion: everything but completed/failed/error (#4184)."""
    created = _payload(status="running", output=None)
    created["type"] = "monitor.run.created"
    assert exa_event_is_non_terminal(created) is True
    for terminal in ("completed", "failed", "error"):
        assert exa_event_is_non_terminal(_payload(status=terminal)) is False, terminal
    for non_terminal in ("running", "cancelled", "queued", "weird", "RUNNING"):
        assert exa_event_is_non_terminal(_payload(status=non_terminal)) is True, non_terminal
    with pytest.raises(ExaAdapterError) as ei:
        exa_event_is_non_terminal(_payload(status=None))
    assert ei.value.code == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_run_cost_is_advisory_passthrough():
    with_cost = exa_run_to_monitor_run(
        watch_id="w1", exa_payload=_payload(costDollars={"total": 0.01})
    )
    assert with_cost.cost_dollars == {"total": 0.01}
    without_cost = exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload())
    assert without_cost.cost_dollars is None


@pytest.mark.unit
def test_exa_monitor_id_extraction_requires_the_nested_envelope():
    assert exa_monitor_id_from_payload(_payload()) == "exa_mon_1"
    with pytest.raises(ExaAdapterError) as ei:
        exa_monitor_id_from_payload(_payload(monitorId=None))
    assert ei.value.code == "exa_monitor_id_missing"
    for malformed in ({}, {"monitorId": "exa_mon_1"}, {"data": "nope"}):
        with pytest.raises(ExaAdapterError) as invalid:
            exa_monitor_id_from_payload(malformed)
        assert invalid.value.code == "exa_payload_invalid"


# --- create_exa_monitor / secret surfacing (§ 4) -----------------------------------


@pytest.mark.unit
def test_exa_create_without_public_webhook_rejected():
    with pytest.raises(ExaAdapterError) as ei:
        create_exa_monitor(query="etf flows", webhook_url="http://127.0.0.1:3000/h", api_key="k")
    assert "cannot point to localhost" in str(ei.value)
    assert ei.value.code == "webhook_url_private"


@pytest.mark.unit
def test_exa_create_validates_delivery_before_resolving_the_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    _forbid_http(monkeypatch)
    with pytest.raises(ExaAdapterError) as ei:
        create_exa_monitor(query="etf flows", webhook_url="http://127.0.0.1:3000/h")
    # No key is set, yet the webhook rejection wins: validation ran first.
    assert ei.value.code == "webhook_url_private"


@pytest.mark.unit
def test_exa_create_without_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    _forbid_http(monkeypatch)
    with pytest.raises(ExaAdapterError) as ei:
        create_exa_monitor(query="etf flows", webhook_url=_PUBLIC_URL)
    assert ei.value.code == "exa_not_configured"
    assert "EXA_API_KEY" in str(ei.value)  # never a silent OSS fallback


@pytest.mark.unit
def test_exa_create_posts_monitor_and_returns_created_response(monkeypatch):
    seen: dict = {}
    created_body = {
        "id": "01m2n17xx29t97bm8jca0x4p9j",
        "name": None,
        "status": "active",
        "search": {"query": "etf flows"},
        "trigger": {"type": "interval", "period": "1d"},
        "outputSchema": None,
        "metadata": None,
        "webhook": {"url": _PUBLIC_URL},
        "nextRunAt": None,
        "createdAt": "2026-09-16T11:57:10.434Z",
        "updatedAt": "2026-09-16T11:57:10.478Z",
        "webhookSecret": "iwz3Z24SKOEHaznoRrHN72YM2kFZYoR8",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.read())
        return httpx.Response(201, json=created_body)

    _patch_client(monkeypatch, handler)
    created = create_exa_monitor(
        query="etf flows", webhook_url=_PUBLIC_URL, schedule="1d", api_key="k"
    )
    assert created == created_body
    assert exa_monitor_secret_from_response(created) == "iwz3Z24SKOEHaznoRrHN72YM2kFZYoR8"
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.exa.ai/monitors"
    assert seen["key"] == "k"
    assert seen["body"] == {
        "search": {"query": "etf flows"},
        "trigger": {"type": "interval", "period": "1d"},
        "webhook": {"url": _PUBLIC_URL},
    }


@pytest.mark.unit
def test_exa_monitor_secret_accessor_is_total():
    assert exa_monitor_secret_from_response({"webhookSecret": "sec"}) == "sec"
    for doc in ({}, {"webhookSecret": None}, {"webhookSecret": ""}, {"webhookSecret": 7}):
        assert exa_monitor_secret_from_response(doc) is None


@pytest.mark.unit
def test_exa_create_tier_gated_401_is_fail_closed(monkeypatch):
    for status in (401, 403):

        def handler(request: httpx.Request, status: int = status) -> httpx.Response:
            return httpx.Response(status, json={"error": "Upgrade to a Pro plan"})

        _patch_client(monkeypatch, handler)
        with pytest.raises(ExaAdapterError) as ei:
            create_exa_monitor(query="etf flows", webhook_url=_PUBLIC_URL, api_key="k")
        assert ei.value.code == "exa_tier_gated"
        assert "Upgrade to a Pro plan" in str(ei.value)  # tier, not key-missing


@pytest.mark.unit
def test_exa_create_maps_remote_webhook_4xx_verbatim(monkeypatch):
    for message in (
        "[webhook.url]: Webhook URL cannot point to localhost, .local domains, "
        "or private IP addresses",
        "[webhook]: Required",
    ):

        def handler(request: httpx.Request, message: str = message) -> httpx.Response:
            return httpx.Response(400, text=message)

        _patch_client(monkeypatch, handler)
        with pytest.raises(ExaAdapterError) as ei:
            create_exa_monitor(query="etf flows", webhook_url=_PUBLIC_URL, api_key="k")
        assert ei.value.code == "exa_webhook_rejected"
        assert str(ei.value) == message  # verbatim, never re-worded


@pytest.mark.unit
def test_exa_create_rejects_blank_input_before_calling_exa(monkeypatch):
    _forbid_http(monkeypatch)
    with pytest.raises(ExaAdapterError) as ei:
        create_exa_monitor(query="   ", webhook_url=_PUBLIC_URL, api_key="k")
    assert ei.value.code == "exa_request_invalid"


# --- delete_exa_monitor ------------------------------------------------------------


@pytest.mark.unit
def test_exa_delete_targets_monitor_path_and_accepts_2xx(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": "01k_mon", "status": "active"})

    _patch_client(monkeypatch, handler)
    assert delete_exa_monitor(exa_monitor_id="01k_mon", api_key="k") is None
    assert seen == {"method": "DELETE", "url": "https://api.exa.ai/monitors/01k_mon"}


@pytest.mark.unit
def test_exa_delete_fails_closed_on_401_and_404(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Upgrade to a Pro plan"})

    _patch_client(monkeypatch, handler)
    with pytest.raises(ExaAdapterError) as ei:
        delete_exa_monitor(exa_monitor_id="01k_mon", api_key="k")
    assert ei.value.code == "exa_tier_gated"

    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "monitor not found"})

    _patch_client(monkeypatch, not_found)
    with pytest.raises(ExaAdapterError) as ei:
        delete_exa_monitor(exa_monitor_id="01k_mon", api_key="k")
    assert ei.value.code == "exa_monitor_not_found"
