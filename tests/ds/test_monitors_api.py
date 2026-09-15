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

import pytest
from digisearch.web_exa import WebSearchData
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


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
def test_exa_webhook_exempt_but_secret_gated(monkeypatch, tmp_path):
    import digisearch.server as srv
    from digisearch.monitors.store import MonitorStore

    monkeypatch.setattr(
        srv, "get_monitor_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )
    monkeypatch.setenv("EXA_MONITOR_WEBHOOK_SECRET", "shh")
    anon = TestClient(srv.app)  # no JWT: exemption lets it reach the handler
    r = anon.post("/v1/monitors/exa_webhook", json={"nope": True})
    assert r.status_code == 401
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


def _create_watch(client: TestClient, **overrides: object) -> dict:
    body: dict = {
        "name": "etf",
        "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
    }
    body.update(overrides)
    r = client.post("/v1/monitors", json=body)
    assert r.status_code == 201, r.text
    return r.json()


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
    forwarded = {"X-Forwarded-For": "203.0.113.91"}  # unique IP: testclient bypasses limits
    for _ in range(10):
        r = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"}, headers=forwarded)
        assert r.status_code == 201, r.text
    limited = c.post(f"/v1/monitors/{wid}/trigger", json={"mode": "poll"}, headers=forwarded)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"


@pytest.mark.unit
def test_exa_webhook_valid_secret_fails_closed_until_adapter(monkeypatch):
    import digisearch.server as srv

    anon = TestClient(srv.app)
    monkeypatch.delenv("EXA_MONITOR_WEBHOOK_SECRET", raising=False)
    unset = anon.post("/v1/monitors/exa_webhook", headers={"X-Exa-Signature": "shh"}, json={})
    assert unset.status_code == 401  # no server secret: fail closed

    monkeypatch.setenv("EXA_MONITOR_WEBHOOK_SECRET", "shh")
    wrong = anon.post("/v1/monitors/exa_webhook", headers={"X-Exa-Signature": "nope"}, json={})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "exa_bad_signature"
    non_ascii = anon.post(
        "/v1/monitors/exa_webhook", headers=[(b"X-Exa-Signature", b"\xe9")], json={}
    )
    assert non_ascii.status_code == 401  # never a 500 from compare_digest

    # Translation lands with the Task 8 EXA adapter; a valid signature must not
    # be treated as accepted content until then.
    matched = anon.post("/v1/monitors/exa_webhook", headers={"X-Exa-Signature": "shh"}, json={})
    assert matched.status_code == 503
    assert matched.json()["error"]["code"] == "exa_not_configured"


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
