"""Phase C monitor store — SQLite persistence for watches and runs (#4065, Task 2).

Stdlib ``sqlite3`` only: this store is the single source of truth for monitor
schedules, run history, and the dedup memory the runner reads. Tables mirror the
spec's §3 storage note:

- ``watches (watch_id PK, body JSON, updated_at, workspace_id, secret)`` —
  ``body`` is the full ``Watch`` document so the model can evolve without
  migrations; ``updated_at`` orders listings and ``workspace_id`` backs the
  API's workspace filter as a real column (queryable columns stay real columns);
  ``secret`` is the nullable per-watch delivery secret (R8).
- ``runs (run_id PK, watch_id, status, trigger, started_at, finished_at, body)``
  with an index on ``(watch_id, started_at DESC)``. Runs are an append-only log
  and are retained after their watch is deleted; the raw ``results_all`` in the
  stored body is what :meth:`MonitorStore.seen_fingerprints` recomputes dedup
  memory from.

Connection and concurrency: each instance owns one connection opened in
``__init__``. ``sqlite3`` connections are thread-bound (``check_same_thread``
keeps its default), so an instance is single-threaded — construct one store per
thread or request (:func:`get_store` does). The file opens in WAL mode with a 5s
busy timeout so the HTTP process and the digiclaw tick process can share it; the
store adds no in-process locking of its own.

``watch_id`` is a 26-char Crockford-base32 ULID (48-bit ms timestamp + 80-bit
randomness) assigned by :meth:`MonitorStore.create_watch`; ``run_id`` values
arrive with the caller's :class:`MonitorRun`. Timestamps written to the
queryable columns are fixed-width UTC ISO strings so lexicographic order matches
chronological order (naive datetimes are treated as UTC). ``created_at`` and
``updated_at`` are server-assigned on create/update and cannot be changed by a
patch.

Dedup memory (R2/R7 contract): :meth:`MonitorStore.seen_fingerprints` merges the
stored raw ``results_all`` payloads of the newest ``limit_runs`` runs,
newest-first, into ``{normalize_url(url): result_fingerprint(result)}``. It
recomputes fingerprints with the public
:func:`digisearch.monitors.dedup.result_fingerprint` (never ad-hoc field
picking) and keys them with the landed Phase B ``normalize_url``, so the runner
can hand the map straight to :func:`digisearch.monitors.dedup.dedup_results`.

Delivery secrets (R8): the secret lives in the dedicated nullable ``secret``
column, never in the watch body, so :meth:`MonitorStore.get_watch` and
:meth:`MonitorStore.list_watches` (body-only selects) can never expose it.
The HTTP create/rotate path writes it with
:meth:`MonitorStore.set_delivery_secret`; the runner reads it with
:meth:`MonitorStore.get_delivery_secret`, where ``None`` means the watch has no
secret yet. Fresh databases get the column from the schema; databases created
before it existed are upgraded in ``__init__`` with a guarded ``ALTER TABLE``,
and a failed upgrade propagates rather than leaving a half-migrated store.

Store home: :func:`get_store` resolves explicit path →
``DIGISEARCH_MONITORS_DB`` → ``{DIGI_WORKSPACE}/.digisearch/monitors.sqlite3`` →
``./.digisearch/monitors.sqlite3`` (cwd fallback for host/test runs).
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from digisearch.monitors.dedup import result_fingerprint
from digisearch.monitors.models import MonitorRun, Watch
from digisearch.web_search.citation import normalize_url

__all__ = ["MonitorStore", "MonitorStoreError", "get_store", "new_ulid"]

_ENV_DB_PATH = "DIGISEARCH_MONITORS_DB"
_ENV_WORKSPACE = "DIGI_WORKSPACE"
_WORKSPACE_DB_DIR = ".digisearch"
_DB_FILENAME = "monitors.sqlite3"

_BUSY_TIMEOUT_MS = 5000
_MIN_LIMIT = 1
_MAX_LIMIT = 100
_DEFAULT_SEEN_RUNS = 10

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LENGTH = 26
_ULID_TIMESTAMP_BITS = 48
_ULID_RANDOM_BITS = 80

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    watch_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    workspace_id TEXT,
    secret TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_watch_started ON runs (watch_id, started_at DESC);
"""


class MonitorStoreError(RuntimeError):
    """Store failure carrying the stable API-facing ``code``.

    Codes raised today: ``watch_not_found``, ``run_not_found`` (also for an
    unknown pagination cursor), and ``run_exists`` (duplicate ``run_id``).
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def new_ulid() -> str:
    """Return a fresh 26-char Crockford-base32 ULID.

    Layout is the standard 48-bit millisecond timestamp followed by 80 bits of
    ``secrets`` randomness; ids sort lexicographically by creation millisecond
    (ids minted inside one millisecond share a prefix and are unordered among
    themselves). Also usable for monitor ``run_id`` values.
    """
    timestamp_ms = (time.time_ns() // 1_000_000) & ((1 << _ULID_TIMESTAMP_BITS) - 1)
    value = (timestamp_ms << _ULID_RANDOM_BITS) | secrets.randbits(_ULID_RANDOM_BITS)
    return _encode_ulid(value)


def _encode_ulid(value: int) -> str:
    chars = ["0"] * _ULID_LENGTH
    for index in range(_ULID_LENGTH - 1, -1, -1):
        chars[index] = _CROCKFORD32[value & 0x1F]
        value >>= 5
    return "".join(chars)


def _ensure_secret_column(conn: sqlite3.Connection) -> None:
    """Add the ``secret`` column when a pre-existing DB predates it.

    ``CREATE TABLE IF NOT EXISTS`` cannot add columns to an existing table, so
    databases created before the R8 column are upgraded here. Any failure
    (read-only file, lock) propagates out of ``__init__`` rather than leaving a
    store whose schema is missing the column.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(watches)")}
    if "secret" not in columns:
        conn.execute("ALTER TABLE watches ADD COLUMN secret TEXT")


class MonitorStore:
    """SQLite-backed watch/run store (single connection, single thread)."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        with self._conn:
            self._conn.executescript(_SCHEMA)
            _ensure_secret_column(self._conn)

    def create_watch(self, watch: Watch) -> Watch:
        """Persist *watch* with a server-assigned ``watch_id`` and timestamps."""
        now = datetime.now(UTC)
        created = watch.model_copy(
            update={"watch_id": new_ulid(), "created_at": now, "updated_at": now}
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO watches (watch_id, body, updated_at, workspace_id) VALUES (?, ?, ?, ?)",
                (created.watch_id, created.model_dump_json(), _utc_iso(now), created.workspace_id),
            )
        return created

    def list_watches(self, *, workspace_id: str | None = None) -> list[Watch]:
        """Watches ordered newest-updated first, optionally scoped by workspace."""
        query = "SELECT body FROM watches"
        params: tuple[Any, ...] = ()
        if workspace_id is not None:
            query += " WHERE workspace_id = ?"
            params = (workspace_id,)
        query += " ORDER BY updated_at DESC, watch_id DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [Watch.model_validate_json(row[0]) for row in rows]

    def get_watch(self, watch_id: str) -> Watch:
        """Load one watch; a missing id raises ``watch_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM watches WHERE watch_id = ?", (watch_id,)
        ).fetchone()
        if row is None:
            raise MonitorStoreError(f"watch not found: {watch_id}", code="watch_not_found")
        return Watch.model_validate_json(row[0])

    def update_watch(self, watch_id: str, patch: dict[str, Any]) -> Watch:
        """Apply a partial *patch*, re-validating the merged watch document.

        Merging is top-level: a nested object supplied in the patch replaces
        that whole nested object, so keys omitted from it fall back to their
        model defaults (e.g. ``{"dedup": {"match": "url"}}`` resets
        ``similarity_threshold`` to 0.9). ``watch_id`` and ``created_at`` are
        server-owned and cannot be changed by the patch; ``updated_at`` is
        bumped to the current UTC time.
        """
        current = self.get_watch(watch_id)
        merged = {**current.model_dump(mode="json"), **patch}
        now = datetime.now(UTC)
        updated = Watch.model_validate(merged).model_copy(
            update={
                "watch_id": current.watch_id,
                "created_at": current.created_at,
                "updated_at": now,
            }
        )
        with self._conn:
            self._conn.execute(
                "UPDATE watches SET body = ?, updated_at = ?, workspace_id = ? WHERE watch_id = ?",
                (updated.model_dump_json(), _utc_iso(now), updated.workspace_id, watch_id),
            )
        return updated

    def delete_watch(self, watch_id: str) -> None:
        """Delete a watch; its runs are retained. A missing id raises."""
        with self._conn:
            cursor = self._conn.execute("DELETE FROM watches WHERE watch_id = ?", (watch_id,))
        if cursor.rowcount == 0:
            raise MonitorStoreError(f"watch not found: {watch_id}", code="watch_not_found")

    def set_delivery_secret(self, watch_id: str, secret: str) -> None:
        """Store (or rotate) the per-watch delivery secret (R8).

        The secret is written to its own column, never into the watch body, so
        public watch payloads cannot expose it. A missing watch raises
        ``watch_not_found``.
        """
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE watches SET secret = ? WHERE watch_id = ?", (secret, watch_id)
            )
        if cursor.rowcount == 0:
            raise MonitorStoreError(f"watch not found: {watch_id}", code="watch_not_found")

    def get_delivery_secret(self, watch_id: str) -> str | None:
        """Return the stored secret; ``None`` when the watch has none yet.

        A missing watch raises ``watch_not_found``. ``None`` is a real state
        (watch created without a secret) and callers must treat it loudly, not
        as permission to skip delivery silently.
        """
        row = self._conn.execute(
            "SELECT secret FROM watches WHERE watch_id = ?", (watch_id,)
        ).fetchone()
        if row is None:
            raise MonitorStoreError(f"watch not found: {watch_id}", code="watch_not_found")
        return row[0]

    def append_run(self, run: MonitorRun) -> MonitorRun:
        """Persist *run* and return it unchanged.

        Appending does not require the watch row to exist: a turn that started
        before a watch delete still lands, and deleted watches keep their runs.
        A duplicate ``run_id`` raises ``run_exists``.
        """
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO runs "
                    "(run_id, watch_id, status, trigger, started_at, finished_at, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run.run_id,
                        run.watch_id,
                        run.status,
                        run.trigger,
                        _utc_iso(run.started_at),
                        _utc_iso(run.finished_at),
                        run.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise MonitorStoreError(f"run already exists: {run.run_id}", code="run_exists") from exc
        return run

    def get_run(self, watch_id: str, run_id: str) -> MonitorRun:
        """Load one run; a missing id raises ``run_not_found``."""
        row = self._conn.execute(
            "SELECT body FROM runs WHERE watch_id = ? AND run_id = ?", (watch_id, run_id)
        ).fetchone()
        if row is None:
            raise MonitorStoreError(f"run not found: {run_id}", code="run_not_found")
        return MonitorRun.model_validate_json(row[0])

    def list_runs(
        self,
        watch_id: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[MonitorRun], str | None]:
        """Page runs newest-first; *cursor* is the ``run_id`` to page after.

        ``limit`` is clamped to 1..100. The returned cursor is the last run id
        of the page when more rows exist, else ``None``. An unknown cursor
        raises ``run_not_found`` rather than silently restarting the page.
        """
        limit = max(_MIN_LIMIT, min(_MAX_LIMIT, limit))
        fetch = limit + 1
        if cursor is None:
            rows = self._conn.execute(
                "SELECT run_id, body FROM runs WHERE watch_id = ? "
                "ORDER BY started_at DESC, run_id DESC LIMIT ?",
                (watch_id, fetch),
            ).fetchall()
        else:
            cursor_row = self._conn.execute(
                "SELECT started_at FROM runs WHERE watch_id = ? AND run_id = ?",
                (watch_id, cursor),
            ).fetchone()
            if cursor_row is None:
                raise MonitorStoreError(f"cursor run not found: {cursor}", code="run_not_found")
            started_at = cursor_row[0]
            rows = self._conn.execute(
                "SELECT run_id, body FROM runs WHERE watch_id = ? AND "
                "(started_at < ? OR (started_at = ? AND run_id < ?)) "
                "ORDER BY started_at DESC, run_id DESC LIMIT ?",
                (watch_id, started_at, started_at, cursor, fetch),
            ).fetchall()
        page = [MonitorRun.model_validate_json(row[1]) for row in rows[:limit]]
        next_cursor = rows[limit - 1][0] if len(rows) > limit else None
        return page, next_cursor

    def seen_fingerprints(
        self, watch_id: str, *, limit_runs: int = _DEFAULT_SEEN_RUNS
    ) -> dict[str, str]:
        """Dedup memory for *watch_id*: normalized URL → fingerprint.

        Merges the raw ``results_all`` payloads of the newest ``limit_runs``
        stored runs, newest run first, so the most recent observation of a URL
        wins. Fingerprints come from the public
        :func:`digisearch.monitors.dedup.result_fingerprint`; keys come from the
        landed Phase B ``normalize_url`` — the exact contract
        :func:`digisearch.monitors.dedup.dedup_results` compares against.
        ``limit_runs <= 0`` and unknown watches yield an empty memory.
        """
        if limit_runs <= 0:
            return {}
        rows = self._conn.execute(
            "SELECT body FROM runs WHERE watch_id = ? "
            "ORDER BY started_at DESC, run_id DESC LIMIT ?",
            (watch_id, limit_runs),
        ).fetchall()
        seen: dict[str, str] = {}
        for (body,) in rows:
            run = MonitorRun.model_validate_json(body)
            for result in run.results_all:
                key = normalize_url(str(result.get("url") or ""))
                if key not in seen:
                    seen[key] = result_fingerprint(result)
        return seen


def get_store(db_path: str | None = None) -> MonitorStore:
    """Build a store for *db_path*, else the configured monitor store home."""
    if db_path is None:
        db_path = os.environ.get(_ENV_DB_PATH) or _default_db_path()
    return MonitorStore(db_path=db_path)


def _default_db_path() -> str:
    workspace = os.environ.get(_ENV_WORKSPACE)
    base = Path(workspace) if workspace else Path()
    return str(base / _WORKSPACE_DB_DIR / _DB_FILENAME)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")
