"""Phase C monitor HTTP API (#4065, Task 6).

Pins the §4.6 surface: watch CRUD, manual/poll trigger, run history, the
digiclaw wake-up tick, and the auth-exempt but secret-gated EXA webhook, plus
the R10 parameterized rate-limit matcher.

Offline only: the runner's shallow-recall boundary is stubbed (the Task 4
seam), and the store seam is patched with a factory that opens a fresh store
per call — SQLite connections are thread-bound (``check_same_thread`` stays
default True) and ``TestClient`` runs sync endpoints on a portal thread, so a
store instance built in the test thread would raise ``sqlite3.ProgrammingError``
on first use. Building it inside the handler thread is what production does.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

import pytest
from digisearch.web_exa import WebSearchData
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

# An address literal keeps the delivery validator offline (no getaddrinfo).
_PUBLIC_HOOK = "https://93.184.216.34/hook"


@pytest.fixture(autouse=True)
def _stub_shallow_recall(monkeypatch):
    """Keep every monitor test offline at the runner's recall boundary."""
    from digisearch.monitors import runner as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "_invoke_shallow_recall",
        lambda **kwargs: WebSearchData.model_validate(
            {"results": [{"url": "https://example.com/a", "title": "A", "text": "alpha"}]}
        ),
    )


_REMOTE_EXA_SECRET = "e" * 32


@pytest.fixture(autouse=True)
def _stub_exa_provisioning(monkeypatch):
    """Keep every monitor test offline at the remote EXA create boundary (#4184)."""
    from digisearch.monitors import provisioning as provisioning_mod

    monkeypatch.setattr(
        provisioning_mod,
        "create_exa_monitor",
        lambda **kwargs: {
            "id": "exa_mon_1",
            "status": "active",
            "webhookSecret": _REMOTE_EXA_SECRET,
        },
    )


@pytest.mark.unit
def test_create_trigger_poll_cycle(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    # Fresh store per call, built on the handler's thread (see module docstring).
    monkeypatch.setattr(
        srv, "get_monitor_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
        },
    )
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"watch", "delivery_secret"}  # R8
    wid = r.json()["watch"]["watch_id"]
    got = c.get(f"/v1/monitors/{wid}")
    assert got.status_code == 200
    assert "delivery_secret" not in got.text  # R8: never on GET
    t = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"})
    assert t.status_code == 201, t.text  # §4.6 table
    body = t.json()
    assert set(body) >= {"run_id", "watch_id", "status", "results_new", "dedup_stats"}
    h = c.get(f"/v1/monitors/{wid}/runs?limit=5")
    assert h.status_code == 200 and h.json()["runs"][0]["run_id"] == body["run_id"]


@pytest.mark.unit
def test_private_webhook_rejected_like_exa(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    monkeypatch.setattr(
        srv, "get_monitor_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {
                "mode": "webhook",
                "targets": [{"kind": "webhook", "url": "http://127.0.0.1:3000/h"}],
            },
        },
    )
    assert r.status_code == 422
    assert "cannot point to localhost" in r.text


@pytest.mark.unit
def test_datatap_watch_rejected(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    monkeypatch.setattr(
        srv, "get_monitor_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )
    c = TestClient(srv.app, headers=auth_headers())
    r = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "workspace_id": "datatap",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "datatap_monitors_disabled"


@pytest.mark.unit
def test_create_exa_provisions_remote_monitor_end_to_end(monkeypatch, tmp_path):
    """#4184: backend=exa provisions remotely, then persists id + remote secret."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors import provisioning as provisioning_mod
    from digisearch.monitors.store import MonitorStore

    seen: dict = {}

    def fake_create(**kwargs):
        seen.update(kwargs)
        return {"id": "exa_mon_42", "status": "active", "webhookSecret": "s" * 32}

    monkeypatch.setattr(provisioning_mod, "create_exa_monitor", fake_create)
    c = _monitor_client()
    created = _create_watch(
        c, backend="exa", schedule={"mode": "interval", "interval_seconds": 86400}
    )

    assert seen == {
        "query": "etf flows",
        "webhook_url": _PUBLIC_HOOK,
        "schedule": "1d",
        "api_key": None,
    }
    wid = created["watch"]["watch_id"]
    assert created["watch"]["exa_monitor_id"] == "exa_mon_42"
    assert created["delivery_secret"] == "s" * 32

    stored = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    assert stored.get_watch(wid).exa_monitor_id == "exa_mon_42"
    assert stored.get_delivery_secret(wid) == "s" * 32
    assert "delivery_secret" not in c.get(f"/v1/monitors/{wid}").text  # R8


@pytest.mark.unit
def test_create_exa_refuses_cron_and_missing_webhook_target(monkeypatch, tmp_path):
    """#4184: EXA cannot express a cron, and its create needs a webhook URL."""
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()

    cron = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "backend": "exa",
            "schedule": {"mode": "cron", "cron": "0 0 * * *"},
            "delivery": {"mode": "poll", "targets": [{"kind": "webhook", "url": _PUBLIC_HOOK}]},
        },
    )
    assert cron.status_code == 422, cron.text
    assert cron.json()["error"]["code"] == "exa_schedule_unsupported"

    no_target = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "backend": "exa",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
        },
    )
    assert no_target.status_code == 422, no_target.text
    assert no_target.json()["error"]["code"] == "exa_webhook_target_missing"
    assert c.get("/v1/monitors").json()["watches"] == []


@pytest.mark.unit
def test_create_exa_502_when_remote_secret_missing(monkeypatch, tmp_path):
    """#4196: HTTP-level pin of the 502 paths — nothing is persisted on a miss."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors import provisioning as provisioning_mod

    monkeypatch.setattr(
        provisioning_mod, "create_exa_monitor", lambda **kwargs: {"id": "exa_mon_1"}
    )
    compensated: list[str] = []
    monkeypatch.setattr(
        provisioning_mod,
        "delete_exa_monitor",
        lambda **kwargs: compensated.append(kwargs["exa_monitor_id"]),
    )
    c = _monitor_client()
    r = c.post("/v1/monitors", json=_exa_watch_body())

    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "exa_webhook_secret_missing"
    assert compensated == ["exa_mon_1"]
    assert c.get("/v1/monitors").json()["watches"] == []


@pytest.mark.unit
def test_create_exa_502_when_remote_id_missing(monkeypatch, tmp_path):
    """#4196: no remote id → 502, nothing persisted, no remote id to compensate."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors import provisioning as provisioning_mod

    monkeypatch.setattr(
        provisioning_mod,
        "create_exa_monitor",
        lambda **kwargs: {"status": "active", "webhookSecret": "s" * 32},
    )
    c = _monitor_client()
    r = c.post("/v1/monitors", json=_exa_watch_body())

    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "exa_monitor_id_missing"
    assert c.get("/v1/monitors").json()["watches"] == []


@pytest.mark.unit
def test_patch_backend_flip_refused_and_rotation_still_gated(monkeypatch, tmp_path):
    """#4196: the flip-then-rotate repro 409s at the flip; state stays exa."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors.store import MonitorStore

    c = _monitor_client()
    created = _create_watch(c, backend="exa")
    wid = created["watch"]["watch_id"]

    flipped = c.patch(f"/v1/monitors/{wid}", json={"backend": "oss"})
    assert flipped.status_code == 409, flipped.text
    assert flipped.json()["error"]["code"] == "watch_backend_immutable"

    unchanged = c.get(f"/v1/monitors/{wid}").json()
    assert unchanged["backend"] == "exa"
    assert unchanged["exa_monitor_id"] == "exa_mon_1"
    stored_secret = MonitorStore(db_path=str(tmp_path / "m.sqlite3")).get_delivery_secret(wid)
    assert stored_secret == created["delivery_secret"]

    rotated = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": True})
    assert rotated.status_code == 409, rotated.text
    assert rotated.json()["error"]["code"] == "exa_secret_rotate_unsupported"
    assert (
        MonitorStore(db_path=str(tmp_path / "m.sqlite3")).get_delivery_secret(wid) == stored_secret
    )


@pytest.mark.unit
def test_patch_backend_oss_to_exa_refused_and_same_value_is_noop(monkeypatch, tmp_path):
    """#4196: the other flip direction is the same rule; same-value patches pass."""
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()

    oss = _create_watch(c)
    oss_id = oss["watch"]["watch_id"]
    upgraded = c.patch(f"/v1/monitors/{oss_id}", json={"backend": "exa"})
    assert upgraded.status_code == 409, upgraded.text
    assert upgraded.json()["error"]["code"] == "watch_backend_immutable"
    assert c.get(f"/v1/monitors/{oss_id}").json()["exa_monitor_id"] is None

    exa_id = _create_watch(c, backend="exa")["watch"]["watch_id"]
    noop = c.patch(f"/v1/monitors/{exa_id}", json={"backend": "exa"})
    assert noop.status_code == 200, noop.text
    assert noop.json()["backend"] == "exa"
    assert noop.json()["exa_monitor_id"] == "exa_mon_1"


@pytest.mark.unit
def test_patch_exa_monitor_id_clear_refused_and_delete_still_tears_down(monkeypatch, tmp_path):
    """#4196: a null-out cannot orphan the remote monitor that DELETE would clean."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    created = _create_watch(c, backend="exa")
    wid = created["watch"]["watch_id"]
    assert created["watch"]["exa_monitor_id"] == "exa_mon_1"

    cleared = c.patch(f"/v1/monitors/{wid}", json={"exa_monitor_id": None})
    assert cleared.status_code == 409, cleared.text
    assert cleared.json()["error"]["code"] == "monitor_exa_monitor_id_immutable"
    assert c.get(f"/v1/monitors/{wid}").json()["exa_monitor_id"] == "exa_mon_1"

    recorded: list[dict] = []
    monkeypatch.setattr(srv, "delete_exa_monitor", lambda **kwargs: recorded.append(kwargs))
    deleted = c.delete(f"/v1/monitors/{wid}")
    assert deleted.status_code == 200, deleted.text
    assert recorded == [{"exa_monitor_id": "exa_mon_1"}]  # the stored link, not a cleared one


@pytest.mark.unit
def test_patch_exa_monitor_id_refuses_cross_watch_id_and_allows_same_value(monkeypatch, tmp_path):
    """#4196: a patch cannot aim DELETE at another watch's remote monitor."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv
    from digisearch.monitors import provisioning as provisioning_mod

    remote_ids = iter(["exa_mon_a", "exa_mon_b"])
    monkeypatch.setattr(
        provisioning_mod,
        "create_exa_monitor",
        lambda **kwargs: {"id": next(remote_ids), "webhookSecret": "s" * 32},
    )
    c = _monitor_client()
    alpha = _create_watch(c, backend="exa")["watch"]
    other = _create_watch(c, backend="exa")["watch"]

    aimed = c.patch(
        f"/v1/monitors/{alpha['watch_id']}", json={"exa_monitor_id": other["exa_monitor_id"]}
    )
    assert aimed.status_code == 409, aimed.text
    assert aimed.json()["error"]["code"] == "monitor_exa_monitor_id_immutable"
    assert c.get(f"/v1/monitors/{alpha['watch_id']}").json()["exa_monitor_id"] == "exa_mon_a"

    noop = c.patch(f"/v1/monitors/{alpha['watch_id']}", json={"exa_monitor_id": "exa_mon_a"})
    assert noop.status_code == 200, noop.text
    assert noop.json()["exa_monitor_id"] == "exa_mon_a"

    recorded: list[dict] = []
    monkeypatch.setattr(srv, "delete_exa_monitor", lambda **kwargs: recorded.append(kwargs))
    assert c.delete(f"/v1/monitors/{alpha['watch_id']}").status_code == 200
    assert recorded == [{"exa_monitor_id": "exa_mon_a"}]  # never the other watch's id


@pytest.mark.unit
def test_patch_rotate_refused_on_stale_exa_monitor_id_misconfig(monkeypatch, tmp_path):
    """#4196: rotation is gated on remote presence, not only backend="exa"."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors.store import MonitorStore

    c = _monitor_client()
    created = _create_watch(c, exa_monitor_id="exa_mon_oss")
    wid = created["watch"]["watch_id"]
    assert created["watch"]["backend"] == "oss"

    refused = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": True})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "exa_secret_rotate_unsupported"
    stored_secret = MonitorStore(db_path=str(tmp_path / "m.sqlite3")).get_delivery_secret(wid)
    assert stored_secret == created["delivery_secret"]


@pytest.mark.unit
def test_patch_rotate_refused_on_exa_backed_watch(monkeypatch, tmp_path):
    """#4184: a locally minted secret would break EXA signature verification."""
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors.store import MonitorStore

    c = _monitor_client()
    created = _create_watch(c, backend="exa")
    wid = created["watch"]["watch_id"]

    refused = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": True})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "exa_secret_rotate_unsupported"
    stored = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    assert stored.get_delivery_secret(wid) == created["delivery_secret"]  # untouched

    renamed = c.patch(f"/v1/monitors/{wid}", json={"name": "renamed"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "renamed"

    oss = _create_watch(c)
    rotated = c.patch(
        f"/v1/monitors/{oss['watch']['watch_id']}", json={"rotate_delivery_secret": True}
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["delivery_secret"] != oss["delivery_secret"]


@pytest.mark.unit
def test_exa_webhook_exempt_but_secret_gated(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    _create_watch(_monitor_client(), backend="exa", exa_monitor_id="exa_mon_1")
    anon = TestClient(srv.app)  # no JWT: exemption lets it reach the handler
    body, _ = _signed_delivery(_event(), "not-the-watch-secret")
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
    # Route-level 401 (the middleware would answer its own auth code first).
    assert r.json()["error"]["code"] == "exa_bad_signature"


def _patch_monitor_store(monkeypatch, tmp_path) -> None:
    """Point the seam at a fresh per-request store (see module docstring)."""
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    monkeypatch.setattr(
        srv, "get_monitor_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )


def _monitor_client() -> TestClient:
    import digisearch.server as srv

    return TestClient(srv.app, headers=auth_headers())


def _event(*, event_type: str = "monitor.run.completed", **run_overrides: object) -> dict:
    """A live-pinned nested EXA event envelope; *run_overrides* patch ``data``."""
    run: dict = {
        "id": "exa_run_9",
        "monitorId": "exa_mon_1",
        "status": "completed",
        "output": {
            "results": [{"id": "https://a.com/1", "url": "https://a.com/1", "title": "A"}],
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
        "type": event_type,
        "data": run,
        "createdAt": "2026-09-16T00:00:00.000Z",
    }


def _signed_delivery(payload: dict, secret: str, *, t: int | None = None) -> tuple[bytes, dict]:
    """Serialize *payload* and sign it with the live ``t.body`` scheme."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = int(time.time()) if t is None else t
    v1 = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return body, {"exa-signature": f"t={ts},v1={v1}"}


def _create_watch(client: TestClient, **overrides: object) -> dict:
    body: dict = {
        "name": "etf",
        "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
    }
    if overrides.get("backend") == "exa" and "delivery" not in overrides:
        # #4184: an exa watch is provisioned remotely and needs a webhook target.
        body["delivery"] = {
            "mode": "poll",
            "targets": [{"kind": "webhook", "url": _PUBLIC_HOOK}],
        }
    body.update(overrides)
    r = client.post("/v1/monitors", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _exa_watch_body() -> dict:
    """A provisionable body whose remote answer the test controls per case."""
    return {
        "name": "etf",
        "query": "etf flows",
        "backend": "exa",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
        "delivery": {"mode": "poll", "targets": [{"kind": "webhook", "url": _PUBLIC_HOOK}]},
    }


@pytest.mark.unit
def test_patch_rotate_and_update_never_leaks_secret(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    created = _create_watch(c)
    wid = created["watch"]["watch_id"]
    first_secret = created["delivery_secret"]
    assert first_secret
    assert "delivery_secret" not in c.get(f"/v1/monitors/{wid}").text

    rotated = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": True})
    assert rotated.status_code == 200, rotated.text
    assert set(rotated.json()) == {"watch", "delivery_secret"}  # R8
    assert rotated.json()["delivery_secret"] != first_secret

    updated = c.patch(f"/v1/monitors/{wid}", json={"name": "renamed"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "renamed"
    assert updated.json()["watch_id"] == wid
    assert "delivery_secret" not in updated.text


@pytest.mark.unit
def test_patch_rotation_requires_literal_true(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    created = _create_watch(c)
    wid = created["watch"]["watch_id"]
    first_secret = created["delivery_secret"]

    for coerced in ("false", "true", 1):
        r = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": coerced})
        assert r.status_code == 200, r.text
        assert "delivery_secret" not in r.text  # only literal JSON true rotates

    def stored_secret() -> str | None:
        from digisearch.monitors.store import MonitorStore

        return MonitorStore(db_path=str(tmp_path / "m.sqlite3")).get_delivery_secret(wid)

    assert stored_secret() == first_secret

    rotated = c.patch(f"/v1/monitors/{wid}", json={"rotate_delivery_secret": True})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["delivery_secret"] not in (None, first_secret)
    assert stored_secret() == rotated.json()["delivery_secret"]


@pytest.mark.unit
def test_trigger_recall_failure_returns_persisted_failed_run(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    from digisearch.monitors import runner as runner_mod

    def _boom(**kwargs):
        raise RuntimeError("recall exploded")

    monkeypatch.setattr(runner_mod, "_invoke_shallow_recall", _boom)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]

    r = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"})
    assert r.status_code == 201, r.text  # the persisted failure is the record, not a 5xx
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"] == "recall exploded"
    assert body["results_all"] == [] and body["results_new"] == []

    runs = c.get(f"/v1/monitors/{wid}/runs").json()["runs"]
    assert [run["run_id"] for run in runs] == [body["run_id"]]
    assert runs[0]["status"] == "failed"
    detail = c.get(f"/v1/monitors/{wid}/runs/{body['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["error"] == "recall exploded"


@pytest.mark.unit
def test_watch_and_run_not_found_codes(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    assert c.get("/v1/monitors/nope").json()["error"]["code"] == "watch_not_found"
    assert c.patch("/v1/monitors/nope", json={"name": "x"}).status_code == 404
    assert c.delete("/v1/monitors/nope").json()["error"]["code"] == "watch_not_found"
    assert c.post("/v1/monitors/nope/trigger", json={}).json()["error"]["code"] == "watch_not_found"

    wid = _create_watch(c)["watch"]["watch_id"]
    missing_run = c.get(f"/v1/monitors/{wid}/runs/missing")
    assert missing_run.status_code == 404
    assert missing_run.json()["error"]["code"] == "run_not_found"
    bad_cursor = c.get(f"/v1/monitors/{wid}/runs?cursor=missing")
    assert bad_cursor.status_code == 404
    assert bad_cursor.json()["error"]["code"] == "run_not_found"


@pytest.mark.unit
def test_create_and_patch_reject_bad_schedule(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    bad_tz = {"mode": "interval", "interval_seconds": 3600, "timezone": "Mars/Olympus"}
    tz = c.post(
        "/v1/monitors",
        json={"name": "etf", "query": "etf flows", "schedule": bad_tz},
    )
    assert tz.status_code == 422
    assert tz.json()["error"]["code"] == "timezone_unknown"

    bad_cron = {"mode": "cron", "cron": "not a cron"}
    cron = c.post(
        "/v1/monitors",
        json={"name": "etf", "query": "etf flows", "schedule": bad_cron},
    )
    assert cron.status_code == 422
    assert cron.json()["error"]["code"] == "invalid_cron"

    wid = _create_watch(c)["watch"]["watch_id"]
    patched = c.patch(f"/v1/monitors/{wid}", json={"schedule": bad_tz})
    assert patched.status_code == 422
    assert patched.json()["error"]["code"] == "timezone_unknown"
    # Validation runs before persistence: the stored watch is untouched.
    assert c.get(f"/v1/monitors/{wid}").json()["schedule"]["timezone"] == "UTC"


@pytest.mark.unit
def test_non_numeric_cron_step_maps_to_invalid_cron(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    bad_cron = {"mode": "cron", "cron": "*/abc 0 0 0 0"}

    created = c.post(
        "/v1/monitors",
        json={"name": "etf", "query": "etf flows", "schedule": bad_cron},
    )
    assert created.status_code == 422, created.text
    assert created.json()["error"]["code"] == "invalid_cron"

    wid = _create_watch(c)["watch"]["watch_id"]
    patched = c.patch(f"/v1/monitors/{wid}", json={"schedule": bad_cron})
    assert patched.status_code == 422, patched.text
    assert patched.json()["error"]["code"] == "invalid_cron"
    # Validation runs before persistence: the stored watch is untouched.
    assert c.get(f"/v1/monitors/{wid}").json()["schedule"]["mode"] == "interval"


@pytest.mark.unit
def test_webhook_mode_without_targets_rejected(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    r = c.post(
        "/v1/monitors",
        json={
            "name": "etf",
            "query": "etf flows",
            "schedule": {"mode": "interval", "interval_seconds": 3600},
            "delivery": {"mode": "webhook", "targets": []},
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "webhook_url_required"


@pytest.mark.unit
def test_delete_retains_runs_and_run_detail(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]
    run = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"}).json()
    assert run["trigger"] == "poll"

    detail = c.get(f"/v1/monitors/{wid}/runs/{run['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run["run_id"]

    deleted = c.delete(f"/v1/monitors/{wid}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": wid}
    assert c.get(f"/v1/monitors/{wid}").status_code == 404
    kept = c.get(f"/v1/monitors/{wid}/runs")
    assert kept.status_code == 200
    assert [r["run_id"] for r in kept.json()["runs"]] == [run["run_id"]]


@pytest.mark.unit
def test_delete_exa_watch_tears_down_remote_best_effort(monkeypatch, tmp_path, caplog):
    """#4196: DELETE passes the stored monitor id; a remote failure never blocks it."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv
    from digisearch.monitors import provisioning as provisioning_mod

    monkeypatch.setattr(
        provisioning_mod,
        "create_exa_monitor",
        lambda **kwargs: {"id": "exa_mon_delete_7", "webhookSecret": "d" * 32},
    )
    recorded: list[dict] = []
    monkeypatch.setattr(srv, "delete_exa_monitor", lambda **kwargs: recorded.append(kwargs))
    c = _monitor_client()

    wid = _create_watch(c, backend="exa")["watch"]["watch_id"]
    deleted = c.delete(f"/v1/monitors/{wid}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": wid}
    assert recorded == [{"exa_monitor_id": "exa_mon_delete_7"}]

    other = _create_watch(c, backend="exa")["watch"]["watch_id"]

    def _boom(**kwargs):
        raise RuntimeError("remote delete exploded")

    monkeypatch.setattr(srv, "delete_exa_monitor", _boom)
    with caplog.at_level(logging.WARNING):
        still_deleted = c.delete(f"/v1/monitors/{other}")
    assert still_deleted.status_code == 200, still_deleted.text
    assert still_deleted.json() == {"deleted": other}
    assert c.get(f"/v1/monitors/{other}").status_code == 404
    assert "failed to delete EXA monitor" in caplog.text


@pytest.mark.unit
def test_delete_oss_watch_makes_no_remote_call(monkeypatch, tmp_path):
    """#4196: the OSS delete path stays adapter-free."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    def _forbidden(**kwargs):
        raise AssertionError("oss watch delete must not call the EXA adapter")

    monkeypatch.setattr(srv, "delete_exa_monitor", _forbidden)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]

    deleted = c.delete(f"/v1/monitors/{wid}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": wid}


@pytest.mark.unit
def test_tick_runs_due_watches_once(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]

    first = c.post("/v1/monitors/tick", json={})
    assert first.status_code == 200, first.text
    runs = first.json()["runs"]
    assert [r["watch_id"] for r in runs] == [wid]
    assert runs[0]["trigger"] == "schedule"

    second = c.post("/v1/monitors/tick", json={})
    assert second.status_code == 200
    assert second.json()["runs"] == []  # interval 3600 not due yet


@pytest.mark.unit
def test_list_watches_filters_workspace(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    alpha = _create_watch(c, workspace_id="alpha")["watch"]["watch_id"]
    beta = _create_watch(c, workspace_id="beta")["watch"]["watch_id"]

    listed = c.get("/v1/monitors")
    assert {w["watch_id"] for w in listed.json()["watches"]} == {alpha, beta}
    scoped = c.get("/v1/monitors?workspace_id=alpha")
    assert [w["watch_id"] for w in scoped.json()["watches"]] == [alpha]


@pytest.mark.unit
def test_monitor_routes_require_jwt():
    import digisearch.server as srv

    anon = TestClient(srv.app)
    assert anon.get("/v1/monitors").status_code == 401
    assert anon.post("/v1/monitors", json={}).status_code == 401
    assert anon.post("/v1/monitors/tick", json={}).status_code == 401
    # The webhook exemption is method-scoped: only POST is exempt (R1).
    assert anon.get("/v1/monitors/exa_webhook").status_code == 401


@pytest.mark.unit
def test_trigger_route_holds_ten_per_minute_through_middleware(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]
    # Neutralize the #4106 identity-aware multiplier so this test pins the
    # per-watch route budget itself (10/min), not the token headroom a bearer
    # caller gets by default (6x budget + 6x per-IP ceiling).
    monkeypatch.setenv("DIGISEARCH_AUTH_RATE_LIMIT_MULTIPLIER", "1")
    monkeypatch.setenv("DIGISEARCH_IP_CEILING_MULTIPLIER", "1")
    forwarded = {"X-Forwarded-For": "203.0.113.91"}  # unique IP: testclient bypasses limits
    for _ in range(10):
        r = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"}, headers=forwarded)
        assert r.status_code == 201, r.text
    limited = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"}, headers=forwarded)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"


@pytest.mark.unit
def test_exa_webhook_per_watch_secret_translates_and_persists(monkeypatch, tmp_path):
    """#4123: the delivery is verified with the watch's stored secret, then persisted."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    created = _create_watch(c, backend="exa", exa_monitor_id="exa_mon_1")
    wid = created["watch"]["watch_id"]
    secret = created["delivery_secret"]
    anon = TestClient(srv.app)

    body, _ = _signed_delivery(_event(), secret)
    unsigned = anon.post(
        "/v1/monitors/exa_webhook", content=body, headers={"Content-Type": "application/json"}
    )
    assert unsigned.status_code == 401  # never a static-secret fallback

    wrong_body, wrong_headers = _signed_delivery(_event(), "0" * len(secret))
    wrong = anon.post(
        "/v1/monitors/exa_webhook",
        content=wrong_body,
        headers={**wrong_headers, "Content-Type": "application/json"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "exa_bad_signature"

    non_ascii = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers=[(b"exa-signature", b"\xe9"), (b"Content-Type", b"application/json")],
    )
    assert non_ascii.status_code == 401  # never a 500 from header parsing

    signed_body, signed_headers = _signed_delivery(_event(), secret)
    matched = anon.post(
        "/v1/monitors/exa_webhook",
        content=signed_body,
        headers={**signed_headers, "Content-Type": "application/json"},
    )
    assert matched.status_code == 201, matched.text
    run = matched.json()
    assert run["backend"] == "exa"
    assert run["watch_id"] == wid
    assert run["run_id"] == "exa_run_9"  # the nested run id, never the event id
    assert run["status"] == "ok"
    assert run["trigger"] == "exa_webhook"
    assert run["results_new"] == [{"id": "https://a.com/1", "url": "https://a.com/1", "title": "A"}]

    runs = c.get(f"/v1/monitors/{wid}/runs").json()["runs"]
    assert [stored["run_id"] for stored in runs] == [run["run_id"]]


@pytest.mark.unit
def test_exa_webhook_non_terminal_event_acks_without_persisting(monkeypatch, tmp_path):
    """#4123: ``monitor.run.created`` (run ``running``) is acked, never stored."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    created = _create_watch(c, backend="exa", exa_monitor_id="exa_mon_1")
    wid = created["watch"]["watch_id"]
    secret = created["delivery_secret"]

    body, headers = _signed_delivery(
        _event(event_type="monitor.run.created", status="running", output=None), secret
    )
    anon = TestClient(srv.app)
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"acknowledged": True}
    assert c.get(f"/v1/monitors/{wid}/runs").json()["runs"] == []


@pytest.mark.unit
@pytest.mark.parametrize("status", ["cancelled", "queued", "some_future_status"])
def test_exa_webhook_broadened_non_terminal_status_acks_without_persisting(
    monkeypatch, tmp_path, status
):
    """#4184: any parseable non-terminal status acks 200 — EXA retries non-2xx forever."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    created = _create_watch(c, backend="exa")
    wid = created["watch"]["watch_id"]

    body, headers = _signed_delivery(_event(status=status, output=None), created["delivery_secret"])
    anon = TestClient(srv.app)
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"acknowledged": True}
    assert c.get(f"/v1/monitors/{wid}/runs").json()["runs"] == []


@pytest.mark.unit
def test_exa_webhook_missing_status_stays_fail_closed(monkeypatch, tmp_path):
    """#4184: the broadened predicate never widens to a malformed envelope."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    created = _create_watch(_monitor_client(), backend="exa")
    body, headers = _signed_delivery(_event(status=None, output=None), created["delivery_secret"])
    anon = TestClient(srv.app)
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_webhook_duplicate_delivery_is_idempotent(monkeypatch, tmp_path):
    """#4123: EXA retries non-2xx, so a redelivered run answers 200 + stored run."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    created = _create_watch(c, backend="exa", exa_monitor_id="exa_mon_1")
    wid = created["watch"]["watch_id"]
    secret = created["delivery_secret"]

    body, headers = _signed_delivery(_event(), secret)
    anon = TestClient(srv.app)
    post = lambda: anon.post(  # noqa: E731 - two deliveries of the same bytes
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    first = post()
    assert first.status_code == 201, first.text
    second = post()
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    runs = c.get(f"/v1/monitors/{wid}/runs").json()["runs"]
    assert [stored["run_id"] for stored in runs] == [first.json()["run_id"]]


@pytest.mark.unit
def test_exa_webhook_bad_payload_or_unknown_monitor_fails_closed(monkeypatch, tmp_path):
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    created = _create_watch(_monitor_client(), backend="exa", exa_monitor_id="exa_mon_1")
    secret = created["delivery_secret"]
    anon = TestClient(srv.app)

    unknown_body, unknown_headers = _signed_delivery(_event(monitorId="nope"), secret)
    unknown = anon.post(
        "/v1/monitors/exa_webhook",
        content=unknown_body,
        headers={**unknown_headers, "Content-Type": "application/json"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "watch_not_found"

    malformed = anon.post(
        "/v1/monitors/exa_webhook",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "exa_payload_invalid"

    # The flat pre-pin shape is no longer a valid envelope (#4123).
    flat_body, flat_headers = _signed_delivery(
        {"monitorId": "exa_mon_1", "status": "completed"}, secret
    )
    flat = anon.post(
        "/v1/monitors/exa_webhook",
        content=flat_body,
        headers={**flat_headers, "Content-Type": "application/json"},
    )
    assert flat.status_code == 422
    assert flat.json()["error"]["code"] == "exa_payload_invalid"


@pytest.mark.unit
def test_exa_webhook_non_exa_backend_watch_fails_closed(monkeypatch, tmp_path):
    """A watch linked to a remote EXA monitor must be backend="exa" (Task 8c)."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv

    c = _monitor_client()
    # backend defaults to "oss" while carrying an exa_monitor_id: misconfigured.
    created = _create_watch(c, exa_monitor_id="exa_mon_oss")
    wid = created["watch"]["watch_id"]

    body, headers = _signed_delivery(
        _event(monitorId="exa_mon_oss", output=None), created["delivery_secret"]
    )
    anon = TestClient(srv.app)
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "watch_backend_mismatch"
    assert c.get(f"/v1/monitors/{wid}/runs").json()["runs"] == []  # nothing persisted


@pytest.mark.unit
def test_exa_webhook_watch_without_a_stored_secret_fails_closed(monkeypatch, tmp_path):
    """A watch whose stored secret is empty can never verify a delivery (#4123)."""
    _patch_monitor_store(monkeypatch, tmp_path)
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    created = _create_watch(_monitor_client(), backend="exa", exa_monitor_id="exa_mon_1")
    wid = created["watch"]["watch_id"]
    MonitorStore(db_path=str(tmp_path / "m.sqlite3")).set_delivery_secret(wid, "")

    body, headers = _signed_delivery(_event(), "some-secret")
    anon = TestClient(srv.app)
    r = anon.post(
        "/v1/monitors/exa_webhook",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "exa_bad_signature"


@pytest.mark.unit
def test_orchestrator_trigger_round_trip(monkeypatch, tmp_path):
    """Hub path (T7): create → trigger → runs through POST /v1/orchestrator_invoke."""
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]

    trigger = c.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_monitors_trigger",
            "arguments": {"watch_id": wid, "mode": "poll"},
        },
    )
    assert trigger.status_code == 200, trigger.text
    assert trigger.json()["ok"] is True
    assert trigger.json()["data"]["watch_id"] == wid
    assert trigger.json()["data"]["trigger"] == "poll"

    runs = c.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_monitors_runs", "arguments": {"watch_id": wid, "limit": 5}},
    )
    assert runs.status_code == 200, runs.text
    assert runs.json()["ok"] is True
    assert [r["run_id"] for r in runs.json()["data"]["runs"]] == [trigger.json()["data"]["run_id"]]


@pytest.mark.unit
def test_orchestrator_monitor_tools_fail_hard(monkeypatch, tmp_path):
    """Missing watch / missing watch_id / bad mode are ok:false, never 5xx."""
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()

    missing = c.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_monitors_trigger", "arguments": {"watch_id": "nope"}},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["ok"] is False
    assert "watch_not_found" in missing.json()["error"]

    no_id = c.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_monitors_runs", "arguments": {}},
    )
    assert no_id.status_code == 200, no_id.text
    assert no_id.json()["ok"] is False
    assert "watch_id" in no_id.json()["error"]

    wid = _create_watch(c)["watch"]["watch_id"]
    bad_mode = c.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_monitors_trigger",
            "arguments": {"watch_id": wid, "mode": "bogus"},
        },
    )
    assert bad_mode.status_code == 200, bad_mode.text
    assert bad_mode.json()["ok"] is False
    assert "mode" in bad_mode.json()["error"]


@pytest.mark.unit
def test_orchestrator_trigger_recall_failure_returns_ok_false(monkeypatch, tmp_path):
    """A persisted failed turn surfaces as ok:false with the run error (T7 arm).

    ``MonitorRunError`` from ``run_watch`` must not escape the orchestrator
    invoke route as a 5xx: the hub gets the fail-hard shape while the failed run
    stays readable through ``GET /v1/monitors/{watch_id}/runs``.
    """
    _patch_monitor_store(monkeypatch, tmp_path)
    c = _monitor_client()
    wid = _create_watch(c)["watch"]["watch_id"]

    from digisearch.monitors import runner as runner_mod

    def _boom(**kwargs):
        raise RuntimeError("recall exploded")

    monkeypatch.setattr(runner_mod, "_invoke_shallow_recall", _boom)
    r = c.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_monitors_trigger", "arguments": {"watch_id": wid}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False
    assert "recall exploded" in r.json()["error"]

    runs = c.get(f"/v1/monitors/{wid}/runs")
    assert runs.status_code == 200, runs.text
    assert runs.json()["runs"][0]["status"] == "failed"
    assert runs.json()["runs"][0]["error"] == "recall exploded"


@pytest.mark.unit
def test_orchestrator_manifest_lists_monitor_tools():
    from digisearch.orchestrator_tools import build_orchestrator_tool_manifest

    tools = {t["function"]["name"]: t for t in build_orchestrator_tool_manifest()}
    assert "digisearch_monitors_trigger" in tools
    assert "digisearch_monitors_runs" in tools
    assert tools["digisearch_monitors_trigger"]["function"]["parameters"]["required"] == [
        "watch_id"
    ]
    assert tools["digisearch_monitors_runs"]["function"]["parameters"]["required"] == ["watch_id"]


@pytest.mark.unit
def test_rate_limit_budgets_key_monitor_routes():
    import digisearch.server as srv

    wid = "01HQZ0000000000000000000000"
    assert srv._rate_limit_for("/v1/monitors") == (30, 60)
    assert srv._rate_limit_for("/v1/monitors/tick") == (10, 60)
    assert srv._rate_limit_for("/v1/monitors/exa_webhook") == (10, 60)
    assert srv._rate_limit_for(f"/v1/monitors/{wid}/trigger") == (10, 60)
    assert srv._rate_limit_for(f"/v1/monitors/{wid}/runs") == (30, 60)
    assert srv._rate_limit_for(f"/v1/monitors/{wid}/runs/{wid}") == (30, 60)
    assert srv._rate_limit_for(f"/v1/monitors/{wid}") == (30, 60)
    assert srv._rate_limit_for("/unmapped") == (30, 60)
