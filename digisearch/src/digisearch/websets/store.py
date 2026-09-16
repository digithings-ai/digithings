# score:allow untyped any
# stored bodies and result rows are dynamic JSON; Any is the honest annotation.
"""Phase D webset store — SQLite persistence for websets (#4066, Task 2).

Stdlib ``sqlite3`` only: this store is the single source of truth for websets,
their settling-pass generations, verified items, enrichment defs, refresh
monitors, webhooks, the delivery ledger, and the append-only event log. Storage
mirrors the spec's object tables:

- ``websets (webset_id PK, body JSON, status, workspace_id, created_at,
  updated_at)`` — ``body`` is the base ``Webset`` document (criteria, backend,
  workspace, status, timestamps) so the model can evolve without migrations;
  ``status`` and ``workspace_id`` are real columns for the resume selector and
  workspace filters. Nested ``searches``/``enrichments`` live in their own
  tables and are assembled back onto reads, so a search-status settlement needs
  no webset-body rewrite.
- ``searches (search_id PK, webset_id, status, created_at, body)`` — one row
  per settling-pass generation; ``status`` backs the resume selector's
  non-terminal union arm, and the persisted ``body`` carries the generation's
  ``verification_mode`` (T6 review carry) so a resumed or refreshed ``rules``
  webset never silently falls back to ``llm``.
- ``items (item_id PK, webset_id, verification, created_at, body)`` — the
  ``verification`` column backs filtered listing; ordering is
  ``created_at DESC, item_id DESC`` (R11 newest-first) so the item-id cursor is
  a stable positional anchor.
- ``enrichments (enrichment_id PK, webset_id, name, status, created_at, body)``
  — at most 10 active defs per webset; ``name`` is the item field key.
- ``webset_monitors (monitor_id PK, webset_id, created_at, body)`` — refresh-
  cadence metadata read by the tick driver (``list_all_monitors``), never a
  Phase C ``Watch``.
- ``webhooks (webhook_id PK, webset_id, created_at, body)`` — the id is
  server-assigned (uuid4 hex, outside the five prefixed families) because
  :class:`~digisearch.websets.models.WebhookConfig` permits ``""`` and the
  ledger key below must never collapse to an empty id.
- ``webhook_deliveries (webhook_id, event_id, ok, status_code, error,
  recorded_at, attempts, next_attempt_at)`` with ``PRIMARY KEY (webhook_id,
  event_id)`` — the T5b ledger; :meth:`WebsetStore.record_webhook_delivery` is
  INSERT-or-ignore so a resumed delivery cannot double-record. ``attempts`` and
  ``next_attempt_at`` (ISO-8601 UTC, nullable) are the #4226 re-delivery state:
  fresh failures start ``attempts=0``/``next_attempt_at NULL`` (unscheduled, so
  a due scan picks them up), :meth:`WebsetStore.update_webhook_delivery` moves
  them in place, and :meth:`WebsetStore.list_due_webhook_deliveries` selects
  failed, unexhausted rows whose scheduled moment has arrived. Databases
  predating those columns are upgraded in ``__init__`` with guarded ``ALTER
  TABLE`` statements (the ``monitors.store`` precedent).
- ``events (event_id PK, webset_id, kind, dedup_key, created_at, body)`` with a
  UNIQUE ``(webset_id, dedup_key)`` index — append-only (there is deliberately
  no update/delete path) and INSERT-or-ignore. ``dedup_key`` is built from
  ``(kind, search_id, item_id or "", field or "")``; the generation that
  produced the event is part of the key, so a resume within one search cannot
  duplicate an event while each ``add_search`` / backfill / ``trigger_monitor``
  pass (a new ``WebsetSearch`` row) can legitimately re-emit terminal events.

Cursors (R11): :meth:`WebsetStore.list_items` is newest-first with the previous
page's last item id as ``cursor``; :meth:`WebsetStore.list_events` is
oldest-first with the last seen event id as ``after``. An unknown cursor raises
``WebsetStoreError(code="cursor_not_found")`` instead of silently restarting;
event cursors are additionally shape-checked at the boundary (``WebsetEvent.id``
carries no model pattern) so an arbitrary string is rejected before any lookup.

Lifecycle: websets and searches only move ``running -> idle|failed|cancelled``
(``idle`` is sticky, and a refresh pass runs as a new search generation without
flipping the webset back); :meth:`WebsetStore.cancel_webset` settles every
non-terminal search ``cancelled`` and leaves an already-terminal webset status
alone. :meth:`WebsetStore.set_webset_idle` refuses while any search is
``running``, any item is ``pending`` verification, or any verified item is
missing a field for an active enrichment def (``webset_not_settled``), so
``idle`` can only be reached with the work actually settled.

Connection and concurrency (R5): exactly Phase C's discipline — each instance
owns one connection opened in ``__init__``; ``sqlite3`` connections are
thread-bound (``check_same_thread`` keeps its default), so an instance is
single-threaded and one store is constructed per thread/request (the
module-level :func:`get_store` does). The file opens in WAL mode with a 5s busy
timeout so the HTTP process and any second process can share it; the store adds
no in-process locking of its own.

Store home (R6): :func:`get_store` resolves explicit path →
``DIGISEARCH_WEBSETS_DB`` → ``{DIGI_WORKSPACE}/.digisearch/websets.sqlite3`` →
``./.digisearch/websets.sqlite3`` (cwd fallback for host/test runs).
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from digisearch.websets.models import (
    EnrichmentDef,
    EventKind,
    SearchStatus,
    VerificationState,
    WebhookConfig,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetMonitor,
    WebsetSearch,
    WebsetStatus,
)

__all__ = ["WebhookDelivery", "WebsetStore", "WebsetStoreError", "get_store"]

_ENV_DB_PATH = "DIGISEARCH_WEBSETS_DB"
_ENV_WORKSPACE = "DIGI_WORKSPACE"
_WORKSPACE_DB_DIR = ".digisearch"
_DB_FILENAME = "websets.sqlite3"

_BUSY_TIMEOUT_MS = 5000
_MIN_LIMIT = 1
_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50
_MAX_ENRICHMENTS = 10

#: Re-delivery cap, mirrored from ``websets.events._WEBHOOK_REDELIVERY_ATTEMPTS``
#: (kept in both modules to avoid a store -> events import cycle; a test pins
#: the equality). A failed row stops being due once ``attempts`` reaches it, so
#: an exhausted row (``next_attempt_at NULL``) is never offered again. The cap
#: sits one past the events ladder's four rungs, so the final 21600s wait is
#: still offered before a row exhausts.
_MAX_DELIVERY_ATTEMPTS = 5

_EVENT_KINDS = frozenset(get_args(EventKind))
_EVENT_ID_RE = re.compile(r"[0-9a-f]{32}")
_TERMINAL_SEARCH_STATUSES = frozenset({"idle", "failed", "cancelled"})

# Websets and searches share the one-way lifecycle: running -> terminal, sticky
# terminals, never backwards (idle is the only success terminal).
_TRANSITIONS: dict[str, frozenset[str]] = {
    "running": frozenset({"idle", "failed", "cancelled"}),
    "idle": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

# The dedup tuple (kind, search_id, item_id or "", field or "") is joined with a
# control character no id/name can carry, so the composite key stays unambiguous.
_DEDUP_SEPARATOR = "\x1f"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS websets (
    webset_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    workspace_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_websets_status ON websets (status);
CREATE INDEX IF NOT EXISTS idx_websets_workspace ON websets (workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS searches (
    search_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_webset ON searches (webset_id);
CREATE INDEX IF NOT EXISTS idx_searches_status ON searches (status);

CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    verification TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_webset_created ON items (webset_id, created_at DESC, item_id DESC);

CREATE TABLE IF NOT EXISTS enrichments (
    enrichment_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrichments_webset ON enrichments (webset_id);

CREATE TABLE IF NOT EXISTS webset_monitors (
    monitor_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webset_monitors_webset ON webset_monitors (webset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhooks_webset ON webhooks (webset_id);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    webhook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    ok INTEGER NOT NULL,
    status_code INTEGER,
    error TEXT,
    recorded_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    PRIMARY KEY (webhook_id, event_id)
);

CREATE TABLE IF NOT EXISTS bridge_handoffs (
    watch_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    webset_id TEXT NOT NULL,
    search_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (watch_id, run_id, webset_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    webset_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_webset_dedup ON events (webset_id, dedup_key);
CREATE INDEX IF NOT EXISTS idx_events_webset ON events (webset_id);
"""


class WebsetStoreError(RuntimeError):
    """Store failure carrying the stable API-facing ``code``.

    Spec codes raised today: ``webset_not_found``, ``search_not_found``,
    ``monitor_not_found``, ``enrichment_limit_exceeded``, ``cursor_not_found``
    (unknown item/event cursor). Sibling codes for the types the spec's list
    omits: ``item_not_found``, ``enrichment_not_found``, ``webhook_not_found``
    (also a missing delivery-ledger pair on update), ``webhook_id_required`` (an
    empty webhook id can never key the delivery ledger), ``event_not_found`` (a
    missing event row). Internal invariant violations raise
    ``transition_invalid`` (illegal status move), ``webset_not_settled`` (idle
    requested while work is pending), ``invalid_event_kind`` (unknown append
    kind), ``invalid_webhook_delivery`` (empty ledger key),
    ``bridge_handoff_not_stored`` (a bridge ledger row whose search id could
    not be read back), and ``event_not_stored`` (a conflicting event row could
    not be read back).
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WebhookDelivery:
    """One ``webhook_deliveries`` ledger row (T5b records terminal state).

    ``attempts`` counts the re-deliveries the shared driver's loop has performed
    against the row (``0`` for a fresh first-attempt failure) and
    ``next_attempt_at`` is when the row becomes due again (``None`` when
    unscheduled or exhausted) — both #4226 re-delivery state carried on the
    ledger, not part of the original T5b row.
    """

    webhook_id: str
    event_id: str
    ok: bool
    recorded_at: datetime
    status_code: int | None = None
    error: str | None = None
    attempts: int = 0
    next_attempt_at: datetime | None = None


class WebsetStore:
    """SQLite-backed webset store (single connection, single thread)."""

    def __init__(self, db_path: str) -> None:
        # The resolved path is kept for callers that need to bind the same file
        # to their own thread's connection (the async runner constructs one
        # store per worker thread — the connection itself stays thread-bound).
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        with self._conn:
            self._conn.executescript(_SCHEMA)
            _ensure_delivery_retry_columns(self._conn)

    # -- websets ----------------------------------------------------------

    def create_webset(self, webset: Webset) -> Webset:
        """Persist *webset* under a server-assigned id; always starts ``running``.

        Nested ``enrichments`` (max 10) and ``searches`` are persisted too, with
        fresh server-assigned child ids and the webset id rewritten onto each
        search. ``created_at``/``updated_at`` are server-assigned; the volume is
        the webset itself, not its children, so its status starts ``running``
        regardless of the incoming value (lifecycle is server-owned).
        """
        if len(webset.enrichments) > _MAX_ENRICHMENTS:
            raise WebsetStoreError(
                f"at most {_MAX_ENRICHMENTS} active enrichments per webset",
                code="enrichment_limit_exceeded",
            )
        now = _now()
        created = webset.model_copy(
            update={
                "id": _new_entity_id("ws"),
                "status": "running",
                "searches": [],
                "enrichments": [],
                "created_at": now,
                "updated_at": now,
            }
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO websets (webset_id, body, status, workspace_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    created.id,
                    _base_document(created),
                    created.status,
                    created.workspace_id,
                    _utc_iso(now),
                    _utc_iso(now),
                ),
            )
        for enrichment in webset.enrichments:
            self.add_enrichment(created.id, enrichment)
        for search in webset.searches:
            self.add_search(search.model_copy(update={"webset_id": created.id}))
        return self.get_webset(created.id)

    def get_webset(self, webset_id: str) -> Webset:
        """Load one webset with its search generations and enrichment defs."""
        row = self._conn.execute(
            "SELECT body FROM websets WHERE webset_id = ?", (webset_id,)
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"webset not found: {webset_id}", code="webset_not_found")
        webset = Webset.model_validate_json(row[0])
        return webset.model_copy(
            update={
                "searches": self.list_searches(webset.id),
                "enrichments": self.list_enrichments(webset.id),
            }
        )

    def set_webset_status(self, webset_id: str, status: WebsetStatus) -> Webset:
        """Move a webset along ``running -> idle|failed|cancelled`` only.

        Setting the current status is a no-op; any other move out of a terminal
        status raises ``transition_invalid`` (``idle`` is sticky after the first
        completion — a refresh pass never flips the webset back).
        """
        current = self.get_webset(webset_id)
        _check_transition(f"webset {webset_id}", current.status, status)
        if current.status == status:
            return current
        updated = current.model_copy(update={"status": status, "updated_at": _now()})
        with self._conn:
            self._write_webset(updated)
        return updated

    def set_webset_idle(self, webset_id: str) -> Webset:
        """Mark a webset ``idle`` once every search, item, and field has settled.

        Refuses with ``webset_not_settled`` while any search is ``running``, any
        item is ``pending`` verification, or any verified item is missing a
        field for an active enrichment def — an ``idle`` webset must be fully
        settled, and ``idle`` is sticky once reached (a repeated call is a
        no-op).
        """
        current = self.get_webset(webset_id)
        _check_transition(f"webset {webset_id}", current.status, "idle")
        if current.status == "idle":
            return current
        blockers = self._settlement_blockers(webset_id)
        if blockers:
            raise WebsetStoreError(
                f"webset {webset_id} is not settled: " + "; ".join(blockers),
                code="webset_not_settled",
            )
        return self.set_webset_status(webset_id, "idle")

    def cancel_webset(self, webset_id: str) -> Webset:
        """Cancel a webset and settle every non-terminal search ``cancelled``.

        A ``running`` webset flips to ``cancelled``; an already-terminal webset
        keeps its status (``idle`` is sticky, ``failed``/``cancelled`` never
        move) while any still-running refresh search is settled ``cancelled``.
        """
        webset = self.get_webset(webset_id)
        flip = webset.status == "running"
        with self._conn:
            if flip:
                self._write_webset(
                    webset.model_copy(update={"status": "cancelled", "updated_at": _now()})
                )
            for search in self.list_searches(webset_id):
                if search.status == "running":
                    settled = search.model_copy(update={"status": "cancelled"})
                    self._conn.execute(
                        "UPDATE searches SET status = ?, body = ? WHERE search_id = ?",
                        (settled.status, settled.model_dump_json(), settled.id),
                    )
        return self.get_webset(webset_id)

    def list_incomplete_websets(self) -> list[Webset]:
        """The startup-resume selector: the union the amended spec defines.

        Every webset still ``running`` (a first pass that never completed) plus
        every webset holding a non-terminal ``running`` search (a crashed
        refresh on a sticky-``idle`` webset, or on any other status). A webset
        selected by both arms appears once.
        """
        rows = self._conn.execute(
            "SELECT webset_id FROM websets WHERE status = 'running' "
            "UNION SELECT webset_id FROM searches WHERE status = 'running' "
            "ORDER BY webset_id"
        ).fetchall()
        return [self.get_webset(row[0]) for row in rows]

    # -- searches ---------------------------------------------------------

    def add_search(self, search: WebsetSearch) -> WebsetSearch:
        """Append a new settling-pass generation under a server-assigned id.

        The search always starts ``running``; its id and the generation the
        event idempotency key carries come from here.
        """
        self.get_webset(search.webset_id)
        created = search.model_copy(update={"id": _new_entity_id("wss"), "status": "running"})
        with self._conn:
            self._conn.execute(
                "INSERT INTO searches (search_id, webset_id, status, created_at, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    created.id,
                    created.webset_id,
                    created.status,
                    _utc_iso(_now()),
                    created.model_dump_json(),
                ),
            )
        return created

    def bridge_handoff(
        self,
        webset_id: str,
        *,
        watch_id: str,
        run_id: str,
        search: WebsetSearch,
    ) -> tuple[WebsetSearch, bool]:
        """Idempotently open one search generation for a watch handoff (#4249).

        Single transaction: an INSERT-or-ignore ledger row keyed
        ``(watch_id, run_id, webset_id)``. The first delivery of a run creates
        the generation (server-assigned ``wss`` id, ``running``) and records its
        id on the ledger; every repeat delivery of the same run finds the ledger
        row and returns the already-created search unchanged — never a second
        generation. Returns ``(search, created)``.
        """
        self.get_webset(webset_id)
        now = _now()
        created: WebsetSearch | None = None
        existing_id: str | None = None
        with self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO bridge_handoffs "
                "(watch_id, run_id, webset_id, search_id, created_at) "
                "VALUES (?, ?, ?, NULL, ?)",
                (watch_id, run_id, webset_id, _utc_iso(now)),
            )
            if cursor.rowcount == 0:
                row = self._conn.execute(
                    "SELECT search_id FROM bridge_handoffs "
                    "WHERE watch_id = ? AND run_id = ? AND webset_id = ?",
                    (watch_id, run_id, webset_id),
                ).fetchone()
                existing_id = row[0] if row is not None else None
                if not existing_id:
                    raise WebsetStoreError(
                        f"bridge handoff ledger row has no search: {watch_id}/{run_id}",
                        code="bridge_handoff_not_stored",
                    )
            else:
                created = search.model_copy(
                    update={
                        "webset_id": webset_id,
                        "id": _new_entity_id("wss"),
                        "status": "running",
                    }
                )
                self._conn.execute(
                    "INSERT INTO searches (search_id, webset_id, status, created_at, body) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        created.id,
                        created.webset_id,
                        created.status,
                        _utc_iso(now),
                        created.model_dump_json(),
                    ),
                )
                self._conn.execute(
                    "UPDATE bridge_handoffs SET search_id = ? "
                    "WHERE watch_id = ? AND run_id = ? AND webset_id = ?",
                    (created.id, watch_id, run_id, webset_id),
                )
        if created is not None:
            return created, True
        assert existing_id is not None
        return self.get_search(webset_id, existing_id), False

    def get_search(self, webset_id: str, search_id: str) -> WebsetSearch:
        """Load one search generation; a missing id raises ``search_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM searches WHERE webset_id = ? AND search_id = ?",
            (webset_id, search_id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"search not found: {search_id}", code="search_not_found")
        return WebsetSearch.model_validate_json(row[0])

    def list_searches(self, webset_id: str) -> list[WebsetSearch]:
        """Search generations in creation order (oldest generation first)."""
        rows = self._conn.execute(
            "SELECT body FROM searches WHERE webset_id = ? ORDER BY rowid ASC", (webset_id,)
        ).fetchall()
        return [WebsetSearch.model_validate_json(row[0]) for row in rows]

    def settle_search(self, webset_id: str, search_id: str, status: SearchStatus) -> WebsetSearch:
        """Settle a ``running`` search as ``idle``/``failed``/``cancelled``.

        Only terminal targets are accepted, the current status must be
        ``running`` (or already the target, a no-op); anything else raises
        ``transition_invalid``.
        """
        if status not in _TERMINAL_SEARCH_STATUSES:
            raise WebsetStoreError(
                f"search {search_id} cannot settle as {status}", code="transition_invalid"
            )
        search = self.get_search(webset_id, search_id)
        if search.status == status:
            return search
        _check_transition(f"search {search_id}", search.status, status)
        settled = search.model_copy(update={"status": status})
        with self._conn:
            self._conn.execute(
                "UPDATE searches SET status = ?, body = ? WHERE search_id = ?",
                (settled.status, settled.model_dump_json(), settled.id),
            )
        return settled

    # -- items ------------------------------------------------------------

    def save_item(self, item: WebsetItem) -> WebsetItem:
        """Insert or replace *item*; ``created_at`` is assigned once, then kept.

        The runner is the only writer and re-drives pending rows on resume, so
        this is an upsert rather than an append; the first stored ``created_at``
        survives later saves that carry no timestamp.
        """
        self.get_webset(item.webset_id)
        row = self._conn.execute(
            "SELECT created_at FROM items WHERE item_id = ?", (item.id,)
        ).fetchone()
        created_at = item.created_at or (_parse_utc(row[0]) if row is not None else None) or _now()
        stored = item.model_copy(update={"created_at": created_at})
        with self._conn:
            self._conn.execute(
                "INSERT INTO items (item_id, webset_id, verification, created_at, body) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(item_id) DO UPDATE SET "
                "webset_id = excluded.webset_id, verification = excluded.verification, "
                "created_at = excluded.created_at, body = excluded.body",
                (
                    stored.id,
                    stored.webset_id,
                    stored.verification,
                    _utc_iso(created_at),
                    stored.model_dump_json(),
                ),
            )
        return stored

    def get_item(self, webset_id: str, item_id: str) -> WebsetItem:
        """Load one item; a missing id raises ``item_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM items WHERE webset_id = ? AND item_id = ?", (webset_id, item_id)
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"item not found: {item_id}", code="item_not_found")
        return WebsetItem.model_validate_json(row[0])

    def list_items(
        self,
        webset_id: str,
        *,
        verification: VerificationState | None = None,
        limit: int = _DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> tuple[list[WebsetItem], str | None]:
        """Page items newest-first; *cursor* is the previous page's last item id.

        ``limit`` is clamped to 1..200. ``next_cursor`` is this page's last item
        id when more rows exist, else ``None``. An unknown cursor (including one
        minted by another webset) raises ``cursor_not_found`` rather than
        silently restarting the page.
        """
        limit = _clamp_limit(limit)
        fetch = limit + 1
        where = " WHERE webset_id = ?"
        params: list[Any] = [webset_id]
        if verification is not None:
            where += " AND verification = ?"
            params.append(verification)
        if cursor is None:
            rows = self._conn.execute(
                f"SELECT body FROM items{where} ORDER BY created_at DESC, item_id DESC LIMIT ?",
                (*params, fetch),
            ).fetchall()
        else:
            cursor_row = self._conn.execute(
                "SELECT created_at FROM items WHERE webset_id = ? AND item_id = ?",
                (webset_id, cursor),
            ).fetchone()
            if cursor_row is None:
                raise WebsetStoreError(f"cursor item not found: {cursor}", code="cursor_not_found")
            created_at = cursor_row[0]
            rows = self._conn.execute(
                f"SELECT body FROM items{where} AND "
                "(created_at < ? OR (created_at = ? AND item_id < ?)) "
                "ORDER BY created_at DESC, item_id DESC LIMIT ?",
                (*params, created_at, created_at, cursor, fetch),
            ).fetchall()
        page = [WebsetItem.model_validate_json(row[0]) for row in rows[:limit]]
        next_cursor = page[-1].id if len(rows) > limit else None
        return page, next_cursor

    def count_items(self, webset_id: str) -> dict[str, int]:
        """Item counts per verification state (zeros when the webset has none)."""
        counts = {"pending": 0, "verified": 0, "rejected": 0}
        rows = self._conn.execute(
            "SELECT verification, COUNT(*) FROM items WHERE webset_id = ? GROUP BY verification",
            (webset_id,),
        ).fetchall()
        for verification, count in rows:
            if verification in counts:
                counts[verification] = int(count)
        return counts

    # -- enrichments ------------------------------------------------------

    def add_enrichment(self, webset_id: str, enrichment: EnrichmentDef) -> EnrichmentDef:
        """Attach an enrichment def (max 10 active) under a server-assigned id.

        The 11th active def raises ``enrichment_limit_exceeded`` (HTTP 400 at
        the service layer).
        """
        self.get_webset(webset_id)
        row = self._conn.execute(
            "SELECT COUNT(*) FROM enrichments WHERE webset_id = ?", (webset_id,)
        ).fetchone()
        if int(row[0]) >= _MAX_ENRICHMENTS:
            raise WebsetStoreError(
                f"at most {_MAX_ENRICHMENTS} active enrichments per webset",
                code="enrichment_limit_exceeded",
            )
        created = enrichment.model_copy(update={"id": _new_entity_id("wse")})
        with self._conn:
            self._conn.execute(
                "INSERT INTO enrichments (enrichment_id, webset_id, name, status, created_at, body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    created.id,
                    webset_id,
                    created.name,
                    created.status,
                    _utc_iso(_now()),
                    created.model_dump_json(),
                ),
            )
        return created

    def list_enrichments(self, webset_id: str) -> list[EnrichmentDef]:
        """Attached enrichment defs in attach order."""
        rows = self._conn.execute(
            "SELECT body FROM enrichments WHERE webset_id = ? ORDER BY rowid ASC", (webset_id,)
        ).fetchall()
        return [EnrichmentDef.model_validate_json(row[0]) for row in rows]

    def update_enrichment(self, webset_id: str, enrichment: EnrichmentDef) -> EnrichmentDef:
        """Replace an attached def's body (the backfill lifecycle settles here).

        The URL path's ``enrichment.id`` is authoritative; a missing id raises
        ``enrichment_not_found``.
        """
        row = self._conn.execute(
            "SELECT enrichment_id FROM enrichments WHERE webset_id = ? AND enrichment_id = ?",
            (webset_id, enrichment.id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(
                f"enrichment not found: {enrichment.id}", code="enrichment_not_found"
            )
        updated = enrichment.model_copy(update={"id": row[0]})
        with self._conn:
            self._conn.execute(
                "UPDATE enrichments SET name = ?, status = ?, body = ? WHERE enrichment_id = ?",
                (updated.name, updated.status, updated.model_dump_json(), updated.id),
            )
        return updated

    def remove_enrichment(self, webset_id: str, enrichment_id: str) -> None:
        """Detach a def; already-resolved item values stay on the item rows."""
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM enrichments WHERE webset_id = ? AND enrichment_id = ?",
                (webset_id, enrichment_id),
            )
        if cursor.rowcount == 0:
            raise WebsetStoreError(
                f"enrichment not found: {enrichment_id}", code="enrichment_not_found"
            )

    # -- monitors ---------------------------------------------------------

    def add_monitor(self, webset_id: str, monitor: WebsetMonitor) -> WebsetMonitor:
        """Record a refresh cadence (the tick driver executes it); id/date server-owned."""
        self.get_webset(webset_id)
        created = monitor.model_copy(
            update={
                "id": _new_entity_id("wsm"),
                "webset_id": webset_id,
                "created_at": monitor.created_at or _now(),
            }
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO webset_monitors (monitor_id, webset_id, created_at, body) "
                "VALUES (?, ?, ?, ?)",
                (
                    created.id,
                    webset_id,
                    _utc_iso(created.created_at or _now()),
                    created.model_dump_json(),
                ),
            )
        return created

    def get_monitor(self, webset_id: str, monitor_id: str) -> WebsetMonitor:
        """Load one monitor; a missing id raises ``monitor_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM webset_monitors WHERE webset_id = ? AND monitor_id = ?",
            (webset_id, monitor_id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"monitor not found: {monitor_id}", code="monitor_not_found")
        return WebsetMonitor.model_validate_json(row[0])

    def list_monitors(self, webset_id: str) -> list[WebsetMonitor]:
        """Monitors newest-created first (per-webset operator surface)."""
        rows = self._conn.execute(
            "SELECT body FROM webset_monitors WHERE webset_id = ? "
            "ORDER BY created_at DESC, monitor_id DESC",
            (webset_id,),
        ).fetchall()
        return [WebsetMonitor.model_validate_json(row[0]) for row in rows]

    def list_all_monitors(self) -> list[WebsetMonitor]:
        """Every monitor across every webset, oldest-created first.

        The tick driver's read: deterministic ``created_at ASC, monitor_id ASC``
        order so a pass processes rows in a stable sequence. An empty table is
        an empty list (no webset needs to exist for a reader); the monitor body
        carries its own ``webset_id``, so the caller needs no join.
        """
        rows = self._conn.execute(
            "SELECT body FROM webset_monitors ORDER BY created_at ASC, monitor_id ASC"
        ).fetchall()
        return [WebsetMonitor.model_validate_json(row[0]) for row in rows]

    def update_monitor(
        self, webset_id: str, monitor_id: str, monitor: WebsetMonitor
    ) -> WebsetMonitor:
        """Replace a monitor's body (the pause lifecycle writes here).

        The path's ids are authoritative (mirrors ``update_enrichment``): the row
        must exist for this webset, the rewritten body keeps the stored
        ``created_at`` when the incoming record carries none, and a missing row
        raises ``monitor_not_found`` — the same not-found semantics as
        :meth:`get_monitor`.
        """
        row = self._conn.execute(
            "SELECT created_at FROM webset_monitors WHERE webset_id = ? AND monitor_id = ?",
            (webset_id, monitor_id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"monitor not found: {monitor_id}", code="monitor_not_found")
        updated = monitor.model_copy(
            update={
                "id": monitor_id,
                "webset_id": webset_id,
                "created_at": monitor.created_at or _parse_utc(row[0]),
            }
        )
        with self._conn:
            self._conn.execute(
                "UPDATE webset_monitors SET body = ? WHERE monitor_id = ?",
                (updated.model_dump_json(), monitor_id),
            )
        return updated

    # -- webhooks ---------------------------------------------------------

    def add_webhook(self, webset_id: str, webhook: WebhookConfig) -> WebhookConfig:
        """Register a webhook under a fresh server-assigned id.

        The id is always minted here (never taken from the payload) because the
        model permits ``""`` and an empty id would collapse the
        ``(webhook_id, event_id)`` delivery-ledger key. ``created_at`` is
        server-assigned when the record carries none.
        """
        self.get_webset(webset_id)
        created = webhook.model_copy(
            update={"webhook_id": uuid.uuid4().hex, "created_at": webhook.created_at or _now()}
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO webhooks (webhook_id, webset_id, created_at, body) VALUES (?, ?, ?, ?)",
                (
                    created.webhook_id,
                    webset_id,
                    _utc_iso(created.created_at or _now()),
                    created.model_dump_json(),
                ),
            )
        return created

    def get_webhook(self, webset_id: str, webhook_id: str) -> WebhookConfig:
        """Load one webhook; a missing id raises ``webhook_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM webhooks WHERE webset_id = ? AND webhook_id = ?",
            (webset_id, webhook_id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"webhook not found: {webhook_id}", code="webhook_not_found")
        return WebhookConfig.model_validate_json(row[0])

    def list_webhooks(self, webset_id: str) -> list[WebhookConfig]:
        """Registered webhooks in creation order (the delivery fan-out reads this)."""
        rows = self._conn.execute(
            "SELECT body FROM webhooks WHERE webset_id = ? ORDER BY rowid ASC", (webset_id,)
        ).fetchall()
        return [WebhookConfig.model_validate_json(row[0]) for row in rows]

    def update_webhook(self, webset_id: str, webhook: WebhookConfig) -> WebhookConfig:
        """Replace a webhook record (secret rotation); the id must already exist.

        An empty ``webhook_id`` raises ``webhook_id_required`` and an unknown id
        raises ``webhook_not_found``; ``created_at`` is preserved when the
        incoming record carries none.
        """
        if not webhook.webhook_id:
            raise WebsetStoreError("webhook_id is required", code="webhook_id_required")
        row = self._conn.execute(
            "SELECT created_at FROM webhooks WHERE webset_id = ? AND webhook_id = ?",
            (webset_id, webhook.webhook_id),
        ).fetchone()
        if row is None:
            raise WebsetStoreError(
                f"webhook not found: {webhook.webhook_id}", code="webhook_not_found"
            )
        stored = webhook.model_copy(update={"created_at": webhook.created_at or _parse_utc(row[0])})
        with self._conn:
            self._conn.execute(
                "UPDATE webhooks SET body = ? WHERE webhook_id = ?",
                (stored.model_dump_json(), stored.webhook_id),
            )
        return stored

    # -- webhook delivery ledger ------------------------------------------

    def record_webhook_delivery(
        self,
        webhook_id: str,
        event_id: str,
        *,
        ok: bool,
        status_code: int | None = None,
        error: str | None = None,
    ) -> bool:
        """Record terminal delivery state, INSERT-or-ignore on the ``(webhook_id, event_id)`` key.

        Returns ``True`` when this call created the ledger row and ``False``
        when the pair was already recorded (a retry or a resumed delivery never
        double-records). The event row itself is never mutated. A new row keeps
        the re-delivery columns' defaults (``attempts = 0``, ``next_attempt_at
        NULL``) — a first-attempt failure is deliberately left unscheduled so
        the shared driver's re-delivery loop picks it up.
        """
        if not webhook_id or not event_id:
            raise WebsetStoreError(
                "webhook_id and event_id are required", code="invalid_webhook_delivery"
            )
        with self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO webhook_deliveries "
                "(webhook_id, event_id, ok, status_code, error, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (webhook_id, event_id, int(ok), status_code, error, _utc_iso(_now())),
            )
        return cursor.rowcount == 1

    def update_webhook_delivery(
        self,
        webhook_id: str,
        event_id: str,
        *,
        ok: bool,
        status_code: int | None,
        error: str | None,
        attempts: int,
        next_attempt_at: datetime | None,
    ) -> WebhookDelivery:
        """Rewrite an existing ledger row's outcome and re-delivery state.

        The #4226 re-delivery loop's write: every mutable field is replaced
        (``ok``, ``status_code``, ``error``, ``attempts``, ``next_attempt_at``)
        while ``recorded_at`` — the pair's first recorded moment — is kept. A
        missing pair (including an empty key) raises ``webhook_not_found``, the
        same not-found convention as :meth:`get_webhook`. Returns the updated
        row.
        """
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE webhook_deliveries SET ok = ?, status_code = ?, error = ?, "
                "attempts = ?, next_attempt_at = ? WHERE webhook_id = ? AND event_id = ?",
                (
                    int(ok),
                    status_code,
                    error,
                    attempts,
                    _utc_iso(next_attempt_at) if next_attempt_at is not None else None,
                    webhook_id,
                    event_id,
                ),
            )
        if cursor.rowcount == 0:
            raise WebsetStoreError(
                f"webhook delivery not found: {webhook_id}/{event_id}",
                code="webhook_not_found",
            )
        row = self.get_webhook_delivery(webhook_id, event_id)
        if row is None:  # pragma: no cover - row existed when the update matched
            raise WebsetStoreError(
                f"webhook delivery not found: {webhook_id}/{event_id}",
                code="webhook_not_found",
            )
        return row

    def get_webhook_delivery(self, webhook_id: str, event_id: str) -> WebhookDelivery | None:
        """Load one ledger row, or ``None`` when the pair was never recorded."""
        row = self._conn.execute(
            "SELECT webhook_id, event_id, ok, status_code, error, recorded_at, "
            "attempts, next_attempt_at FROM webhook_deliveries "
            "WHERE webhook_id = ? AND event_id = ?",
            (webhook_id, event_id),
        ).fetchone()
        return None if row is None else _delivery_from_row(row)

    def list_webhook_deliveries(self, webhook_id: str) -> list[WebhookDelivery]:
        """Ledger rows for one webhook in recording order."""
        rows = self._conn.execute(
            "SELECT webhook_id, event_id, ok, status_code, error, recorded_at, "
            "attempts, next_attempt_at FROM webhook_deliveries "
            "WHERE webhook_id = ? ORDER BY recorded_at ASC, event_id ASC",
            (webhook_id,),
        ).fetchall()
        return [_delivery_from_row(row) for row in rows]

    def list_due_webhook_deliveries(
        self, *, now: datetime, limit: int = 100
    ) -> list[WebhookDelivery]:
        """Failed ledger rows due for a re-delivery attempt, oldest-due first.

        A row is due when it is still failed (``ok = 0``), it has not exhausted
        the re-delivery attempts (``attempts < _MAX_DELIVERY_ATTEMPTS`` — an
        exhausted row keeps ``next_attempt_at NULL`` and is never offered
        again), and its scheduled moment has arrived (``next_attempt_at`` NULL
        for a never-scheduled first-attempt failure, or at/before ``now``).
        Order is deterministic — unscheduled rows first, then earliest scheduled
        moment, then ``recorded_at``, then the ledger key — so a pass processes
        a stable sequence. ``limit`` is clamped to 1..200 like the other
        selectors.
        """
        limit = _clamp_limit(limit)
        rows = self._conn.execute(
            "SELECT webhook_id, event_id, ok, status_code, error, recorded_at, "
            "attempts, next_attempt_at FROM webhook_deliveries "
            "WHERE ok = 0 AND attempts < ? AND "
            "(next_attempt_at IS NULL OR next_attempt_at <= ?) "
            "ORDER BY next_attempt_at ASC NULLS FIRST, recorded_at ASC, "
            "webhook_id ASC, event_id ASC LIMIT ?",
            (_MAX_DELIVERY_ATTEMPTS, _utc_iso(now), limit),
        ).fetchall()
        return [_delivery_from_row(row) for row in rows]

    # -- events -----------------------------------------------------------

    def append_event(self, event: WebsetEvent) -> WebsetEvent:
        """Append *event* idempotently and return the canonical stored row.

        The ``(webset_id, dedup_key)`` unique index makes this INSERT-or-ignore:
        a duplicate within one generation returns the first stored event, while
        a new generation (new ``search_id``) is a legitimately new row. Unknown
        kinds are rejected before any write (the event log stays append-only —
        there is no update or delete path).
        """
        self.get_webset(event.webset_id)
        if event.type not in _EVENT_KINDS:
            raise WebsetStoreError(f"unknown event kind: {event.type}", code="invalid_event_kind")
        created_at = event.created_at or _now()
        stored = event.model_copy(update={"created_at": created_at})
        dedup_key = _dedup_key(stored)
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO events "
                "(event_id, webset_id, kind, dedup_key, created_at, body) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    stored.id,
                    stored.webset_id,
                    stored.type,
                    dedup_key,
                    _utc_iso(created_at),
                    stored.model_dump_json(),
                ),
            )
        row = self._conn.execute(
            "SELECT body FROM events WHERE webset_id = ? AND dedup_key = ?",
            (stored.webset_id, dedup_key),
        ).fetchone()
        if row is None:
            row = self._conn.execute(
                "SELECT body FROM events WHERE event_id = ?", (stored.id,)
            ).fetchone()
        if row is None:  # pragma: no cover - insert failure with no conflicting row
            raise WebsetStoreError(f"event not stored: {stored.id}", code="event_not_stored")
        return WebsetEvent.model_validate_json(row[0])

    def get_event(self, event_id: str) -> WebsetEvent:
        """Load one stored event by id; a missing id raises ``event_not_found``.

        The re-delivery loop's read: the event body is the payload source for a
        re-sent delivery, so the row must be recoverable from the ledger's
        ``event_id`` alone.
        """
        row = self._conn.execute(
            "SELECT body FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            raise WebsetStoreError(f"event not found: {event_id}", code="event_not_found")
        return WebsetEvent.model_validate_json(row[0])

    def list_events(
        self,
        webset_id: str,
        *,
        after: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> tuple[list[WebsetEvent], str | None]:
        """Page the append-only event log oldest-first; *after* is the last seen id.

        The page returns events strictly newer than ``after``, oldest-first —
        the forward cursor a tailing client holds across polls. ``limit`` is
        clamped to 1..200; ``next_cursor`` is this page's last event id when
        more rows exist, else ``None``. An unknown ``after`` raises
        ``cursor_not_found``; a malformed one is rejected by the same code at
        this boundary (event ids carry no model pattern) instead of silently
        restarting or scanning for an arbitrary string.
        """
        limit = _clamp_limit(limit)
        fetch = limit + 1
        if after is None:
            rows = self._conn.execute(
                "SELECT body FROM events WHERE webset_id = ? ORDER BY rowid ASC LIMIT ?",
                (webset_id, fetch),
            ).fetchall()
        else:
            if _EVENT_ID_RE.fullmatch(after) is None:
                raise WebsetStoreError(f"cursor event not found: {after}", code="cursor_not_found")
            cursor_row = self._conn.execute(
                "SELECT rowid FROM events WHERE webset_id = ? AND event_id = ?",
                (webset_id, after),
            ).fetchone()
            if cursor_row is None:
                raise WebsetStoreError(f"cursor event not found: {after}", code="cursor_not_found")
            rows = self._conn.execute(
                "SELECT body FROM events WHERE webset_id = ? AND rowid > ? ORDER BY rowid ASC LIMIT ?",
                (webset_id, cursor_row[0], fetch),
            ).fetchall()
        page = [WebsetEvent.model_validate_json(row[0]) for row in rows[:limit]]
        next_cursor = page[-1].id if len(rows) > limit else None
        return page, next_cursor

    # -- internals --------------------------------------------------------

    def _write_webset(self, webset: Webset) -> None:
        self._conn.execute(
            "UPDATE websets SET body = ?, status = ?, workspace_id = ?, updated_at = ? "
            "WHERE webset_id = ?",
            (
                _base_document(webset),
                webset.status,
                webset.workspace_id,
                _utc_iso(webset.updated_at or _now()),
                webset.id,
            ),
        )

    def _settlement_blockers(self, webset_id: str) -> list[str]:
        """Reasons ``set_webset_idle`` must refuse: the spec's idle conjunction."""
        blockers: list[str] = []
        pending = self._conn.execute(
            "SELECT COUNT(*) FROM items WHERE webset_id = ? AND verification = 'pending'",
            (webset_id,),
        ).fetchone()
        if int(pending[0]):
            blockers.append(f"{pending[0]} item(s) pending verification")
        running = self._conn.execute(
            "SELECT COUNT(*) FROM searches WHERE webset_id = ? AND status = 'running'",
            (webset_id,),
        ).fetchone()
        if int(running[0]):
            blockers.append(f"{running[0]} search(es) still running")
        fields = [
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM enrichments WHERE webset_id = ? ORDER BY rowid ASC", (webset_id,)
            ).fetchall()
        ]
        if fields:
            missing: set[str] = set()
            rows = self._conn.execute(
                "SELECT body FROM items WHERE webset_id = ? AND verification = 'verified'",
                (webset_id,),
            ).fetchall()
            for (body,) in rows:
                item = WebsetItem.model_validate_json(body)
                missing.update(field for field in fields if field not in item.enrichments)
            if missing:
                blockers.append("enrichment field(s) still pending: " + ", ".join(sorted(missing)))
        return blockers


def get_store(db_path: str | None = None) -> WebsetStore:
    """Build a store for *db_path*, else the configured webset store home."""
    if db_path is None:
        db_path = os.environ.get(_ENV_DB_PATH) or _default_db_path()
    return WebsetStore(db_path=db_path)


def _default_db_path() -> str:
    workspace = os.environ.get(_ENV_WORKSPACE)
    base = Path(workspace) if workspace else Path()
    return str(base / _WORKSPACE_DB_DIR / _DB_FILENAME)


def _new_entity_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _base_document(webset: Webset) -> str:
    """Serialize the webset row body without the child collections (own tables)."""
    return webset.model_copy(update={"searches": [], "enrichments": []}).model_dump_json()


def _ensure_delivery_retry_columns(conn: sqlite3.Connection) -> None:
    """Add the #4226 re-delivery columns when a pre-existing DB predates them.

    ``CREATE TABLE IF NOT EXISTS`` cannot add columns to an existing table, so
    databases created before ``attempts``/``next_attempt_at`` are upgraded here
    (the ``monitors.store._ensure_secret_column`` precedent). Both guards make a
    re-open idempotent; any failure propagates out of ``__init__`` rather than
    leaving a store whose ledger is missing the columns.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(webhook_deliveries)")}
    if "attempts" not in columns:
        conn.execute(
            "ALTER TABLE webhook_deliveries ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
        )
    if "next_attempt_at" not in columns:
        conn.execute("ALTER TABLE webhook_deliveries ADD COLUMN next_attempt_at TEXT")


def _delivery_from_row(row: tuple[Any, ...]) -> WebhookDelivery:
    """Map a full eight-column ledger row (the store's canonical select order)."""
    return WebhookDelivery(
        webhook_id=row[0],
        event_id=row[1],
        ok=bool(row[2]),
        status_code=row[3],
        error=row[4],
        recorded_at=_parse_utc(row[5]),
        attempts=int(row[6]),
        next_attempt_at=_parse_utc(row[7]) if row[7] is not None else None,
    )


def _dedup_key(event: WebsetEvent) -> str:
    return _DEDUP_SEPARATOR.join(
        (event.type, event.search_id, event.item_id or "", event.field or "")
    )


def _check_transition(label: str, current: str, target: str) -> None:
    if current == target:
        return
    if target not in _TRANSITIONS[current]:
        raise WebsetStoreError(
            f"{label} cannot transition {current} -> {target}", code="transition_invalid"
        )


def _clamp_limit(limit: int) -> int:
    return max(_MIN_LIMIT, min(_MAX_LIMIT, limit))


def _now() -> datetime:
    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
