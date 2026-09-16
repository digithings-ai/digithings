"""Phase D webset store (#4066, Task 2).

Pins the real SQLite persistence layer: server-owned ids and timestamps across
all seven tables, newest-first item pagination with an item-id cursor,
oldest-first event tailing with an explicit ``after`` cursor (and malformed
cursor rejection at the store boundary), the ``(webset_id, dedup_key)``
insert-or-ignore event idempotency scheme that dedups within one generation but
re-emits terminal events under a new generation, one-way webset/search status
transitions with sticky ``idle`` and ``cancelled`` search settlement, the idle
guard that refuses while items or enrichment fields are unsettled, the
``webhook_deliveries`` ledger keyed ``(webhook_id, event_id)`` with a non-empty
server-assigned webhook id, and the ``get_store`` resolution order (explicit ->
``DIGISEARCH_WEBSETS_DB`` -> ``{DIGI_WORKSPACE}`` -> cwd).

No mocks: every test opens real sqlite files under ``tmp_path`` (never the real
workspace dir). Offline and stdlib-only.
"""

from __future__ import annotations

import inspect
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets import store as store_module
from digisearch.websets.models import (
    EnrichedField,
    EnrichmentDef,
    WebhookConfig,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetMonitor,
    WebsetSearch,
)
from digisearch.websets.store import WebsetStore, WebsetStoreError, get_store

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
_WS_ID_RE = re.compile(r"ws_[0-9a-f]{32}$")
_WSS_ID_RE = re.compile(r"wss_[0-9a-f]{32}$")
_WSI_ID_RE = re.compile(r"wsi_[0-9a-f]{32}$")
_WSE_ID_RE = re.compile(r"wse_[0-9a-f]{32}$")
_WSM_ID_RE = re.compile(r"wsm_[0-9a-f]{32}$")
_WEBHOOK_ID_RE = re.compile(r"[0-9a-f]{32}$")
_GHOST = "ws_" + "f" * 32
_GHOST_SEARCH = "wss_" + "f" * 32
_GHOST_ITEM = "wsi_" + "f" * 32
_GHOST_ENRICHMENT = "wse_" + "f" * 32
_GHOST_MONITOR = "wsm_" + "f" * 32


def _criteria() -> list[dict[str, str]]:
    return [{"name": "photonics", "rule": "company is a photonics startup"}]


def _webset(**overrides: Any) -> Webset:
    payload: dict[str, Any] = {"criteria": _criteria()}
    payload.update(overrides)
    return Webset.model_validate(payload)


def _search(webset_id: str, **overrides: Any) -> WebsetSearch:
    payload: dict[str, Any] = {
        "webset_id": webset_id,
        "query": "photonics startups",
        "criteria": _criteria(),
    }
    payload.update(overrides)
    return WebsetSearch.model_validate(payload)


def _item(
    webset_id: str, *, created_at: datetime, url: str = "https://example.com/a", **overrides: Any
) -> WebsetItem:
    payload: dict[str, Any] = {"webset_id": webset_id, "url": url, "created_at": created_at}
    payload.update(overrides)
    return WebsetItem.model_validate(payload)


def _resolved_field(value: str = "strong") -> EnrichedField:
    return EnrichedField(
        value=value, citations=[Citation(url="https://example.com/a", excerpt="ex")]
    )


def test_store_round_trips_webset_search_items_and_export_read(tmp_path):
    """The Task 2 acceptance flow: create -> search -> items -> events -> read-back."""
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    created = store.create_webset(
        _webset(
            workspace_id="ws-a",
            enrichments=[{"name": "fit", "type": "options", "options": ["strong", "weak"]}],
        )
    )
    assert _WS_ID_RE.fullmatch(created.id)
    assert created.object == "webset"
    assert created.status == "running"
    assert created.created_at is not None and created.updated_at is not None
    assert created.updated_at >= created.created_at
    assert [e.name for e in created.enrichments] == ["fit"]
    assert _WSE_ID_RE.fullmatch(created.enrichments[0].id)

    search = store.add_search(_search(created.id))
    assert _WSS_ID_RE.fullmatch(search.id)
    assert search.status == "running"
    assert store.get_webset(created.id).searches == [search]

    verified = store.save_item(
        _item(
            created.id,
            created_at=_T0 + timedelta(seconds=1),
            verification="verified",
            enrichments={"fit": _resolved_field()},
        )
    )
    rejected = store.save_item(
        _item(
            created.id,
            created_at=_T0 + timedelta(seconds=2),
            url="https://example.com/b",
            verification="rejected",
        )
    )
    pending = store.save_item(
        _item(created.id, created_at=_T0 + timedelta(seconds=3), url="https://example.com/c")
    )

    everything, cursor = store.list_items(created.id)
    assert [i.id for i in everything] == [pending.id, rejected.id, verified.id]
    assert cursor is None
    assert [i.id for i in store.list_items(created.id, verification="verified")[0]] == [verified.id]
    assert [i.id for i in store.list_items(created.id, verification="rejected")[0]] == [rejected.id]
    assert [i.id for i in store.list_items(created.id, verification="pending")[0]] == [pending.id]
    assert store.count_items(created.id) == {"verified": 1, "rejected": 1, "pending": 1}
    assert store.count_items(_GHOST) == {"verified": 0, "rejected": 0, "pending": 0}

    exported = json.loads(
        json.dumps(
            [
                i.model_dump(mode="json")
                for i in store.list_items(created.id, verification="verified")[0]
            ]
        )
    )
    assert exported[0]["enrichments"]["fit"]["citations"][0]["url"] == "https://example.com/a"
    assert WebsetItem.model_validate(exported[0]) == verified

    created_event = store.append_event(
        WebsetEvent(
            webset_id=created.id,
            type="item.created",
            search_id=search.id,
            item_id=verified.id,
            payload={"url": verified.url},
        )
    )
    idle_event = store.append_event(
        WebsetEvent(webset_id=created.id, type="webset.idle", search_id=search.id)
    )
    events, next_cursor = store.list_events(created.id)
    assert [e.id for e in events] == [created_event.id, idle_event.id]
    assert next_cursor is None

    duplicate = store.append_event(
        WebsetEvent(webset_id=created.id, type="webset.idle", search_id=search.id)
    )
    assert duplicate.id == idle_event.id
    assert len(store.list_events(created.id)[0]) == 2

    assert store.get_item(created.id, verified.id) == verified
    assert store.get_search(created.id, search.id) == search
    with pytest.raises(WebsetStoreError) as ei:
        store.get_item(created.id, _GHOST_ITEM)
    assert ei.value.code == "item_not_found"


def test_items_newest_first_cursor_clamping_and_unknown_cursor(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    items = [
        store.save_item(
            _item(webset.id, created_at=_T0 + timedelta(seconds=i), url=f"https://example.com/{i}")
        )
        for i in range(4)
    ]
    assert all(_WSI_ID_RE.fullmatch(i.id) for i in items)

    page, cursor = store.list_items(webset.id, limit=2)
    assert [i.id for i in page] == [items[3].id, items[2].id]
    assert cursor == items[2].id
    page2, cursor2 = store.list_items(webset.id, limit=2, cursor=cursor)
    assert [i.id for i in page2] == [items[1].id, items[0].id]
    assert cursor2 is None

    page, cursor = store.list_items(webset.id, limit=0)
    assert [i.id for i in page] == [items[3].id]
    assert cursor == items[3].id
    page, cursor = store.list_items(webset.id, limit=10_000)
    assert len(page) == 4
    assert cursor is None

    with pytest.raises(WebsetStoreError) as ei:
        store.list_items(webset.id, cursor=_GHOST_ITEM)
    assert ei.value.code == "cursor_not_found"
    other = store.create_webset(_webset())
    foreign = store.save_item(_item(other.id, created_at=_T0))
    with pytest.raises(WebsetStoreError) as ei:
        store.list_items(webset.id, cursor=foreign.id)
    assert ei.value.code == "cursor_not_found"


def test_item_upsert_preserves_created_at_and_scopes_to_webset(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    item = store.save_item(_item(webset.id, created_at=_T0))
    updated = store.save_item(item.model_copy(update={"verification": "rejected"}))
    assert updated.created_at == item.created_at
    assert store.get_item(webset.id, item.id).verification == "rejected"
    with pytest.raises(WebsetStoreError) as ei:
        store.get_item(_GHOST, item.id)
    assert ei.value.code == "item_not_found"


def test_events_oldest_first_cursor_tailing_and_rejections(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    search = store.add_search(_search(webset.id))
    events = [
        store.append_event(
            WebsetEvent(
                webset_id=webset.id,
                type="item.created",
                search_id=search.id,
                item_id=f"wsi_{i:032x}",
            )
        )
        for i in range(4)
    ]

    page, cursor = store.list_events(webset.id, limit=2)
    assert [e.id for e in page] == [events[0].id, events[1].id]
    assert cursor == events[1].id
    page2, cursor2 = store.list_events(webset.id, after=cursor, limit=2)
    assert [e.id for e in page2] == [events[2].id, events[3].id]
    assert cursor2 is None

    page3, cursor3 = store.list_events(webset.id, limit=1)
    assert [e.id for e in page3] == [events[0].id]
    assert cursor3 == events[0].id
    page4, cursor4 = store.list_events(webset.id, after=cursor3, limit=1)
    assert [e.id for e in page4] == [events[1].id]
    assert cursor4 == events[1].id
    tail, tail_cursor = store.list_events(webset.id, after=events[3].id)
    assert tail == [] and tail_cursor is None

    # Unknown-but-well-formed cursor: looked up, not found.
    with pytest.raises(WebsetStoreError) as ei:
        store.list_events(webset.id, after="0123456789abcdef0123456789abcdef")
    assert ei.value.code == "cursor_not_found"
    # Malformed cursors are rejected at the store boundary, never silently accepted.
    for bad in ("evt-1", "not a cursor", "0" * 31, "f" * 33, "wsi_" + "a" * 32):
        with pytest.raises(WebsetStoreError) as ei:
            store.list_events(webset.id, after=bad)
        assert ei.value.code == "cursor_not_found"
    # A cursor minted by another webset is unknown here too.
    other = store.create_webset(_webset())
    other_search = store.add_search(_search(other.id))
    foreign = store.append_event(
        WebsetEvent(webset_id=other.id, type="webset.idle", search_id=other_search.id)
    )
    with pytest.raises(WebsetStoreError) as ei:
        store.list_events(webset.id, after=foreign.id)
    assert ei.value.code == "cursor_not_found"


def test_event_dedup_is_insert_or_ignore_within_a_generation_and_reemits_across_generations(
    tmp_path,
):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    first = store.add_search(_search(webset.id))
    second = store.add_search(_search(webset.id, query="photonics round two"))
    item_id = "wsi_" + "a" * 32

    enriched = store.append_event(
        WebsetEvent(webset_id=webset.id, type="item.enriched", search_id=first.id, item_id=item_id)
    )
    duplicate = store.append_event(
        WebsetEvent(webset_id=webset.id, type="item.enriched", search_id=first.id, item_id=item_id)
    )
    assert duplicate.id == enriched.id
    assert len(store.list_events(webset.id)[0]) == 1

    # Same generation, different kind or item -> distinct rows.
    store.append_event(
        WebsetEvent(webset_id=webset.id, type="item.created", search_id=first.id, item_id=item_id)
    )
    store.append_event(
        WebsetEvent(
            webset_id=webset.id, type="item.created", search_id=first.id, item_id="wsi_" + "b" * 32
        )
    )
    # New generation (a new search row) legitimately re-emits the same terminal event.
    store.append_event(
        WebsetEvent(webset_id=webset.id, type="item.enriched", search_id=second.id, item_id=item_id)
    )

    store.append_event(WebsetEvent(webset_id=webset.id, type="webset.idle", search_id=first.id))
    store.append_event(WebsetEvent(webset_id=webset.id, type="webset.idle", search_id=first.id))
    store.append_event(WebsetEvent(webset_id=webset.id, type="webset.idle", search_id=second.id))

    events, _ = store.list_events(webset.id)
    keys = [(e.type, e.search_id, e.item_id) for e in events]
    assert keys == [
        ("item.enriched", first.id, item_id),
        ("item.created", first.id, item_id),
        ("item.created", first.id, "wsi_" + "b" * 32),
        ("item.enriched", second.id, item_id),
        ("webset.idle", first.id, ""),
        ("webset.idle", second.id, ""),
    ]
    assert sum(1 for e in events if e.type == "webset.idle") == 2


def test_append_event_rejects_unknown_kinds(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    search = store.add_search(_search(webset.id))
    rogue = WebsetEvent.model_construct(
        id="a" * 32, webset_id=webset.id, type="bogus.kind", search_id=search.id
    )
    with pytest.raises(WebsetStoreError) as ei:
        store.append_event(rogue)
    assert ei.value.code == "invalid_event_kind"
    assert store.list_events(webset.id)[0] == []


def test_events_have_no_mutation_path():
    source = inspect.getsource(store_module)
    assert "UPDATE events" not in source
    assert "DELETE FROM events" not in source
    assert "INSERT OR REPLACE INTO events" not in source
    assert not hasattr(WebsetStore, "update_event")
    assert not hasattr(WebsetStore, "delete_event")


def test_webset_transitions_are_one_way_and_idle_is_sticky(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))

    first = store.create_webset(_webset())
    assert first.status == "running"
    assert store.set_webset_idle(first.id).status == "idle"
    assert store.set_webset_idle(first.id).status == "idle"
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_status(first.id, "failed")
    assert ei.value.code == "transition_invalid"
    assert store.cancel_webset(first.id).status == "idle"

    second = store.create_webset(_webset())
    assert store.cancel_webset(second.id).status == "cancelled"
    assert store.cancel_webset(second.id).status == "cancelled"
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_status(second.id, "idle")
    assert ei.value.code == "transition_invalid"

    third = store.create_webset(_webset())
    assert store.set_webset_status(third.id, "failed").status == "failed"
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_idle(third.id)
    assert ei.value.code == "transition_invalid"
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_status(third.id, "running")
    assert ei.value.code == "transition_invalid"

    with pytest.raises(WebsetStoreError) as ei:
        store.get_webset(_GHOST)
    assert ei.value.code == "webset_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.cancel_webset(_GHOST)
    assert ei.value.code == "webset_not_found"


def test_settle_search_transitions_are_one_way(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    search = store.add_search(_search(webset.id))
    assert store.settle_search(webset.id, search.id, "idle").status == "idle"
    assert store.settle_search(webset.id, search.id, "idle").status == "idle"
    with pytest.raises(WebsetStoreError) as ei:
        store.settle_search(webset.id, search.id, "failed")
    assert ei.value.code == "transition_invalid"
    with pytest.raises(WebsetStoreError) as ei:
        store.settle_search(webset.id, search.id, "running")
    assert ei.value.code == "transition_invalid"
    with pytest.raises(WebsetStoreError) as ei:
        store.settle_search(webset.id, _GHOST_SEARCH, "idle")
    assert ei.value.code == "search_not_found"
    assert store.get_search(webset.id, search.id).status == "idle"
    assert store.list_searches(webset.id) == [search.model_copy(update={"status": "idle"})]


def test_cancel_webset_settles_only_non_terminal_searches(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    settled = store.add_search(_search(webset.id))
    failed = store.add_search(_search(webset.id, query="fails"))
    running = store.add_search(_search(webset.id, query="still running"))
    store.settle_search(webset.id, settled.id, "idle")
    store.settle_search(webset.id, failed.id, "failed")

    cancelled = store.cancel_webset(webset.id)
    assert cancelled.status == "cancelled"
    assert [s.status for s in store.list_searches(webset.id)] == ["idle", "failed", "cancelled"]
    assert store.get_search(webset.id, running.id).status == "cancelled"


def test_set_webset_idle_refuses_while_work_is_unsettled(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))

    webset = store.create_webset(_webset())
    search = store.add_search(_search(webset.id))
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_idle(webset.id)
    assert ei.value.code == "webset_not_settled"
    store.settle_search(webset.id, search.id, "idle")

    pending = store.save_item(_item(webset.id, created_at=_T0))
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_idle(webset.id)
    assert ei.value.code == "webset_not_settled"
    store.save_item(pending.model_copy(update={"verification": "rejected"}))

    store.add_enrichment(webset.id, EnrichmentDef(name="fit", type="text"))
    verified = store.save_item(
        _item(
            webset.id,
            created_at=_T0 + timedelta(seconds=1),
            url="https://example.com/v",
            verification="verified",
        )
    )
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_idle(webset.id)
    assert ei.value.code == "webset_not_settled"
    store.save_item(verified.model_copy(update={"enrichments": {"fit": _resolved_field()}}))
    assert store.set_webset_idle(webset.id).status == "idle"

    # An unresolved field is terminal too: it settles the item without blocking idle.
    second = store.create_webset(_webset())
    store.add_enrichment(second.id, EnrichmentDef(name="fit", type="text"))
    store.save_item(
        _item(
            second.id,
            created_at=_T0,
            verification="verified",
            enrichments={"fit": EnrichedField(status="unresolved", error="no citation")},
        )
    )
    assert store.set_webset_idle(second.id).status == "idle"

    # Detaching the def unblocks an item that never received the field.
    third = store.create_webset(_webset())
    defn = store.add_enrichment(third.id, EnrichmentDef(name="fit", type="text"))
    store.save_item(_item(third.id, created_at=_T0, verification="verified"))
    with pytest.raises(WebsetStoreError) as ei:
        store.set_webset_idle(third.id)
    assert ei.value.code == "webset_not_settled"
    store.remove_enrichment(third.id, defn.id)
    assert store.set_webset_idle(third.id).status == "idle"


def test_enrichment_cap_attach_list_update_and_remove(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    defs = [
        store.add_enrichment(webset.id, EnrichmentDef(name=f"field_{i}", type="text"))
        for i in range(10)
    ]
    assert all(_WSE_ID_RE.fullmatch(d.id) for d in defs)
    assert [d.name for d in store.list_enrichments(webset.id)] == [f"field_{i}" for i in range(10)]
    assert [d.name for d in store.get_webset(webset.id).enrichments] == [
        f"field_{i}" for i in range(10)
    ]
    with pytest.raises(WebsetStoreError) as ei:
        store.add_enrichment(webset.id, EnrichmentDef(name="eleventh", type="text"))
    assert ei.value.code == "enrichment_limit_exceeded"

    store.remove_enrichment(webset.id, defs[0].id)
    assert [d.name for d in store.list_enrichments(webset.id)] == [
        f"field_{i}" for i in range(1, 10)
    ]
    store.add_enrichment(webset.id, EnrichmentDef(name="field_10", type="text"))
    assert len(store.list_enrichments(webset.id)) == 10

    updated = store.update_enrichment(webset.id, defs[1].model_copy(update={"status": "idle"}))
    assert updated.status == "idle"
    assert store.list_enrichments(webset.id)[0].status == "idle"
    with pytest.raises(WebsetStoreError) as ei:
        store.update_enrichment(webset.id, defs[0].model_copy(update={"status": "idle"}))
    assert ei.value.code == "enrichment_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.remove_enrichment(webset.id, _GHOST_ENRICHMENT)
    assert ei.value.code == "enrichment_not_found"

    overflowing = Webset.model_construct(
        criteria=_criteria(),
        enrichments=[EnrichmentDef(name=f"field_{i}", type="text") for i in range(11)],
    )
    with pytest.raises(WebsetStoreError) as ei:
        store.create_webset(overflowing)
    assert ei.value.code == "enrichment_limit_exceeded"
    with sqlite3.connect(tmp_path / "websets.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM websets").fetchone()[0] == 1


def test_monitor_crud_and_newest_first_ordering(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    first = store.add_monitor(
        webset.id, WebsetMonitor(webset_id=webset.id, interval_seconds=3600, created_at=_T0)
    )
    second = store.add_monitor(
        webset.id,
        WebsetMonitor(
            webset_id=webset.id, interval_seconds=60, created_at=_T0 + timedelta(hours=1)
        ),
    )
    third = store.add_monitor(
        webset.id,
        WebsetMonitor(
            webset_id=webset.id,
            interval_seconds=120,
            webhook_url="https://hooks.example.com/x",
            created_at=_T0 - timedelta(hours=1),
        ),
    )
    assert _WSM_ID_RE.fullmatch(first.id)
    assert all(m.object == "webset_monitor" for m in store.list_monitors(webset.id))
    assert [m.id for m in store.list_monitors(webset.id)] == [second.id, first.id, third.id]
    assert store.get_monitor(webset.id, third.id) == third
    with pytest.raises(WebsetStoreError) as ei:
        store.get_monitor(webset.id, _GHOST_MONITOR)
    assert ei.value.code == "monitor_not_found"

    # Server-assigned created_at when the caller omits it.
    other = store.create_webset(_webset())
    assigned = store.add_monitor(other.id, WebsetMonitor(webset_id=other.id, interval_seconds=60))
    assert assigned.created_at is not None


def test_list_all_monitors_spans_websets_in_created_order(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    assert store.list_all_monitors() == []

    first_ws = store.create_webset(_webset())
    second_ws = store.create_webset(_webset())
    newest = store.add_monitor(
        second_ws.id,
        WebsetMonitor(webset_id=second_ws.id, created_at=_T0 + timedelta(hours=2)),
    )
    oldest = store.add_monitor(first_ws.id, WebsetMonitor(webset_id=first_ws.id, created_at=_T0))
    middle = store.add_monitor(
        first_ws.id,
        WebsetMonitor(webset_id=first_ws.id, created_at=_T0 + timedelta(hours=1)),
    )

    all_monitors = store.list_all_monitors()
    assert [m.id for m in all_monitors] == [oldest.id, middle.id, newest.id]
    assert [m.webset_id for m in all_monitors] == [
        first_ws.id,
        first_ws.id,
        second_ws.id,
    ]
    assert store.list_all_monitors() == all_monitors


def test_update_monitor_persists_body_and_preserves_created_at(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    monitor = store.add_monitor(
        webset.id,
        WebsetMonitor(webset_id=webset.id, interval_seconds=120, created_at=_T0),
    )
    assert monitor.paused is False

    paused = store.update_monitor(
        webset.id, monitor.id, monitor.model_copy(update={"paused": True})
    )

    assert paused.id == monitor.id
    assert paused.paused is True
    assert paused.created_at == _T0
    assert store.get_monitor(webset.id, monitor.id) == paused
    assert [m.paused for m in store.list_monitors(webset.id)] == [True]
    assert [m.paused for m in store.list_all_monitors()] == [True]

    resumed = store.update_monitor(
        webset.id, monitor.id, paused.model_copy(update={"paused": False})
    )
    assert resumed.paused is False
    assert store.get_monitor(webset.id, monitor.id).paused is False

    # An incoming body without created_at keeps the stored row's timestamp.
    bare = store.update_monitor(
        webset.id, monitor.id, WebsetMonitor(webset_id=webset.id, paused=False)
    )
    assert bare.created_at == _T0

    with pytest.raises(WebsetStoreError) as ei:
        store.update_monitor(webset.id, _GHOST_MONITOR, monitor)
    assert ei.value.code == "monitor_not_found"

    other = store.create_webset(_webset())
    with pytest.raises(WebsetStoreError) as ei:
        store.update_monitor(other.id, monitor.id, monitor)
    assert ei.value.code == "monitor_not_found"


def test_webhook_crud_assigns_non_empty_ids_and_ledger_is_insert_or_ignore(tmp_path):
    path = tmp_path / "websets.sqlite3"
    store = WebsetStore(db_path=str(path))
    webset = store.create_webset(_webset())
    webhook = store.add_webhook(
        webset.id,
        WebhookConfig(
            url="https://hooks.example.com/x",
            events=["item.enriched", "webset.idle"],
            secret="s3cr3t",
        ),
    )
    assert _WEBHOOK_ID_RE.fullmatch(webhook.webhook_id)
    assert webhook.created_at is not None
    spoofed = store.add_webhook(
        webset.id, WebhookConfig(webhook_id="caller-supplied", url="https://hooks.example.com/y")
    )
    assert spoofed.webhook_id != "caller-supplied"
    assert _WEBHOOK_ID_RE.fullmatch(spoofed.webhook_id)
    assert store.get_webhook(webset.id, webhook.webhook_id) == webhook
    assert [w.webhook_id for w in store.list_webhooks(webset.id)] == [
        webhook.webhook_id,
        spoofed.webhook_id,
    ]
    with pytest.raises(WebsetStoreError) as ei:
        store.get_webhook(webset.id, "f" * 32)
    assert ei.value.code == "webhook_not_found"

    rotated = webhook.model_copy(
        update={
            "secret": "rotated",
            "previous_secret": webhook.secret,
            "previous_expires_at": _T0 + timedelta(hours=24),
        }
    )
    stored_rotation = store.update_webhook(webset.id, rotated)
    assert store.get_webhook(webset.id, webhook.webhook_id) == stored_rotation
    assert stored_rotation.created_at == webhook.created_at
    with pytest.raises(WebsetStoreError) as ei:
        store.update_webhook(webset.id, rotated.model_copy(update={"webhook_id": "f" * 32}))
    assert ei.value.code == "webhook_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.update_webhook(webset.id, rotated.model_copy(update={"webhook_id": ""}))
    assert ei.value.code == "webhook_id_required"

    search = store.add_search(_search(webset.id))
    first_event = store.append_event(
        WebsetEvent(webset_id=webset.id, type="webset.idle", search_id=search.id)
    )
    second_event = store.append_event(
        WebsetEvent(
            webset_id=webset.id, type="item.created", search_id=search.id, item_id="wsi_" + "a" * 32
        )
    )
    assert (
        store.record_webhook_delivery(webhook.webhook_id, first_event.id, ok=True, status_code=200)
        is True
    )
    assert (
        store.record_webhook_delivery(webhook.webhook_id, first_event.id, ok=False, error="late")
        is False
    )
    rows = store.list_webhook_deliveries(webhook.webhook_id)
    assert len(rows) == 1
    assert rows[0] == store.get_webhook_delivery(webhook.webhook_id, first_event.id)
    assert rows[0].ok is True and rows[0].status_code == 200
    assert (
        store.record_webhook_delivery(
            webhook.webhook_id, second_event.id, ok=False, status_code=500, error="boom"
        )
        is True
    )
    assert len(store.list_webhook_deliveries(webhook.webhook_id)) == 2
    assert store.list_webhook_deliveries(spoofed.webhook_id) == []
    assert store.get_webhook_delivery(webhook.webhook_id, _GHOST) is None

    with pytest.raises(WebsetStoreError) as ei:
        store.record_webhook_delivery("", first_event.id, ok=True)
    assert ei.value.code == "invalid_webhook_delivery"
    with pytest.raises(WebsetStoreError) as ei:
        store.record_webhook_delivery(webhook.webhook_id, "", ok=True)
    assert ei.value.code == "invalid_webhook_delivery"

    with sqlite3.connect(path) as conn:
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='webhook_deliveries'"
        ).fetchone()[0]
    assert "PRIMARY KEY (webhook_id, event_id)" in ddl


# ── #4226: re-delivery ledger state (attempts / next_attempt_at) ──────────────

_LEGACY_DELIVERIES_DDL = """
CREATE TABLE webhook_deliveries (
    webhook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    ok INTEGER NOT NULL,
    status_code INTEGER,
    error TEXT,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (webhook_id, event_id)
);
"""


def _table_columns(path, table: str) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_legacy_webhook_deliveries_table_gains_retry_columns(tmp_path):
    """A pre-#4226 DB is upgraded in place on open, and reopening is a no-op."""
    path = tmp_path / "legacy.sqlite3"
    webhook_id, event_id = "w" * 32, "e" * 32
    with sqlite3.connect(path) as conn:
        conn.executescript(_LEGACY_DELIVERIES_DDL)
        conn.execute(
            "INSERT INTO webhook_deliveries VALUES (?, ?, ?, ?, ?, ?)",
            (webhook_id, event_id, 0, 503, "HTTP 503", _T0.isoformat()),
        )
    assert _table_columns(path, "webhook_deliveries") == {
        "webhook_id",
        "event_id",
        "ok",
        "status_code",
        "error",
        "recorded_at",
    }

    store = WebsetStore(db_path=str(path))
    assert {"attempts", "next_attempt_at"} <= _table_columns(path, "webhook_deliveries")
    legacy = store.get_webhook_delivery(webhook_id, event_id)
    assert legacy is not None
    assert legacy.attempts == 0 and legacy.next_attempt_at is None
    assert legacy.recorded_at == _T0

    migrated = store.update_webhook_delivery(
        webhook_id,
        event_id,
        ok=False,
        status_code=503,
        error="HTTP 503",
        attempts=1,
        next_attempt_at=_T0 + timedelta(seconds=300),
    )
    assert migrated.attempts == 1 and migrated.recorded_at == _T0
    # Reopening runs both guarded ALTERs again; the store must stay usable.
    reopened = WebsetStore(db_path=str(path))
    assert reopened.get_webhook_delivery(webhook_id, event_id) == migrated


def test_update_webhook_delivery_round_trips_and_keeps_recorded_at(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "_now", lambda: _T0)
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webhook_id, event_id = "a" * 32, "e" * 32
    store.record_webhook_delivery(webhook_id, event_id, ok=False, status_code=503, error="HTTP 503")
    recorded = store.get_webhook_delivery(webhook_id, event_id)
    assert recorded is not None
    assert recorded.attempts == 0 and recorded.next_attempt_at is None

    scheduled = store.update_webhook_delivery(
        webhook_id,
        event_id,
        ok=False,
        status_code=503,
        error="HTTP 503",
        attempts=1,
        next_attempt_at=_T0 + timedelta(seconds=300),
    )
    assert scheduled == store.get_webhook_delivery(webhook_id, event_id)
    assert scheduled.attempts == 1
    assert scheduled.next_attempt_at == _T0 + timedelta(seconds=300)
    assert scheduled.recorded_at == recorded.recorded_at == _T0

    recovered = store.update_webhook_delivery(
        webhook_id,
        event_id,
        ok=True,
        status_code=200,
        error=None,
        attempts=2,
        next_attempt_at=None,
    )
    assert recovered.ok is True and recovered.status_code == 200 and recovered.error is None
    assert recovered.attempts == 2 and recovered.next_attempt_at is None
    assert recovered.recorded_at == _T0

    with pytest.raises(WebsetStoreError) as ei:
        store.update_webhook_delivery(
            "b" * 32,
            event_id,
            ok=True,
            status_code=200,
            error=None,
            attempts=1,
            next_attempt_at=None,
        )
    assert ei.value.code == "webhook_not_found"


def test_list_due_webhook_deliveries_filters_and_orders(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "_now", lambda: _T0 - timedelta(minutes=5))
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))

    def _at(moment: datetime) -> None:
        monkeypatch.setattr(store_module, "_now", lambda: moment)

    # Unscheduled first-attempt failures: due, oldest recorded first.
    assert store.record_webhook_delivery(
        "a" * 32, "e" * 32, ok=False, status_code=500, error="HTTP 500"
    )
    _at(_T0 - timedelta(minutes=4))
    assert store.record_webhook_delivery(
        "b" * 32, "e" * 32, ok=False, status_code=500, error="HTTP 500"
    )
    # Scheduled failure whose moment has arrived: due after the NULL group.
    _at(_T0 - timedelta(minutes=3))
    assert store.record_webhook_delivery(
        "c" * 32, "e" * 32, ok=False, status_code=503, error="HTTP 503"
    )
    store.update_webhook_delivery(
        "c" * 32,
        "e" * 32,
        ok=False,
        status_code=503,
        error="HTTP 503",
        attempts=1,
        next_attempt_at=_T0 - timedelta(seconds=60),
    )
    # Not due: future-scheduled, exhausted (attempts at the cap), or successful.
    assert store.record_webhook_delivery(
        "d" * 32, "e" * 32, ok=False, status_code=503, error="HTTP 503"
    )
    store.update_webhook_delivery(
        "d" * 32,
        "e" * 32,
        ok=False,
        status_code=503,
        error="HTTP 503",
        attempts=1,
        next_attempt_at=_T0 + timedelta(seconds=60),
    )
    assert store.record_webhook_delivery(
        "f" * 32, "e" * 32, ok=False, status_code=503, error="HTTP 503"
    )
    store.update_webhook_delivery(
        "f" * 32,
        "e" * 32,
        ok=False,
        status_code=503,
        error="HTTP 503",
        attempts=store_module._MAX_DELIVERY_ATTEMPTS,
        next_attempt_at=None,
    )
    assert store.record_webhook_delivery("g" * 32, "e" * 32, ok=True, status_code=200)

    due = store.list_due_webhook_deliveries(now=_T0)
    assert [row.webhook_id for row in due] == ["a" * 32, "b" * 32, "c" * 32]
    assert due[2].attempts == 1
    assert due[2].next_attempt_at == _T0 - timedelta(seconds=60)
    assert [row.webhook_id for row in store.list_due_webhook_deliveries(now=_T0, limit=2)] == [
        "a" * 32,
        "b" * 32,
    ]
    # An exhausted row never becomes due again, however far the clock runs;
    # the future-scheduled row does (its moment has passed by then).
    far = store.list_due_webhook_deliveries(now=_T0 + timedelta(days=365))
    assert {row.webhook_id for row in far} == {"a" * 32, "b" * 32, "c" * 32, "d" * 32}
    assert "f" * 32 not in {row.webhook_id for row in far}


def test_get_event_round_trips_and_missing_raises(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    webset = store.create_webset(_webset())
    search = store.add_search(_search(webset.id))
    event = store.append_event(
        WebsetEvent(webset_id=webset.id, type="webset.idle", search_id=search.id)
    )
    assert store.get_event(event.id) == event
    with pytest.raises(WebsetStoreError) as ei:
        store.get_event("e" * 32)
    assert ei.value.code == "event_not_found"


def test_delivery_attempt_cap_matches_the_events_redelivery_schedule():
    """The due selector's cap and the events retry schedule are one contract."""
    from digisearch.websets import events as events_module

    assert store_module._MAX_DELIVERY_ATTEMPTS == events_module._WEBHOOK_REDELIVERY_ATTEMPTS


def test_create_webset_assigns_server_owned_identity_for_nested_children(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    spoofed_webset = "ws_" + "e" * 32
    created = store.create_webset(
        _webset(
            id=spoofed_webset,
            status="idle",
            enrichments=[{"name": "fit", "type": "text"}],
            searches=[_search("ws_" + "d" * 32, query="nested")],
        )
    )
    assert created.id != spoofed_webset
    assert _WS_ID_RE.fullmatch(created.id)
    assert created.status == "running"
    assert created.searches[0].webset_id == created.id
    assert _WSS_ID_RE.fullmatch(created.searches[0].id)
    assert [e.name for e in created.enrichments] == ["fit"]
    assert store.get_webset(created.id) == created


def test_children_require_an_existing_webset(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    search = _search(_GHOST)
    with pytest.raises(WebsetStoreError) as ei:
        store.add_search(search)
    assert ei.value.code == "webset_not_found"
    assert store.list_searches(_GHOST) == []
    with pytest.raises(WebsetStoreError) as ei:
        store.save_item(_item(_GHOST, created_at=_T0))
    assert ei.value.code == "webset_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.add_enrichment(_GHOST, EnrichmentDef(name="fit", type="text"))
    assert ei.value.code == "webset_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.add_monitor(_GHOST, WebsetMonitor(webset_id=_GHOST))
    assert ei.value.code == "webset_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.add_webhook(_GHOST, WebhookConfig(url="https://hooks.example.com/x"))
    assert ei.value.code == "webset_not_found"
    with pytest.raises(WebsetStoreError) as ei:
        store.append_event(
            WebsetEvent(webset_id=_GHOST, type="webset.idle", search_id=_GHOST_SEARCH)
        )
    assert ei.value.code == "webset_not_found"


def test_resume_selector_is_the_union_of_running_websets_and_running_searches(tmp_path):
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))

    first_pass = store.create_webset(_webset())
    store.add_search(_search(first_pass.id))

    sticky = store.create_webset(_webset())
    settled = store.add_search(_search(sticky.id))
    store.settle_search(sticky.id, settled.id, "idle")
    assert store.set_webset_idle(sticky.id).status == "idle"
    store.add_search(_search(sticky.id, query="refresh"))

    clean = store.create_webset(_webset())
    clean_search = store.add_search(_search(clean.id))
    store.settle_search(clean.id, clean_search.id, "idle")
    store.set_webset_idle(clean.id)

    failed = store.create_webset(_webset())
    failed_search = store.add_search(_search(failed.id))
    store.settle_search(failed.id, failed_search.id, "failed")
    store.set_webset_status(failed.id, "failed")

    cancelled = store.create_webset(_webset())
    store.add_search(_search(cancelled.id))
    store.cancel_webset(cancelled.id)

    selected = store.list_incomplete_websets()
    assert {w.id for w in selected} == {first_pass.id, sticky.id}
    assert all(w.searches for w in selected)


def test_store_opens_in_wal_mode_with_busy_timeout(tmp_path):
    path = tmp_path / "websets.sqlite3"
    store = WebsetStore(db_path=str(path))
    # journal_mode is persisted in the file header, so a second connection sees it.
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_get_store_prefers_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(tmp_path / "env.sqlite3"))
    store = get_store(db_path=str(tmp_path / "explicit.sqlite3"))
    store.create_webset(_webset())
    assert (tmp_path / "explicit.sqlite3").exists()
    assert not (tmp_path / "env.sqlite3").exists()


def test_get_store_reads_env_db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(tmp_path / "env.sqlite3"))
    monkeypatch.delenv("DIGI_WORKSPACE", raising=False)
    get_store().create_webset(_webset())
    assert (tmp_path / "env.sqlite3").exists()


def test_get_store_defaults_to_workspace_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGISEARCH_WEBSETS_DB", raising=False)
    monkeypatch.setenv("DIGI_WORKSPACE", str(tmp_path))
    get_store().create_webset(_webset())
    assert (tmp_path / ".digisearch" / "websets.sqlite3").exists()


def test_get_store_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGISEARCH_WEBSETS_DB", raising=False)
    monkeypatch.delenv("DIGI_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    get_store().create_webset(_webset())
    assert (tmp_path / ".digisearch" / "websets.sqlite3").exists()
