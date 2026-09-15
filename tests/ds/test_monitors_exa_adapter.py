"""Phase C EXA monitor adapter (#4065, Task 8c) — EXPERIMENTAL, offline only.

The adapter is marked EXPERIMENTAL + tier-gated: its remote shapes are derived
from observed EXA docs/error strings (2026-09-14) and are NOT live-validated
(the Task 8a live spike was deferred; a live-pin follow-up issue owns the
record). These tests pin the translation table and the fail-closed posture
only — they never open a socket: ``httpx.MockTransport`` stubs every request,
and the public webhook URL is an address literal so ``getaddrinfo`` answers
without leaving the host.
"""

from __future__ import annotations

import json

import httpx
import pytest
from digisearch.monitors import exa_adapter as mod
from digisearch.monitors.exa_adapter import (
    ExaAdapterError,
    create_exa_monitor,
    delete_exa_monitor,
    exa_monitor_id_from_payload,
    exa_run_to_monitor_run,
)

pytestmark = pytest.mark.unit

# An address literal keeps validate_delivery's getaddrinfo offline.
_PUBLIC_URL = "https://93.184.216.34/hook"


def _payload(**overrides: object) -> dict:
    payload: dict = {
        "id": "exa_run_9",
        "monitorId": "exa_mon_1",
        "status": "completed",
        "trigger": "schedule",
        "createdAt": "2026-09-14T00:00:00Z",
        "completedAt": "2026-09-14T00:01:00Z",
        "query": "etf flows",
        "results": [{"url": "https://a.com/1", "title": "A"}],
        "newResults": [{"url": "https://a.com/1", "title": "A"}],
    }
    payload.update(overrides)
    return payload


def _patch_client(monkeypatch, handler) -> None:
    """Bind the adapter's httpx seam to a MockTransport *handler*."""
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mod, "_client_for", lambda: httpx.Client(transport=transport))


def _forbid_http(monkeypatch) -> None:
    """Fail loudly if any HTTP call is attempted."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected EXA call: {request.method} {request.url}")

    _patch_client(monkeypatch, handler)


# --- Translation (Step 1 test a + matrix) ----------------------------------------


def test_exa_run_translates_to_canonical_envelope():
    run = exa_run_to_monitor_run(
        watch_id="w1",
        exa_payload={
            "id": "exa_run_9",
            "status": "completed",
            "trigger": "schedule",
            "createdAt": "2026-09-14T00:00:00Z",
            "completedAt": "2026-09-14T00:01:00Z",
            "query": "etf flows",
            "results": [{"url": "https://a.com/1", "title": "A"}],
            "newResults": [{"url": "https://a.com/1", "title": "A"}],
        },
    )
    assert run.backend == "exa"
    assert run.status == "ok"
    assert run.results_new == [{"url": "https://a.com/1", "title": "A"}]
    assert run.dedup_stats["new"] == 1
    # Additions on the pinned behavior: canonical envelope, never a shape fork.
    assert run.watch_id == "w1"
    assert run.run_id == "exa_run_9"
    assert run.trigger == "exa_webhook"
    assert run.results_all == [{"url": "https://a.com/1", "title": "A"}]
    assert run.error is None


@pytest.mark.unit
def test_exa_run_completed_without_new_results_is_no_change():
    run = exa_run_to_monitor_run(
        watch_id="w1",
        exa_payload=_payload(
            results=[{"url": "https://a.com/1"}, {"url": "https://a.com/2"}],
            newResults=[],
        ),
    )
    assert run.status == "no_change"
    assert run.results_new == []
    assert len(run.results_all) == 2
    # seen/unchanged are EXA's remote-dedup remainder; changed stays 0.
    assert run.dedup_stats == {"seen": 2, "new": 0, "changed": 0, "unchanged": 2}


@pytest.mark.unit
def test_exa_run_failed_passes_error_through():
    for status in ("failed", "error"):
        run = exa_run_to_monitor_run(
            watch_id="w1",
            exa_payload=_payload(status=status, error="remote recall exploded", newResults=[]),
        )
        assert run.status == "failed"
        assert run.error == "remote recall exploded"
        assert run.results_new == []


@pytest.mark.unit
def test_exa_run_failed_without_error_text_still_fails_loudly():
    run = exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(status="failed"))
    assert run.status == "failed"
    assert run.error == "exa_run_failed"


@pytest.mark.unit
def test_exa_run_missing_result_lists_yields_empty_statistics():
    run = exa_run_to_monitor_run(
        watch_id="w1",
        exa_payload={"id": "exa_run_9", "status": "completed", "query": "etf flows"},
    )
    assert run.status == "no_change"
    assert run.results_all == [] and run.results_new == []
    assert run.dedup_stats == {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}


@pytest.mark.unit
def test_exa_run_malformed_result_container_fails_closed():
    """Present-but-malformed results must not read as no_change (fail closed)."""
    for field, value in (
        ("results", "not-a-list"),
        ("results", [{"url": "https://a.com/1"}, "oops"]),
        ("newResults", {"url": "https://a.com/1"}),
        ("newResults", [1, 2]),
        # A present null is shape drift too: coercing it to [] would skip delivery.
        ("newResults", None),
    ):
        with pytest.raises(ExaAdapterError) as ei:
            exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(**{field: value}))
        assert ei.value.code == "exa_payload_invalid"
        assert field in str(ei.value)


@pytest.mark.unit
def test_exa_run_cost_is_advisory_passthrough():
    with_cost = exa_run_to_monitor_run(
        watch_id="w1", exa_payload=_payload(costDollars={"total": 0.01})
    )
    assert with_cost.cost_dollars == {"total": 0.01}
    without_cost = exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload())
    assert without_cost.cost_dollars is None


@pytest.mark.unit
def test_exa_run_unknown_status_fails_closed():
    with pytest.raises(ExaAdapterError) as ei:
        exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(status="running"))
    assert ei.value.code == "exa_run_status_unknown"

    with pytest.raises(ExaAdapterError) as missing:
        exa_run_to_monitor_run(watch_id="w1", exa_payload=_payload(status=None))
    assert missing.value.code == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_run_monitor_id_extraction_fails_closed():
    assert exa_monitor_id_from_payload({"monitorId": "exa_mon_1"}) == "exa_mon_1"
    for bad in ({}, {"monitorId": ""}, {"monitorId": 7}):
        with pytest.raises(ExaAdapterError) as ei:
            exa_monitor_id_from_payload(bad)
        assert ei.value.code == "exa_monitor_id_missing"


# --- create_exa_monitor ------------------------------------------------------------


@pytest.mark.unit  # Step 1 test b
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

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.read())
        return httpx.Response(201, json={"id": "01k_mon", "webhookSecret": "whsec"})

    _patch_client(monkeypatch, handler)
    created = create_exa_monitor(
        query="etf flows", webhook_url=_PUBLIC_URL, schedule="1d", api_key="k"
    )
    assert created == {"id": "01k_mon", "webhookSecret": "whsec"}
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.exa.ai/monitors"
    assert seen["key"] == "k"
    assert seen["body"] == {
        "search": {"query": "etf flows"},
        "trigger": {"type": "interval", "period": "1d"},
        "webhook": {"url": _PUBLIC_URL},
    }


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
        "[webhook.url]: Webhook URL cannot point to localhost or private IPs",
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
        return httpx.Response(204)

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
