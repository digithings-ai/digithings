"""Phase C monitor models (#4065, Task 1).

Pins the canonical ``Watch`` / ``MonitorRun`` envelope: default delivery is
poll with no targets, the interval floor is 60s, cron mode requires ``cron``,
``search_type`` is validated against the landed EXA alias set, and the run
envelope carries the dedup stats downstream consumers read. Pure model tests —
no network, no store.
"""

from __future__ import annotations

from typing import Any

import pytest
from digisearch.monitors.models import DeliveryConfig, MonitorRun, Watch
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_BASE_WATCH: dict[str, Any] = {
    "name": "etf flows",
    "query": "bitcoin etf flows",
    "schedule": {"mode": "interval", "interval_seconds": 3600},
}


def _watch(**overrides: Any) -> Watch:
    return Watch.model_validate({**_BASE_WATCH, **overrides})


def _run_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "r1",
        "watch_id": "w1",
        "status": "ok",
        "trigger": "manual",
        "started_at": "2026-09-14T00:00:00Z",
        "finished_at": "2026-09-14T00:01:00Z",
        "query_snapshot": {"query": "q"},
        "results_all": [],
        "results_new": [],
        "dedup_stats": {"seen": 0, "new": 0, "changed": 0, "unchanged": 0},
    }
    payload.update(overrides)
    return payload


def test_watch_defaults_poll_no_targets():
    w = Watch.model_validate(
        {
            "name": "etf flows",
            "query": "bitcoin etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
        }
    )
    assert w.delivery.mode == "poll"
    assert w.delivery.targets == []
    assert w.backend == "oss"
    assert w.dedup.match == "url_content"
    assert w.search_type == "auto"
    assert w.num_results == 8
    assert w.watch_id == ""
    assert w.exa_monitor_id is None


def test_interval_minimum_rejected():
    with pytest.raises(ValidationError):
        Watch.model_validate(
            {"name": "x", "query": "y", "schedule": {"mode": "interval", "interval_seconds": 5}}
        )


def test_interval_floor_boundary_accepted():
    w = _watch(schedule={"mode": "interval", "interval_seconds": 60})
    assert w.schedule.interval_seconds == 60


def test_interval_mode_requires_interval_seconds():
    with pytest.raises(ValidationError, match="interval_seconds"):
        _watch(schedule={"mode": "interval"})


def test_cron_mode_requires_cron():
    with pytest.raises(ValidationError, match="cron"):
        _watch(schedule={"mode": "cron"})
    w = _watch(schedule={"mode": "cron", "cron": "0 9 * * 1-5"})
    assert w.schedule.cron == "0 9 * * 1-5"
    assert w.schedule.interval_seconds is None


def test_schedule_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        _watch(schedule={"mode": "interval", "interval_seconds": 3600, "bogus": 1})


def test_watch_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        _watch(bogus=1)


def test_search_type_validated_against_landed_aliases():
    assert _watch(search_type="deep-reasoning").search_type == "deep-reasoning"
    with pytest.raises(ValidationError, match="invalid search_type"):
        _watch(search_type="definitely-not-a-search-type")


def test_num_results_bounds_are_exa_cap():
    assert _watch(num_results=1).num_results == 1
    assert _watch(num_results=100).num_results == 100
    with pytest.raises(ValidationError):
        _watch(num_results=0)
    with pytest.raises(ValidationError):
        _watch(num_results=101)


def test_delivery_targets_capped_at_five():
    targets = [{"kind": "webhook", "url": "https://example.test/hook"} for _ in range(6)]
    with pytest.raises(ValidationError):
        _watch(delivery={"targets": targets})
    assert len(_watch(delivery={"targets": targets[:5]}).delivery.targets) == 5


def test_delivery_config_defaults():
    cfg = DeliveryConfig()
    assert cfg.mode == "poll"
    assert cfg.targets == []


def test_watch_has_no_delivery_secret_field():
    assert "delivery_secret" not in Watch.model_fields


def test_monitor_run_envelope_keys():
    run = MonitorRun.model_validate(_run_payload(delivery=[{"target_kind": "webhook", "ok": True}]))
    assert run.dedup_stats["new"] == 0
    assert run.backend == "oss"
    assert run.cost_dollars is None
    assert run.error is None
    assert run.delivery[0].ok is True


def test_monitor_run_rejects_unknown_status_and_keys():
    with pytest.raises(ValidationError):
        MonitorRun.model_validate(_run_payload(status="exploded"))
    with pytest.raises(ValidationError):
        MonitorRun.model_validate(_run_payload(bogus=1))


# ── config gate: EXA-local-only options (#4249) ──────────────────────────────


def test_watch_bridge_round_trips_and_stays_strict():
    assert _watch().bridge is None
    watch = _watch(bridge={"webset_id": "ws_1"})
    assert watch.bridge is not None and watch.bridge.webset_id == "ws_1"
    with pytest.raises(ValidationError):
        _watch(bridge={"webset_id": ""})
    with pytest.raises(ValidationError):
        _watch(bridge={"webset_id": "ws_1", "extra": 1})


def test_config_gate_rejects_bridge_on_exa_watches():
    from digisearch.monitors.validation import watch_config_error

    assert watch_config_error(_watch(bridge={"webset_id": "ws_1"})) is None
    error = watch_config_error(
        _watch(backend="exa", exa_monitor_id="mon_1", bridge={"webset_id": "ws_1"})
    )
    assert error is not None
    assert error[0] == 422 and error[1] == "bridge_exa_unsupported"


def test_monitor_run_bridge_receipt_round_trips():
    assert MonitorRun.model_validate(_run_payload()).bridge is None
    run = MonitorRun.model_validate(
        _run_payload(bridge={"webset_id": "ws_1", "ok": True, "search_id": "wss_1"})
    )
    assert run.bridge is not None
    assert run.bridge.duplicate is False
