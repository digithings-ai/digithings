"""Watch provisioning unit tests (#4184) — offline only.

Pins ``monitors/provisioning.py``: the OSS path is byte-for-byte the old local
mint, and the EXA path is fail-closed remote-first (validate → remote create →
require monitor id + webhookSecret → persist), with best-effort remote
compensation when the secret/id is missing or the local persist fails. The
adapter is monkeypatched at the provisioning seam; nothing opens a socket.
"""

from __future__ import annotations

import pytest
from digisearch.monitors import provisioning as prov
from digisearch.monitors.exa_adapter import ExaAdapterError
from digisearch.monitors.models import (
    DeliveryConfig,
    DeliveryTarget,
    Watch,
    WatchSchedule,
)
from digisearch.monitors.provisioning import WatchProvisioningError, create_watch_provisioned
from digisearch.monitors.store import MonitorStore

pytestmark = pytest.mark.unit

# An address literal keeps the delivery validator offline (no getaddrinfo).
_HOOK = "https://93.184.216.34/hook"
_REMOTE_SECRET = "r" * 32


def _store(tmp_path) -> MonitorStore:
    return MonitorStore(db_path=str(tmp_path / "m.sqlite3"))


def _watch(
    *,
    backend: str = "exa",
    mode: str = "interval",
    interval_seconds: int | None = 86400,
    targets: list[DeliveryTarget] | None = None,
) -> Watch:
    schedule = (
        WatchSchedule(mode="interval", interval_seconds=interval_seconds)
        if mode == "interval"
        else WatchSchedule(mode="cron", cron="0 0 * * *")
    )
    delivery = DeliveryConfig(
        mode="poll",
        targets=([DeliveryTarget(kind="webhook", url=_HOOK)] if targets is None else targets),
    )
    return Watch(
        name="etf", query="etf flows", schedule=schedule, delivery=delivery, backend=backend
    )


def _fake_create(monkeypatch, doc: dict, calls: dict | None = None):
    """Patch the provisioning seam's remote create; return the captured calls dict."""

    def _create(**kwargs):
        if calls is not None:
            calls.update(kwargs)
        return doc

    monkeypatch.setattr(prov, "create_exa_monitor", _create)
    return calls


def _capture_deletes(monkeypatch) -> list[dict]:
    deleted: list[dict] = []

    def _delete(**kwargs):
        deleted.append(kwargs)

    monkeypatch.setattr(prov, "delete_exa_monitor", _delete)
    return deleted


def _forbid_create(monkeypatch) -> list[dict]:
    """Fail loudly if the remote create is attempted; returns the call log."""
    calls: list[dict] = []

    def _create(**kwargs):
        calls.append(kwargs)
        raise AssertionError(f"unexpected remote create: {kwargs}")

    monkeypatch.setattr(prov, "create_exa_monitor", _create)
    return calls


# --- OSS path ---------------------------------------------------------------------


@pytest.mark.unit
def test_oss_path_keeps_local_mint_and_never_calls_the_adapter(monkeypatch, tmp_path):
    calls: list[dict] = []

    def _create(**kwargs):
        calls.append(kwargs)
        raise AssertionError("oss watches must never provision remotely")

    monkeypatch.setattr(prov, "create_exa_monitor", _create)
    store = _store(tmp_path)
    created, secret = create_watch_provisioned(store, _watch(backend="oss"))

    assert calls == []
    assert created.watch_id
    assert created.exa_monitor_id is None
    assert len(secret) == 64
    assert store.get_delivery_secret(created.watch_id) == secret


# --- EXA happy path ---------------------------------------------------------------


@pytest.mark.unit
def test_exa_happy_path_persists_remote_id_and_secret(monkeypatch, tmp_path):
    calls: dict = {}
    _fake_create(
        monkeypatch, {"id": "exa_mon_1", "status": "active", "webhookSecret": _REMOTE_SECRET}, calls
    )
    deleted = _capture_deletes(monkeypatch)
    store = _store(tmp_path)

    created, secret = create_watch_provisioned(store, _watch(), api_key="k")

    assert calls == {
        "query": "etf flows",
        "webhook_url": _HOOK,
        "schedule": "1d",
        "api_key": "k",
    }
    assert created.exa_monitor_id == "exa_mon_1"
    assert secret == _REMOTE_SECRET
    assert store.get_delivery_secret(created.watch_id) == _REMOTE_SECRET
    assert store.get_watch(created.watch_id).exa_monitor_id == "exa_mon_1"
    assert deleted == []


# --- Schedule / target validation --------------------------------------------------


@pytest.mark.unit
def test_exa_cron_refused_without_remote_call_or_write(monkeypatch, tmp_path):
    calls = _forbid_create(monkeypatch)
    store = _store(tmp_path)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(store, _watch(mode="cron"))
    assert (ei.value.status_code, ei.value.code) == (422, "exa_schedule_unsupported")
    assert calls == []
    assert store.list_watches() == []


@pytest.mark.unit
def test_exa_needs_a_webhook_delivery_target(monkeypatch, tmp_path):
    calls = _forbid_create(monkeypatch)
    store = _store(tmp_path)
    for targets in (
        [],
        [DeliveryTarget(kind="email", email_to=["a@b.co"])],
        [DeliveryTarget(kind="webhook", url=None)],
        [DeliveryTarget(kind="webhook", url="   ")],
        [DeliveryTarget(kind="slack", url="https://93.184.216.34/hook")],
    ):
        with pytest.raises(WatchProvisioningError) as ei:
            create_watch_provisioned(store, _watch(targets=targets))
        assert (ei.value.status_code, ei.value.code) == (422, "exa_webhook_target_missing")
    assert calls == []
    assert store.list_watches() == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("interval_seconds", "period"),
    [(86400, "1d"), (172800, "2d"), (3600, "1h"), (7200, "2h"), (60, "1m"), (120, "2m")],
)
def test_exa_period_mapping_is_exact(monkeypatch, tmp_path, interval_seconds, period):
    calls: dict = {}
    _fake_create(monkeypatch, {"id": "exa_mon_1", "webhookSecret": _REMOTE_SECRET}, calls)
    create_watch_provisioned(_store(tmp_path), _watch(interval_seconds=interval_seconds))
    assert calls["schedule"] == period


@pytest.mark.unit
@pytest.mark.parametrize("interval_seconds", [90, 61, 86399, 3661])
def test_exa_inexact_period_refused_without_remote_call(monkeypatch, tmp_path, interval_seconds):
    calls = _forbid_create(monkeypatch)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(_store(tmp_path), _watch(interval_seconds=interval_seconds))
    assert (ei.value.status_code, ei.value.code) == (422, "exa_schedule_unsupported")
    assert calls == []


# --- Adapter error mapping ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("adapter_code", "status_code", "code"),
    [
        ("exa_request_invalid", 422, "exa_request_invalid"),
        ("exa_api_error", 502, "exa_api_error"),
        ("exa_tier_gated", 502, "exa_api_error"),
        ("exa_not_configured", 502, "exa_api_error"),
        ("exa_webhook_rejected", 502, "exa_api_error"),
        ("exa_monitor_not_found", 502, "exa_api_error"),
    ],
)
def test_adapter_errors_map_deterministically(
    monkeypatch, tmp_path, adapter_code, status_code, code
):
    def _boom(**kwargs):
        raise ExaAdapterError(adapter_code, "remote said no")

    monkeypatch.setattr(prov, "create_exa_monitor", _boom)
    store = _store(tmp_path)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(store, _watch())
    assert (ei.value.status_code, ei.value.code) == (status_code, code)
    assert "remote said no" in str(ei.value)
    assert store.list_watches() == []


# --- Missing remote fields + compensation ------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc",
    [
        {"id": "exa_mon_1"},
        {"id": "exa_mon_1", "webhookSecret": None},
        {"id": "exa_mon_1", "webhookSecret": "   "},
        {"id": "exa_mon_1", "webhookSecret": 7},
    ],
)
def test_missing_webhook_secret_compensates_and_fails_closed(monkeypatch, tmp_path, doc):
    _fake_create(monkeypatch, doc)
    deleted = _capture_deletes(monkeypatch)
    store = _store(tmp_path)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(store, _watch(), api_key="k")
    assert (ei.value.status_code, ei.value.code) == (502, "exa_webhook_secret_missing")
    assert deleted == [{"exa_monitor_id": "exa_mon_1", "api_key": "k"}]
    assert store.list_watches() == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc",
    [
        {"webhookSecret": _REMOTE_SECRET},
        {"id": None, "webhookSecret": _REMOTE_SECRET},
        {"id": "   ", "webhookSecret": _REMOTE_SECRET},
        {"id": 7, "webhookSecret": _REMOTE_SECRET},
    ],
)
def test_missing_monitor_id_never_writes_and_has_nothing_to_compensate(monkeypatch, tmp_path, doc):
    _fake_create(monkeypatch, doc)
    deleted = _capture_deletes(monkeypatch)
    store = _store(tmp_path)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(store, _watch(), api_key="k")
    assert (ei.value.status_code, ei.value.code) == (502, "exa_monitor_id_missing")
    assert deleted == []
    assert store.list_watches() == []


@pytest.mark.unit
def test_compensation_delete_failure_does_not_mask_the_original_error(monkeypatch, tmp_path):
    _fake_create(monkeypatch, {"id": "exa_mon_1"})

    def _boom(**kwargs):
        raise ExaAdapterError("exa_monitor_not_found", "already gone")

    monkeypatch.setattr(prov, "delete_exa_monitor", _boom)
    with pytest.raises(WatchProvisioningError) as ei:
        create_watch_provisioned(_store(tmp_path), _watch())
    assert ei.value.code == "exa_webhook_secret_missing"


@pytest.mark.unit
@pytest.mark.parametrize("failing_call", ["create_watch", "set_delivery_secret"])
def test_local_persist_failure_compensates_and_reraises(monkeypatch, tmp_path, failing_call):
    _fake_create(monkeypatch, {"id": "exa_mon_1", "webhookSecret": _REMOTE_SECRET})
    deleted = _capture_deletes(monkeypatch)
    store = _store(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("local store exploded")

    monkeypatch.setattr(store, failing_call, _boom)
    with pytest.raises(RuntimeError, match="local store exploded"):
        create_watch_provisioned(store, _watch(), api_key="k")
    assert deleted == [{"exa_monitor_id": "exa_mon_1", "api_key": "k"}]
