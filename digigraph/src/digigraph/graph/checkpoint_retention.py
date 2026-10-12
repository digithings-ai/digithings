"""Retention for the file-backed (sqlite) LangGraph checkpointer (DIG-2896).

A port of ``public.prune_langgraph_checkpoints`` from
``digiquant/supabase/migrations/061_checkpointer_retention.sql`` to the two tables
``SqliteSaver`` actually creates. Postgres needed two daily ``pg_cron`` jobs (prune
05:20 UTC, ``VACUUM`` 05:50 UTC) because nothing in ``PostgresSaver`` deletes thread
state. The sqlite file is a different animal: ``SqliteSaver`` stores blobs inline in
``checkpoints.checkpoint`` and ``writes.value`` with no separate blob table, so a
thread-scoped delete reaches every byte the old migration had to reach in three
tables, and SQLite returns the freed pages only when it is VACUUMed. Neither thing
happens on its own, so this module does both and the cron pair can go away.

Three properties are carried over from 061 unchanged, because each is load-bearing:

* ``retain_days`` may never be below 1. ``pipeline-olympus.yml`` exposes
  ``resume_run_id``, so a thread older than the window can still be resumed.
* A thread is stale only when **every** checkpoint it holds predates the window.
  That is the ``HAVING max(checkpoint->>'ts')`` rule from the migration: an in-flight
  or freshly-resumed run must never become eligible, not even at ``retain_days = 1``.
* An unreadable timestamp is treated as fresh (retained). The migration relied on a
  ``NULL`` failing the ``<`` comparison; here the failure is decoding, and the same
  conservative answer follows.

What is deliberately *not* here: reading or writing the file to object storage, and
any change to the default backend. Postgres stays the default and stays live, so a
deployment that never sets ``DIGI_CHECKPOINTER`` is unaffected.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

LOGGER = logging.getLogger(__name__)

#: Mirrors ``retain_days integer DEFAULT 14`` in 061_checkpointer_retention.sql.
DEFAULT_RETAIN_DAYS = 14

#: Env var that overrides the window for the sqlite backend.
RETAIN_DAYS_ENV = "DIGI_CHECKPOINTER_SQLITE_RETAIN_DAYS"

# ``DELETE ... WHERE thread_id IN (...)`` takes one parameter per thread. Chunk so a
# large backlog cannot exceed the driver's bound variable limit on an older build.
_DELETE_BATCH = 500


class RetentionConfigError(ValueError):
    """The requested retention window cannot be honoured."""


@dataclass(frozen=True)
class RetentionResult:
    """Outcome of one retention pass.

    ``vacuumed`` is False both when the caller did not ask for a VACUUM and when
    nothing was pruned -- there is nothing to reclaim in the second case, and
    VACUUM rewrites the whole file.
    """

    threads_pruned: int = 0
    checkpoints_deleted: int = 0
    writes_deleted: int = 0
    vacuumed: bool = False

    @property
    def pruned_any(self) -> bool:
        return self.threads_pruned > 0


def retain_days_from_env(env: Mapping[str, str] | None = None) -> int:
    """Return ``DIGI_CHECKPOINTER_SQLITE_RETAIN_DAYS`` as a usable int.

    An unset or blank value means "not configured" and yields the migration's
    default. Anything present but unusable raises :class:`RetentionConfigError`, so
    the caller can complain loudly and fall back to the default rather than
    quietly leaving the file unpruned forever.
    """
    source = os.environ if env is None else env
    raw = (source.get(RETAIN_DAYS_ENV) or "").strip()
    if not raw:
        return DEFAULT_RETAIN_DAYS
    try:
        value = int(raw)
    except ValueError as exc:
        raise RetentionConfigError(f"{RETAIN_DAYS_ENV}={raw!r} is not an integer") from exc
    if value < 1:
        raise RetentionConfigError(
            f"{RETAIN_DAYS_ENV}={raw!r} is below the 1-day floor: an older thread is "
            "still resumable (resume_run_id), so retention can never be zero"
        )
    return value


def _default_serde() -> Any:
    """Return LangGraph's own serializer, or ``None`` if it is not importable.

    ``None`` is not an error: :func:`_checkpoint_ts` falls back to decoding the blob
    directly, which is all the retention pass needs from the checkpoint.
    """
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        return JsonPlusSerializer()
    except ImportError:  # pragma: no cover - langgraph ships this serde
        return None


def _decode(serde: Any, type_: Any, blob: Any) -> Any:
    """Return the checkpoint object stored at *blob*, or ``None`` if unreadable."""
    if blob is None:
        return None
    if serde is not None:
        try:
            return serde.loads_typed((type_, blob))
        except Exception:  # noqa: BLE001 - a bad row must not abort the prune
            LOGGER.debug("checkpoint serializer could not read a %s blob", type_, exc_info=True)
    # No usable serializer: decode the two wire formats LangGraph emits directly.
    # ormsgpack is langgraph's own dependency, so it is present wherever a saver is.
    try:
        if type_ == "msgpack":
            import ormsgpack

            return ormsgpack.unpackb(blob)
        if type_ == "json":
            return json.loads(blob)
    except Exception:  # noqa: BLE001 - unreadable rows are retained, never fatal
        LOGGER.debug("could not decode a %s checkpoint blob", type_, exc_info=True)
    return None


def _parse_ts(raw: Any) -> datetime | None:
    """Parse a checkpoint ``ts`` into an aware datetime, or ``None`` if unusable."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A naive timestamp is read as UTC so the comparison against the cutoff is
    # total. LangGraph writes aware values; this only keeps a hand-written row
    # from being treated as unreadable (and therefore as fresh forever).
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _checkpoint_ts(serde: Any, type_: Any, blob: Any) -> datetime | None:
    """Return the ``ts`` of one stored checkpoint, or ``None`` when unreadable.

    The timestamp lives **inside the checkpoint blob**, not in the ``metadata``
    column: ``put()`` serialises ``get_checkpoint_metadata(config, metadata)`` to
    ``metadata`` and that helper only merges config metadata, so ``metadata`` carries
    ``source``/``step``/``writes`` and never ``ts``. Reading ``metadata`` instead would
    return ``None`` for every row, every thread would look fresh, and the prune would
    pass while deleting nothing.
    """
    checkpoint = _decode(serde, type_, blob)
    if not isinstance(checkpoint, Mapping):
        return None
    return _parse_ts(checkpoint.get("ts"))


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _stale_thread_ids(
    conn: sqlite3.Connection, *, cutoff: datetime, serde: Any
) -> list[str]:
    """Return the thread ids whose every checkpoint predates *cutoff*.

    Port of ``GROUP BY c.thread_id HAVING max(checkpoint->>'ts') < cutoff``. The rows
    are read one at a time so a single pass decides each thread: one checkpoint at or
    after the cutoff marks the thread fresh and every later row for it is skipped, and
    a thread is only reported stale once nothing has rescued it. That makes the answer
    independent of the order rows happen to arrive in.
    """
    fresh: set[str] = set()
    stale: set[str] = set()
    for thread_id, type_, blob in conn.execute(
        "SELECT thread_id, type, checkpoint FROM checkpoints"
    ):
        if thread_id in fresh:
            continue
        ts = _checkpoint_ts(serde, type_, blob)
        if ts is None or ts >= cutoff:
            fresh.add(thread_id)
            stale.discard(thread_id)
        else:
            stale.add(thread_id)
    return sorted(stale - fresh)


def _batched(values: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def prune_checkpoints(
    conn: sqlite3.Connection,
    *,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    now: datetime | None = None,
    serde: Any = None,
) -> RetentionResult:
    """Delete every checkpoint of every thread older than *retain_days*.

    Children go before parents, as in the migration: ``writes`` first, then
    ``checkpoints``. Deletion is scoped by ``thread_id`` alone and spans every
    ``checkpoint_ns``, because a thread id that has aged out is aged out. The deletes
    are committed before returning so a following VACUUM is not inside a transaction.
    """
    if isinstance(retain_days, bool) or not isinstance(retain_days, int):
        raise RetentionConfigError(f"retain_days must be an int, got {retain_days!r}")
    if retain_days < 1:
        raise RetentionConfigError(
            "retain_days must be at least 1: an older thread is still resumable "
            "(resume_run_id), so retention can never be zero"
        )
    if conn is None:
        raise RetentionConfigError("a sqlite connection is required")

    now = now or datetime.now(timezone.utc)
    # ``from_conn_string`` does not run ``setup()``, so a file that has never been
    # written to has no tables at all. Nothing to prune is a success, not an error.
    if not _has_table(conn, "checkpoints"):
        return RetentionResult()

    cutoff = now - timedelta(days=retain_days)
    stale = _stale_thread_ids(conn, cutoff=cutoff, serde=serde if serde is not None else _default_serde())
    if not stale:
        return RetentionResult()

    writes_deleted = 0
    checkpoints_deleted = 0
    for batch in _batched(stale, _DELETE_BATCH):
        placeholders = ",".join("?" * len(batch))
        # writes first: a surviving write row references a checkpoint that is gone.
        writes_deleted += conn.execute(
            "DELETE FROM writes WHERE thread_id IN (" + placeholders + ")", batch
        ).rowcount
        checkpoints_deleted += conn.execute(
            "DELETE FROM checkpoints WHERE thread_id IN (" + placeholders + ")", batch
        ).rowcount
    conn.commit()
    return RetentionResult(
        threads_pruned=len(stale),
        checkpoints_deleted=checkpoints_deleted,
        writes_deleted=writes_deleted,
    )


def vacuum_checkpoints(conn: sqlite3.Connection) -> None:
    """Reclaim the pages freed by a prune.

    Plain ``VACUUM``, never ``VACUUM FULL``: SQLite's FULL variant needs a table lock
    it cannot take while other connections hold the file open, and buys nothing here
    that the default does not. ``ANALYZE`` follows because the migration's job was
    ``VACUUM (ANALYZE)``; SQLite spells that as two statements.
    """
    # VACUUM cannot run inside a transaction; commit whatever the caller left open.
    conn.commit()
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.commit()


def apply_retention(
    conn: sqlite3.Connection,
    *,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    now: datetime | None = None,
    vacuum: bool = True,
    serde: Any = None,
) -> RetentionResult:
    """Prune, then VACUUM only if something was actually removed.

    Gating the VACUUM on a real delete keeps a no-op pass cheap: it rewrites the whole
    file, and a healthy checkpoint file has nothing to give back.
    """
    result = prune_checkpoints(conn, retain_days=retain_days, now=now, serde=serde)
    if vacuum and result.pruned_any:
        vacuum_checkpoints(conn)
        result = replace(result, vacuumed=True)
    return result


def describe(result: RetentionResult) -> str:
    """One-line summary for a log message."""
    return (
        f"{result.threads_pruned} thread(s), {result.checkpoints_deleted} checkpoint(s), "
        f"{result.writes_deleted} write(s){', vacuumed' if result.vacuumed else ''}"
    )


__all__: Iterable[str] = (
    "DEFAULT_RETAIN_DAYS",
    "RETAIN_DAYS_ENV",
    "RetentionConfigError",
    "RetentionResult",
    "apply_retention",
    "describe",
    "prune_checkpoints",
    "retain_days_from_env",
    "vacuum_checkpoints",
)