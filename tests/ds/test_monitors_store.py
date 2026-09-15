"""Phase C monitor store (#4065, Task 2).

Pins the real SQLite persistence layer: 26-char ULID watch ids assigned on
create, watch CRUD with patch re-validation, runs retained after watch delete,
newest-first run pagination with a run-id cursor, and the ``seen_fingerprints``
dedup memory that recomputes stored raw results with Task 3's public
``result_fingerprint`` (R7 extraction) instead of ad-hoc hashing.

No mocks: every test opens real sqlite files under ``tmp_path`` (never the real
workspace dir). Offline and stdlib-only.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

import pytest
from digisearch.monitors.dedup import dedup_results, result_fingerprint
from digisearch.monitors.models import DedupRule, MonitorRun, Watch
from digisearch.monitors.store import MonitorStore, MonitorStoreError, get_store, new_ulid
from digisearch.web_search.citation import normalize_url
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _watch(**overrides: Any) -> Watch:
    payload: dict[str, Any] = {
        "name": "etf",
        "query": "etf flows",
        "schedule": {"mode": "interval", "interval_seconds": 3600},
    }
    payload.update(overrides)
    return Watch.model_validate(payload)


def _run(
    run_id: str,
    watch_id: str,
    *,
    started_at: str = "2026-09-14T00:00:00Z",
    status: str = "no_change",
    results_all: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> MonitorRun:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "watch_id": watch_id,
        "status": status,
        "trigger": "schedule",
        "started_at": started_at,
        "finished_at": "2026-09-14T00:01:00Z",
        "query_snapshot": {"query": "etf flows"},
        "results_all": results_all or [],
        "results_new": [],
        "dedup_stats": {"seen": 1, "new": 0, "changed": 0, "unchanged": 1},
    }
    payload.update(overrides)
    return MonitorRun.model_validate(payload)


def test_crud_and_run_history_pagination(tmp_path):
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
    assert w.watch_id
    assert store.get_watch(w.watch_id).query == "etf flows"
    for i in range(3):
        store.append_run(
            MonitorRun.model_validate(
                {
                    "run_id": f"r{i}",
                    "watch_id": w.watch_id,
                    "status": "no_change",
                    "trigger": "schedule",
                    "started_at": "2026-09-14T00:00:00Z",
                    "finished_at": "2026-09-14T00:01:00Z",
                    "query_snapshot": {"query": "etf flows"},
                    "results_all": [],
                    "results_new": [],
                    "dedup_stats": {"seen": 1, "new": 0, "changed": 0, "unchanged": 1},
                }
            )
        )
    page, cursor = store.list_runs(w.watch_id, limit=2)
    assert [r.run_id for r in page] == ["r2", "r1"]
    assert cursor == "r1"
    page2, cursor2 = store.list_runs(w.watch_id, limit=2, cursor=cursor)
    assert [r.run_id for r in page2] == ["r0"]
    assert cursor2 is None
    store.delete_watch(w.watch_id)


def test_watch_ids_are_26_char_ulids(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    first = store.create_watch(_watch())
    second = store.create_watch(_watch())
    spoofed = store.create_watch(_watch(watch_id="caller-supplied"))
    assert _ULID_RE.fullmatch(first.watch_id)
    assert first.watch_id != second.watch_id
    assert spoofed.watch_id != "caller-supplied"
    assert _ULID_RE.fullmatch(new_ulid())
    assert len({new_ulid() for _ in range(50)}) == 50


def test_ulid_time_prefix_is_monotonic():
    ids = [new_ulid() for _ in range(50)]
    prefixes = [value[:10] for value in ids]
    assert prefixes == sorted(prefixes)


def test_watch_round_trip_preserves_configuration(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(
        _watch(
            search_type="deep-reasoning",
            num_results=20,
            category="news",
            include_domains=["a.com"],
            exclude_domains=["b.com"],
            dedup={"match": "url", "similarity_threshold": 0.5},
            delivery={
                "mode": "webhook",
                "targets": [{"kind": "webhook", "url": "https://hooks.example.com/x"}],
            },
            backend="exa",
            exa_monitor_id="exa_mon_123",
            workspace_id="ws-a",
        )
    )
    assert store.get_watch(w.watch_id) == w
    assert store.get_watch(w.watch_id).delivery.mode == "webhook"


def test_get_watch_missing_raises_watch_not_found(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    with pytest.raises(MonitorStoreError) as ei:
        store.get_watch("missing")
    assert ei.value.code == "watch_not_found"


def test_list_watches_and_workspace_filter(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    ws_a = store.create_watch(_watch(name="a", workspace_id="ws-a"))
    ws_b = store.create_watch(_watch(name="b", workspace_id="ws-b"))
    no_ws = store.create_watch(_watch(name="c"))
    assert {w.watch_id for w in store.list_watches()} == {
        ws_a.watch_id,
        ws_b.watch_id,
        no_ws.watch_id,
    }
    assert [w.watch_id for w in store.list_watches(workspace_id="ws-a")] == [ws_a.watch_id]
    assert store.list_watches(workspace_id="nope") == []


def test_update_watch_patches_and_preserves_identity(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    original = store.create_watch(_watch())
    before = store.get_watch(original.watch_id)
    updated = store.update_watch(
        original.watch_id,
        {
            "name": "renamed",
            "num_results": 3,
            "watch_id": "attacker-supplied",
            "created_at": "2000-01-01T00:00:00Z",
        },
    )
    assert updated.watch_id == original.watch_id
    assert updated.created_at == before.created_at
    assert updated.updated_at >= before.updated_at
    assert updated.name == "renamed"
    assert updated.num_results == 3
    assert store.get_watch(original.watch_id).name == "renamed"


def test_update_watch_revalidates_the_merged_document(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    with pytest.raises(ValidationError):
        store.update_watch(w.watch_id, {"bogus": 1})
    with pytest.raises(ValidationError):
        store.update_watch(w.watch_id, {"schedule": {"mode": "interval"}})
    with pytest.raises(MonitorStoreError) as ei:
        store.update_watch("missing", {"name": "x"})
    assert ei.value.code == "watch_not_found"


def test_delete_watch_retains_runs_and_is_fail_hard_when_missing(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    store.append_run(_run("r1", w.watch_id))
    store.delete_watch(w.watch_id)
    with pytest.raises(MonitorStoreError) as ei:
        store.get_watch(w.watch_id)
    assert ei.value.code == "watch_not_found"
    runs, cursor = store.list_runs(w.watch_id)
    assert [r.run_id for r in runs] == ["r1"]
    assert cursor is None
    with pytest.raises(MonitorStoreError) as ei:
        store.delete_watch(w.watch_id)
    assert ei.value.code == "watch_not_found"


def test_run_round_trip_preserves_envelope(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    results = [{"url": "https://a.com/1", "title": "A", "text": "alpha"}]
    run = _run(
        "r1",
        w.watch_id,
        status="ok",
        results_all=results,
        results_new=results,
        cost_dollars={"total": 0.0, "provider": "searxng"},
        delivery=[{"target_kind": "webhook", "ok": True, "status_code": 200}],
    )
    assert store.append_run(run) == run
    got = store.get_run(w.watch_id, "r1")
    assert got == run
    assert got.started_at == run.started_at
    assert got.results_all == results
    assert got.delivery[0].status_code == 200


def test_get_run_missing_raises_run_not_found(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    with pytest.raises(MonitorStoreError) as ei:
        store.get_run(w.watch_id, "missing")
    assert ei.value.code == "run_not_found"


def test_append_run_duplicate_run_id_raises_run_exists(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    store.append_run(_run("r1", w.watch_id))
    with pytest.raises(MonitorStoreError) as ei:
        store.append_run(_run("r1", w.watch_id))
    assert ei.value.code == "run_exists"


def test_list_runs_clamps_limit_and_rejects_unknown_cursor(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    for i in range(3):
        store.append_run(_run(f"r{i}", w.watch_id))
    page, cursor = store.list_runs(w.watch_id, limit=0)
    assert [r.run_id for r in page] == ["r2"]
    assert cursor == "r2"
    page, cursor = store.list_runs(w.watch_id, limit=10_000)
    assert [r.run_id for r in page] == ["r2", "r1", "r0"]
    assert cursor is None
    with pytest.raises(MonitorStoreError) as ei:
        store.list_runs(w.watch_id, limit=2, cursor="missing")
    assert ei.value.code == "run_not_found"


def test_seen_fingerprints_merges_newest_run_first(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    old_a = {"url": "https://a.com/1", "title": "A", "text": "old body"}
    keep_b = {"url": "https://b.com/2", "title": "B", "text": "keep body"}
    new_a = {"url": "https://a.com/1", "title": "A", "text": "new body"}
    store.append_run(_run("r1", w.watch_id, results_all=[old_a, keep_b]))
    store.append_run(_run("r2", w.watch_id, started_at="2026-09-14T01:00:00Z", results_all=[new_a]))
    seen = store.seen_fingerprints(w.watch_id)
    assert seen == {
        normalize_url("https://a.com/1"): result_fingerprint(new_a),
        normalize_url("https://b.com/2"): result_fingerprint(keep_b),
    }
    assert store.seen_fingerprints(w.watch_id, limit_runs=1) == {
        normalize_url("https://a.com/1"): result_fingerprint(new_a),
    }


def test_seen_fingerprints_empty_cases(tmp_path):
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    assert store.seen_fingerprints(w.watch_id) == {}
    assert store.seen_fingerprints(w.watch_id, limit_runs=0) == {}
    assert store.seen_fingerprints("missing") == {}


def test_seen_fingerprints_feed_dedup_without_false_changes(tmp_path):
    """R7 contract: memory recomputed by the store compares equal inside dedup."""
    store = MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    w = store.create_watch(_watch())
    results = [
        {"url": "https://a.com/1", "title": "Highlights only", "highlights": ["alpha beta"]},
        {"url": "https://b.com/2", "title": "Snippet only", "snippet": "gamma delta"},
    ]
    store.append_run(_run("r1", w.watch_id, status="ok", results_all=results, results_new=results))
    seen = store.seen_fingerprints(w.watch_id)
    assert seen[normalize_url("https://a.com/1")] == result_fingerprint(results[0])
    survivors, stats = dedup_results(results, seen, DedupRule())
    assert survivors == []
    assert stats == {"seen": 2, "new": 0, "changed": 0, "unchanged": 2}


def test_store_opens_in_wal_mode(tmp_path):
    path = tmp_path / "m.sqlite3"
    MonitorStore(db_path=str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_get_store_prefers_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DIGISEARCH_MONITORS_DB", str(tmp_path / "env.sqlite3"))
    store = get_store(db_path=str(tmp_path / "explicit.sqlite3"))
    store.create_watch(_watch())
    assert (tmp_path / "explicit.sqlite3").exists()
    assert not (tmp_path / "env.sqlite3").exists()


def test_get_store_reads_env_db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DIGISEARCH_MONITORS_DB", str(tmp_path / "env.sqlite3"))
    monkeypatch.delenv("DIGI_WORKSPACE", raising=False)
    get_store().create_watch(_watch())
    assert (tmp_path / "env.sqlite3").exists()


def test_get_store_defaults_to_workspace_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGISEARCH_MONITORS_DB", raising=False)
    monkeypatch.setenv("DIGI_WORKSPACE", str(tmp_path))
    get_store().create_watch(_watch())
    assert (tmp_path / ".digisearch" / "monitors.sqlite3").exists()


def test_get_store_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGISEARCH_MONITORS_DB", raising=False)
    monkeypatch.delenv("DIGI_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    get_store().create_watch(_watch())
    assert (tmp_path / ".digisearch" / "monitors.sqlite3").exists()


def test_get_monitor_store_seam_reads_env(tmp_path, monkeypatch):
    import digisearch.server as srv

    monkeypatch.setenv("DIGISEARCH_MONITORS_DB", str(tmp_path / "seam.sqlite3"))
    store = srv.get_monitor_store()
    assert isinstance(store, MonitorStore)
    store.create_watch(_watch())
    assert (tmp_path / "seam.sqlite3").exists()
