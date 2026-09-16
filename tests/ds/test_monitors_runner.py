"""Phase C watch runner (#4065, Task 4).

Pins the §4.4 flow: direct in-process shallow recall (EXA when configured, else
the OSS seam with ``recency_days=None`` per R5 and the ``min(num_results, 10)``
clamp per R6, adapted via ``_oss_response_to_data`` per R3), dedup against the
store's seen memory, append-only persistence, delivery only on ``ok`` +
non-poll runs (R13) threading the watch's stored secret, a loud failure when a
delivery-enabled watch has no stored secret, cron/interval due evaluation with
the cron grammar imported from ``digiclaw.cron`` (never copied), and per-watch
tick isolation. Offline only — the recall boundary is always mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from digisearch.monitors.models import DeliveryReceipt, MonitorRun, Watch
from digisearch.monitors.store import MonitorStore, new_ulid
from digisearch.web_exa import WebSearchData
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _exa_unconfigured(monkeypatch):
    """Default every test to the OSS leg; EXA tests opt in by setting the key."""
    monkeypatch.delenv("EXA_API_KEY", raising=False)


def _recall_data() -> WebSearchData:
    # The seam boundary is WebSearchData (R3). The OSS leg produces
    # WebSearchResponse; _oss_response_to_data adapts it. This test pins the
    # ADAPTED boundary only — it never claims the OSS leg returns
    # WebSearchData directly (see test_oss_response_adapts_to_web_search_data).
    return WebSearchData.model_validate(
        {
            "results": [
                {"url": "https://a.com/1", "title": "A", "text": "alpha"},
                {"url": "https://b.com/2", "title": "B", "text": "beta"},
            ]
        }
    )


def _make_watch(store: MonitorStore, **overrides) -> Watch:
    body: dict = {
        "name": "etf",
        "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
    }
    body.update(overrides)
    return store.create_watch(Watch.model_validate(body))


def _webhook_delivery() -> dict:
    return {
        "mode": "webhook",
        "targets": [{"kind": "webhook", "url": "https://hook.example/x"}],
    }


def _stub_pipeline(monkeypatch, data: WebSearchData | None = None) -> list[tuple[str, str]]:
    """Patch the recall boundary and the delivery seam; return delivery calls."""
    from digisearch.monitors import runner as mod

    monkeypatch.setattr(
        mod, "_invoke_shallow_recall", lambda **k: data if data is not None else _recall_data()
    )
    delivered: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mod,
        "deliver",
        lambda run, watch, **k: delivered.append((run.status, k.get("delivery_secret"))) or [],
    )
    return delivered


@pytest.mark.unit
def test_oss_response_adapts_to_web_search_data():
    """R3: the OSS leg returns WebSearchResponse; the seam adapts it."""
    from digisearch.monitors import runner as mod
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult

    resp = WebSearchResponse(
        query="q",
        results=[WebSearchResult(url="https://a.com/1", title="A", snippet="alpha")],
        provider="searxng",
    )
    data = mod._oss_response_to_data(resp)
    assert isinstance(data, WebSearchData)
    assert data.results == [r.model_dump() for r in resp.results]


@pytest.mark.unit
def test_run_watch_persists_new_only(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        Watch.model_validate(
            {
                "name": "etf",
                "query": "etf flows",
                "schedule": {"mode": "interval", "interval_seconds": 3600},
            }
        )
    )
    monkeypatch.setattr(mod, "_invoke_shallow_recall", lambda **k: _recall_data())
    monkeypatch.setattr(mod, "deliver", lambda run, watch, **k: [])
    first = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert first.status == "ok" and len(first.results_new) == 2
    second = mod.run_watch(w.watch_id, trigger="schedule", store=store)
    assert second.status == "no_change" and second.results_new == []


@pytest.mark.unit
def test_run_watch_fail_hard_persists_failed(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        Watch.model_validate(
            {
                "name": "etf",
                "query": "etf flows",
                "schedule": {"mode": "interval", "interval_seconds": 3600},
            }
        )
    )

    def boom(**k):
        raise RuntimeError("turn down")

    monkeypatch.setattr(mod, "_invoke_shallow_recall", boom)
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="manual", store=store)
    runs, _ = store.list_runs(w.watch_id)
    assert runs[0].status == "failed" and runs[0].error == "turn down"


@pytest.mark.unit
def test_oss_seam_pins_recency_and_clamp(monkeypatch):
    """R5/R6: recency_days=None, max_results=min(num_results, 10), domains passed."""
    from digisearch.monitors import runner as mod

    captured: dict = {}

    def fake_search(req):
        captured["req"] = req
        return WebSearchResponse(
            query=req.query,
            results=[WebSearchResult(url="https://a.com/1", title="A", snippet="alpha")],
            provider="searxng",
        )

    monkeypatch.setattr(mod, "search_web", fake_search)
    data = mod._invoke_shallow_recall(
        query="etf flows",
        search_type="auto",
        num_results=25,
        category="news",
        include_domains=["a.com"],
        exclude_domains=["b.com"],
    )
    req = captured["req"]
    assert req.query == "etf flows"
    assert req.recency_days is None
    assert req.max_results == 10
    assert req.include_domains == ["a.com"]
    assert req.exclude_domains == ["b.com"]
    assert set(req.model_dump()) == {
        "query",
        "include_domains",
        "exclude_domains",
        "max_results",
        "recency_days",
    }
    assert data.results == [
        WebSearchResult(url="https://a.com/1", title="A", snippet="alpha").model_dump()
    ]


@pytest.mark.unit
def test_exa_seam_passthrough_when_configured(monkeypatch):
    from digisearch.monitors import runner as mod

    captured: dict = {}

    def fake_exa(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return WebSearchData(results=[])

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr(mod, "exa_search", fake_exa)
    data = mod._invoke_shallow_recall(
        query="etf flows",
        search_type="deep",
        num_results=25,
        category="news",
        include_domains=["a.com"],
        exclude_domains=None,
    )
    assert captured == {
        "query": "etf flows",
        "search_type": "deep",
        "num_results": 25,
        "offset": 0,
        "category": "news",
        "include_domains": ["a.com"],
        "exclude_domains": None,
    }
    assert data.results == []


@pytest.mark.unit
def test_exa_seam_forwards_offset(monkeypatch):
    """#4241: the runner seam threads the #4234 offset (EXA-only) through."""
    from digisearch.monitors import runner as mod

    captured: dict = {}

    def fake_exa(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return WebSearchData(results=[])

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr(mod, "exa_search", fake_exa)
    mod._invoke_shallow_recall(
        query="etf flows",
        search_type="auto",
        num_results=8,
        category=None,
        include_domains=None,
        exclude_domains=None,
        offset=8,
    )
    assert captured["offset"] == 8


@pytest.mark.unit
def test_oss_seam_rejects_nonzero_offset(monkeypatch):
    """The OSS seam has no offset — fail loudly, never silently serve page 1."""
    from digisearch.monitors import runner as mod

    calls: list = []

    def fake_search(req):
        calls.append(req)
        return WebSearchResponse(query=req.query, results=[], provider="searxng")

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setattr(mod, "search_web", fake_search)
    with pytest.raises(ValueError, match="offset"):
        mod._invoke_shallow_recall(
            query="etf flows",
            search_type="auto",
            num_results=8,
            category=None,
            include_domains=None,
            exclude_domains=None,
            offset=8,
        )
    assert calls == []


@pytest.mark.unit
def test_run_watch_snapshot_records_oss_clamp(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(
        store,
        num_results=25,
        category="news",
        include_domains=["a.com"],
        exclude_domains=["b.com"],
    )
    _stub_pipeline(monkeypatch)
    run = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert run.query_snapshot == {
        "query": "etf flows",
        "search_type": "auto",
        "category": "news",
        "recency_days": None,
        "include_domains": ["a.com"],
        "exclude_domains": ["b.com"],
        "num_results": 10,
        "num_results_clamped_from": 25,
    }


@pytest.mark.unit
def test_oss_max_results_constant_ties_to_request_bound():
    """The R6 constant must track WebSearchRequest's ``le`` bound (drift fails here)."""
    from digisearch.monitors import runner as mod

    bounds = [
        constraint.le
        for constraint in WebSearchRequest.model_fields["max_results"].metadata
        if hasattr(constraint, "le")
    ]
    assert bounds == [mod._OSS_MAX_RESULTS]


@pytest.mark.unit
def test_run_watch_snapshot_at_oss_bound_records_no_clamp(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, num_results=10)
    _stub_pipeline(monkeypatch)
    run = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert run.query_snapshot["num_results"] == 10
    assert "num_results_clamped_from" not in run.query_snapshot


@pytest.mark.unit
def test_run_watch_snapshot_exa_keeps_num_results(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, num_results=25)
    _stub_pipeline(monkeypatch)
    run = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert run.query_snapshot["num_results"] == 25
    assert "num_results_clamped_from" not in run.query_snapshot


@pytest.mark.unit
def test_run_watch_poll_mode_never_delivers(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store)
    delivered = _stub_pipeline(monkeypatch)
    run = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert run.status == "ok"
    assert delivered == []


@pytest.mark.unit
def test_run_watch_delivers_only_on_ok_non_poll(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, delivery=_webhook_delivery())
    store.set_delivery_secret(w.watch_id, "s3cr3t")
    delivered = _stub_pipeline(monkeypatch)
    first = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert first.status == "ok"
    second = mod.run_watch(w.watch_id, trigger="schedule", store=store)
    assert second.status == "no_change"
    assert delivered == [("ok", "s3cr3t")]


@pytest.mark.unit
def test_delivery_receipts_returned_but_not_persisted(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, delivery=_webhook_delivery())
    store.set_delivery_secret(w.watch_id, "s3cr3t")
    monkeypatch.setattr(mod, "_invoke_shallow_recall", lambda **k: _recall_data())
    receipt = DeliveryReceipt(target_kind="webhook", ok=True, status_code=200)
    monkeypatch.setattr(mod, "deliver", lambda run, watch, **k: [receipt])
    run = mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert run.delivery == [receipt]
    stored, _ = store.list_runs(w.watch_id)
    assert stored[0].delivery == []


@pytest.mark.unit
def test_run_watch_missing_delivery_secret_fails_loud(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, delivery=_webhook_delivery())
    delivered = _stub_pipeline(monkeypatch)
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="manual", store=store)
    runs, _ = store.list_runs(w.watch_id)
    assert runs[0].status == "failed"
    assert runs[0].error == "delivery_secret_missing"
    assert delivered == []


@pytest.mark.unit
def test_missing_secret_failure_does_not_advance_dedup_memory(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, delivery=_webhook_delivery())
    delivered = _stub_pipeline(monkeypatch)
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="manual", store=store)
    runs, _ = store.list_runs(w.watch_id)
    assert runs[0].status == "failed"
    assert runs[0].results_all == []
    assert len(runs[0].results_new) == 2
    # Until the operator provisions a secret, the same content is re-detected
    # as new and the run fails loudly again (no silent no_change absorption).
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="schedule", store=store)
    runs, _ = store.list_runs(w.watch_id)
    assert runs[0].status == "failed"
    assert runs[0].error == "delivery_secret_missing"
    assert delivered == []
    # With a secret the re-detected content is new again and delivers.
    store.set_delivery_secret(w.watch_id, "s3cr3t")
    run = mod.run_watch(w.watch_id, trigger="schedule", store=store)
    assert run.status == "ok"
    assert delivered == [("ok", "s3cr3t")]


@pytest.mark.unit
def test_run_watch_failed_recall_skips_delivery(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store, delivery=_webhook_delivery())
    store.set_delivery_secret(w.watch_id, "s3cr3t")

    def boom(**k):
        raise RuntimeError("boom")

    delivered: list = []
    monkeypatch.setattr(mod, "_invoke_shallow_recall", boom)
    monkeypatch.setattr(mod, "deliver", lambda *a, **k: delivered.append(a) or [])
    with pytest.raises(mod.MonitorRunError):
        mod.run_watch(w.watch_id, trigger="manual", store=store)
    assert delivered == []


@pytest.mark.unit
def test_is_due_interval_mode():
    from digisearch.monitors.runner import is_due

    watch = Watch.model_validate(
        {"name": "etf", "query": "q", "schedule": {"mode": "interval", "interval_seconds": 3600}}
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert is_due(watch, now, None) is True
    assert is_due(watch, now, now - timedelta(seconds=3599)) is False
    assert is_due(watch, now, now - timedelta(seconds=3600)) is True
    assert is_due(watch, now, now - timedelta(seconds=7200)) is True


@pytest.mark.unit
def test_is_due_treats_naive_now_as_utc():
    from digisearch.monitors.runner import is_due

    watch = Watch.model_validate(
        {"name": "etf", "query": "q", "schedule": {"mode": "interval", "interval_seconds": 3600}}
    )
    naive_now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    assert is_due(watch, naive_now, None) is True


@pytest.mark.unit
def test_is_due_cron_uses_watch_timezone():
    from digisearch.monitors.runner import is_due

    watch = Watch.model_validate(
        {
            "name": "etf",
            "query": "q",
            "schedule": {"mode": "cron", "cron": "30 9 * * *", "timezone": "America/New_York"},
        }
    )
    # 2026-09-15 is EDT (UTC-4): 13:30 UTC is 09:30 New York.
    assert is_due(watch, datetime(2026, 9, 15, 13, 30, tzinfo=UTC), None) is True
    assert is_due(watch, datetime(2026, 9, 15, 13, 30, 45, tzinfo=UTC), None) is True
    assert is_due(watch, datetime(2026, 9, 15, 9, 30, tzinfo=UTC), None) is False
    assert is_due(watch, datetime(2026, 9, 16, 13, 31, tzinfo=UTC), None) is False


@pytest.mark.unit
def test_is_due_cron_suppresses_same_minute_rerun():
    from digisearch.monitors.runner import is_due

    watch = Watch.model_validate(
        {
            "name": "etf",
            "query": "q",
            "schedule": {"mode": "cron", "cron": "30 9 * * *", "timezone": "UTC"},
        }
    )
    now = datetime(2026, 9, 15, 9, 30, 50, tzinfo=UTC)
    assert is_due(watch, now, datetime(2026, 9, 15, 9, 30, 5, tzinfo=UTC)) is False
    assert is_due(watch, now, datetime(2026, 9, 14, 9, 30, 0, tzinfo=UTC)) is True


@pytest.mark.unit
def test_tick_runs_due_enabled_watches_once(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    due = _make_watch(store)
    _make_watch(
        store,
        name="disabled",
        schedule={"mode": "interval", "interval_seconds": 3600, "enabled": False},
    )
    _stub_pipeline(monkeypatch)
    runs = mod.tick_due_watches(store=store)
    assert [r.watch_id for r in runs] == [due.watch_id]
    assert runs[0].status == "ok" and runs[0].trigger == "schedule"
    assert mod.tick_due_watches(store=store) == []


@pytest.mark.unit
def test_tick_now_controls_interval_cadence(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = _make_watch(store)
    store.append_run(
        MonitorRun(
            run_id=new_ulid(),
            watch_id=w.watch_id,
            status="no_change",
            trigger="schedule",
            started_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, 11, 0, 5, tzinfo=UTC),
            query_snapshot={"query": w.query},
            results_all=[],
            results_new=[],
            dedup_stats={"seen": 0, "new": 0, "changed": 0, "unchanged": 0},
        )
    )
    _stub_pipeline(monkeypatch)
    assert mod.tick_due_watches(now=datetime(2026, 1, 1, 11, 30, tzinfo=UTC), store=store) == []
    runs = mod.tick_due_watches(now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC), store=store)
    assert [r.status for r in runs] == ["ok"]


@pytest.mark.unit
def test_tick_isolates_watch_failures(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    bad = _make_watch(store, name="bad", query="boom")
    good = _make_watch(store, name="good", query="ok")

    def recall(**k):
        if k["query"] == "boom":
            raise RuntimeError("kaboom")
        return _recall_data()

    monkeypatch.setattr(mod, "_invoke_shallow_recall", recall)
    monkeypatch.setattr(mod, "deliver", lambda run, watch, **k: [])
    runs = mod.tick_due_watches(store=store)
    by_watch = {r.watch_id: r for r in runs}
    assert len(runs) == 2
    assert by_watch[bad.watch_id].status == "failed"
    assert by_watch[bad.watch_id].error == "kaboom"
    assert by_watch[good.watch_id].status == "ok"


@pytest.mark.unit
def test_tick_skips_datatap_watches(monkeypatch, tmp_path):
    from digisearch.monitors import runner as mod

    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    _make_watch(store, workspace_id="datatap")
    delivered = _stub_pipeline(monkeypatch)
    assert mod.tick_due_watches(store=store) == []
    assert delivered == []
