"""Phase D webset events (#4066, Task 5a) — the single event writer.

The append-only ``events`` table and its ``(webset_id, dedup_key)`` generation
key are owned by the T2 store (``websets/store.py``): the dedup key is built from
``(kind, search_id, item_id or "", field or "")`` so a resumed pass within one
``WebsetSearch`` generation cannot duplicate an event, while each new generation
(``add_search`` / the ``add_enrichment`` backfill run / ``trigger_monitor``) may
legitimately re-emit terminal events (spec § Async lifecycle, flag I3).

This module is the only place the runner builds event rows, and it delegates
every write to :meth:`WebsetStore.append_event` — events are never written
anywhere else (single-writer rule; T2 review note), so the dedup-key and
generation scheme is enforced at exactly one site. ``payload`` is the compact
delivery/consumer body (ids, urls, titles, field names, reasoning) and never a
full page body.

Webhook fan-out and the ``webhook_deliveries`` ledger are Task 5b (human gate,
R13) and extend this module; T5a ships no outbound delivery.
"""

from __future__ import annotations

from typing import Any

from digisearch.websets.models import EventKind, WebsetEvent, WebsetItem
from digisearch.websets.store import WebsetStore

__all__ = [
    "append_event",
    "emit_item_created",
    "emit_item_enriched",
    "emit_webset_failed",
    "emit_webset_idle",
    "list_events",
]


def append_event(store: WebsetStore, event: WebsetEvent) -> WebsetEvent:
    """Append one event through the store's INSERT-or-ignore path.

    Returns the canonical stored row: a duplicate within a generation returns
    the first stored event instead of appending a second one (the
    ``(webset_id, dedup_key)`` UNIQUE index).
    """
    return store.append_event(event)


def list_events(
    store: WebsetStore,
    webset_id: str,
    *,
    after: str | None = None,
    limit: int = 50,
) -> tuple[list[WebsetEvent], str | None]:
    """Cursor-page a webset's event log oldest-first (R11) through the store."""
    return store.list_events(webset_id, after=after, limit=limit)


def _emit(
    store: WebsetStore,
    webset_id: str,
    kind: EventKind,
    search_id: str,
    *,
    payload: dict[str, Any],
    item_id: str = "",
) -> WebsetEvent:
    return append_event(
        store,
        WebsetEvent(
            webset_id=webset_id,
            type=kind,
            search_id=search_id,
            item_id=item_id,
            payload=payload,
        ),
    )


def emit_item_created(store: WebsetStore, item: WebsetItem, search_id: str) -> WebsetEvent:
    """``item.created`` — emitted once the candidate passed verification.

    Rejected candidates emit no item event and stay queryable via
    ``items?verification=rejected`` for audit (spec § Architecture). The
    generation that admitted the item is part of the dedup key, so a resume
    within one ``WebsetSearch`` cannot duplicate this event.
    """
    return _emit(
        store,
        item.webset_id,
        "item.created",
        search_id,
        item_id=item.id,
        payload={"item_id": item.id, "url": item.url, "title": item.title},
    )


def emit_item_enriched(store: WebsetStore, item: WebsetItem, search_id: str) -> WebsetEvent:
    """``item.enriched`` — all requested fields settled with >= 1 resolved.

    An item whose every field is ``unresolved``/``skipped`` settles silently
    (spec § Architecture); this emitter is only called once the terminal-state
    conditions hold.
    """
    return _emit(
        store,
        item.webset_id,
        "item.enriched",
        search_id,
        item_id=item.id,
        payload={"item_id": item.id, "url": item.url, "fields": sorted(item.enrichments)},
    )


def emit_webset_idle(store: WebsetStore, webset_id: str, search_id: str) -> WebsetEvent:
    """``webset.idle`` — terminal ``webset.*`` events carry the pass generation."""
    return _emit(
        store,
        webset_id,
        "webset.idle",
        search_id,
        payload={"webset_id": webset_id, "status": "idle"},
    )


def emit_webset_failed(
    store: WebsetStore, webset_id: str, search_id: str, reason: str
) -> WebsetEvent:
    """``webset.failed`` — a webset-level failure under the pass generation."""
    return _emit(
        store,
        webset_id,
        "webset.failed",
        search_id,
        payload={"webset_id": webset_id, "status": "failed", "reason": reason},
    )
