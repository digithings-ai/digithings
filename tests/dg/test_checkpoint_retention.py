"""Retention for the file-backed (sqlite) LangGraph checkpointer (DIG-2896).

Ports ``public.prune_langgraph_checkpoints`` from
``digiquant/supabase/migrations/061_checkpointer_retention.sql`` to the two tables
``SqliteSaver`` actually creates, so the two daily ``pg_cron`` jobs (prune 05:20,
vacuum 05:50) have a replacement that lives with the file they maintain.

Fixtures write through the real ``SqliteSaver`` wherever the row shape matters, so a
schema or serialization change upstream breaks these tests instead of silently
turning the pruner into a no-op.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from digigraph.graph import checkpoint_retention as cr

NOW = datetime(2026, 10, 12, 6, 0, 0, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=40)).isoformat()
FRESH = (NOW - timedelta(hours=1)).isoformat()


def _saver(path: str) -> tuple[Any, sqlite3.Connection]:
    """Return an entered ``SqliteSaver`` over *path* plus its raw connection.

    ``from_conn_string`` is a ``@contextmanager`` generator that wraps the connection in
    ``closing(...)``. Let the context manager be garbage-collected and the generator is
    closed, ``conn.close()`` runs, and every later statement on the connection raises
    ``ProgrammingError: Cannot operate on a closed database``. So the holder is bound to
    the saver here for the same reason ``graph.py`` keeps ``_cm_holders``.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    cm = SqliteSaver.from_conn_string(path)
    saver = cm.__enter__()
    saver.setup()
    saver._test_cm_holder = cm
    return saver, saver.conn


def _put(saver: Any, thread_id: str, ts: str, *, ns: str = "", point: int = 0) -> None:
    """Write one checkpoint the way LangGraph does, with an explicit ``ts``."""
    saver.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ns}},
        {
            "ts": ts,
            "id": f"{thread_id}-{ns}-{point}",
            "channel_values": {"k": "v"},
            "channel_versions": {"k": "1"},
            "versions_seen": {"k": set()},
        },
        {"source": "input", "step": point, "writes": {}},
        {},
    )


def _counts(conn: sqlite3.Connection) -> tuple[int, int]:
    checkpoints = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    writes = conn.execute("SELECT COUNT(*) FROM writes").fetchone()[0]
    return checkpoints, writes


def _threads(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT thread_id FROM checkpoints")}


# --------------------------------------------------------------------------- guard


@pytest.mark.unit
def test_retain_days_below_one_is_refused(tmp_path) -> None:
    """061 RAISEs on ``retain_days < 1``; a resume window of zero strands every run.

    The connection is a real one on purpose. ``prune_checkpoints`` refuses a missing
    connection with the *same* exception type, so with ``conn=None`` a floor guard that
    had been weakened to ``< 0`` would still raise -- on the wrong guard -- and the test
    would stay green. A live connection means only the floor guard can fire, and the
    match on the message says which one it was.
    """
    _, conn = _saver(str(tmp_path / "ckpt.sqlite"))

    for window in (0, -3):
        with pytest.raises(cr.RetentionConfigError, match="at least 1"):
            cr.prune_checkpoints(conn, retain_days=window, now=NOW)


@pytest.mark.unit
def test_a_missing_connection_is_refused_separately() -> None:
    """The missing-connection guard is distinct, and must not masquerade as the floor."""
    with pytest.raises(cr.RetentionConfigError, match="connection is required"):
        cr.prune_checkpoints(None, retain_days=14, now=NOW)


@pytest.mark.unit
def test_default_retain_days_matches_the_migration() -> None:
    assert cr.DEFAULT_RETAIN_DAYS == 14


# ----------------------------------------------------------------------- the prune


@pytest.mark.unit
def test_stale_thread_is_deleted_from_both_tables(tmp_path) -> None:
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)
    _put(saver, "new", FRESH)
    assert _counts(conn) == (2, 0)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 1
    assert result.checkpoints_deleted == 1
    assert _threads(conn) == {"new"}
    assert _counts(conn) == (1, 0)


@pytest.mark.unit
def test_stale_thread_writes_are_deleted_before_its_checkpoints(tmp_path) -> None:
    """061 deletes children first; a leftover ``writes`` row is unreachable state."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    cfg = {"configurable": {"thread_id": "old", "checkpoint_ns": ""}}
    saved = saver.put(
        cfg,
        {
            "ts": OLD,
            "id": "cp-1",
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        },
        {"source": "input", "step": 0, "writes": {}},
        {},
    )
    task_id = "task-1"
    saver.put_writes(saved, [("chan", "value")], task_id)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.writes_deleted == 1
    assert result.checkpoints_deleted == 1
    assert _counts(conn) == (0, 0)


@pytest.mark.unit
def test_fresh_thread_survives_even_at_the_narrowest_window(tmp_path) -> None:
    """The control for the delete arm: the same call that removes old state keeps new."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "new", FRESH)

    result = cr.prune_checkpoints(conn, retain_days=1, now=NOW)

    assert result.threads_pruned == 0
    assert result.checkpoints_deleted == 0
    assert _threads(conn) == {"new"}


@pytest.mark.unit
def test_thread_is_stale_only_when_its_NEWEST_checkpoint_is_old(tmp_path) -> None:
    """Ports 061's ``HAVING max(ts)`` — one fresh checkpoint in a thread saves it all."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "mixed", OLD, point=1)
    _put(saver, "mixed", FRESH, point=2)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 0
    assert _threads(conn) == {"mixed"}


@pytest.mark.unit
def test_a_fresh_checkpoint_still_saves_its_thread_when_it_is_the_older_row(tmp_path) -> None:
    """Staleness must not depend on insertion order -- kills a ``first row wins`` prune."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "mixed", FRESH, point=1)
    _put(saver, "mixed", OLD, point=2)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 0
    assert _threads(conn) == {"mixed"}


@pytest.mark.unit
def test_all_namespaces_of_a_stale_thread_are_removed(tmp_path) -> None:
    """061 deletes by ``thread_id`` alone; ``checkpoint_ns`` must not scope the delete."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD, ns="")
    _put(saver, "old", OLD, ns="sub-agent")
    _put(saver, "new", FRESH)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 1
    assert result.checkpoints_deleted == 2
    assert _threads(conn) == {"new"}


@pytest.mark.unit
def test_thread_with_an_unreadable_timestamp_is_retained(tmp_path) -> None:
    """061's fail-safe: an unreadable ``ts`` fails the ``<`` comparison and is retained.

    ``dead`` is the control for the delete arm and ``good`` the control for the
    keep arm, so a pruner that treated unreadable as stale would show up as
    ``threads_pruned == 2`` with ``garbled`` missing -- not as a silent pass.
    """
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "dead", OLD)
    _put(saver, "good", FRESH)
    conn.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata)"
        " VALUES ('garbled', '', 'c1', 'msgpack', ?, ?)",
        (b"\x80\x80", b'{"source":"input"}'),
    )

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 1
    assert _threads(conn) == {"good", "garbled"}


@pytest.mark.unit
def test_null_checkpoint_blob_is_retained(tmp_path) -> None:
    """Same fail-safe with no ``checkpoint`` blob at all rather than a bad one."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "dead", OLD)
    _put(saver, "good", FRESH)
    conn.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, metadata)"
        " VALUES ('empty', '', 'c1', NULL)"
    )

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert _threads(conn) == {"good", "empty"}
    assert result.threads_pruned == 1


@pytest.mark.unit
def test_naive_timestamp_is_read_as_utc(tmp_path) -> None:
    """LangGraph writes an aware ts, but a naive one must not crash the prune."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "naive", (NOW - timedelta(days=40)).replace(tzinfo=None).isoformat())
    _put(saver, "new", FRESH)

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 1
    assert _threads(conn) == {"new"}


@pytest.mark.unit
def test_timestamp_extraction_reads_the_real_msgpack_blob(tmp_path) -> None:
    """Non-vacuity control: the ts comes from the checkpoint blob, not from a guess.

    If ``_checkpoint_ts`` stopped decoding the blob it would return ``None`` for every
    row and the prune would silently retain everything -- still "safe", still green.
    """
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)
    row = conn.execute("SELECT type, checkpoint FROM checkpoints").fetchone()
    assert row[0] == "msgpack"
    assert cr._checkpoint_ts(cr._default_serde(), row[0], row[1]) == datetime.fromisoformat(OLD)
    # Without a serde every row is unreadable, so 061's fail-safe keeps it all --
    # the same green outcome, reached by not being able to see anything.
    assert cr._checkpoint_ts(None, row[0], row[1]) is None

    cr.prune_checkpoints(conn, retain_days=14, now=NOW)
    assert _counts(conn) == (0, 0)


@pytest.mark.unit
def test_json_typed_checkpoint_row_is_read(tmp_path) -> None:
    """A row stored as ``json`` rather than ``msgpack`` must still be understood."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "new", FRESH)
    conn.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata)"
        " VALUES ('oldjson', '', 'c1', 'json', ?, '{}')",
        (('{"ts": "%s", "id": "x"}' % OLD).encode(),),
    )

    result = cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    assert result.threads_pruned == 1
    assert _threads(conn) == {"new"}


# ------------------------------------------------------------------- missing tables


@pytest.mark.unit
def test_a_brand_new_file_is_a_noop(tmp_path) -> None:
    """``from_conn_string`` does not run ``setup()``; retention must not create or fail."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    cm = SqliteSaver.from_conn_string(str(tmp_path / "fresh.sqlite"))
    saver = cm.__enter__()
    # Hold the context manager: otherwise it is garbage-collected mid-test, its
    # ``closing(sqlite3.connect(...))`` runs and every later call sees a closed
    # database -- the same reason graph.py keeps ``_cm_holders``.
    saver._test_cm_holder = cm
    tables = saver.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[
        0
    ]

    result = cr.prune_checkpoints(saver.conn, retain_days=14, now=NOW)

    assert tables == 0
    assert result.threads_pruned == 0
    assert result.vacuumed is False


# ------------------------------------------------------------------------- vacuum


class _RecordingConn:
    """Proxy that records every statement, so a VACUUM variant can be asserted on."""

    def __init__(self, inner: sqlite3.Connection) -> None:
        self._inner = inner
        self.statements: list[str] = []

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        self.statements.append(" ".join(sql.split()))
        return self._inner.execute(sql, *args)

    def commit(self) -> None:
        self._inner.commit()


@pytest.mark.unit
def test_vacuum_is_plain_never_full(tmp_path) -> None:
    """061 refuses ``VACUUM FULL``: it takes an exclusive lock to reclaim nothing."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)
    recorder = _RecordingConn(conn)

    result = cr.apply_retention(recorder, retain_days=14, now=NOW)

    vacuum_sql = [s for s in recorder.statements if "VACUUM" in s.upper()]
    assert vacuum_sql == ["VACUUM"]
    assert not any("FULL" in s.upper() for s in vacuum_sql)
    assert result.vacuumed is True


@pytest.mark.unit
def test_prune_checkpoints_commits_on_its_own(tmp_path) -> None:
    """``prune_checkpoints`` is public, so it must not depend on a later VACUUM to commit.

    ``apply_retention`` would hide the bug: ``vacuum_checkpoints`` opens with its own
    ``commit()``, which commits the prune on the way past. And ``sqlite3`` rolls back on
    ``close()``, so a caller that prunes and exits without vacuuming would silently lose
    every delete. This calls the pruner alone and reads the file from outside.
    """
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)

    cr.prune_checkpoints(conn, retain_days=14, now=NOW)

    other = sqlite3.connect(str(tmp_path / "ckpt.sqlite"))
    assert other.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    other.close()


@pytest.mark.unit
def test_vacuum_runs_after_the_delete_commits(tmp_path) -> None:
    """VACUUM cannot run inside a transaction, so the deletes must commit first."""
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)

    cr.apply_retention(conn, retain_days=14, now=NOW)

    # A committed delete is visible to an independent connection only after commit.
    other = sqlite3.connect(str(tmp_path / "ckpt.sqlite"))
    assert other.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    other.close()


@pytest.mark.unit
def test_a_prune_that_deletes_nothing_does_not_vacuum(tmp_path) -> None:
    """VACUUM rewrites the whole file, so it is gated on a real delete.

    Nothing to prune is the common case on every start with a live workload. Paying a
    full-file rewrite each time to reclaim nothing is the cost the gate avoids.
    """
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "live", FRESH)
    recorder = _RecordingConn(conn)

    result = cr.apply_retention(recorder, retain_days=14, now=NOW)

    assert result.threads_pruned == 0
    assert result.vacuumed is False
    assert not any("VACUUM" in s.upper() for s in recorder.statements)
    assert _counts(conn) == (1, 0)


@pytest.mark.unit
def test_vacuum_is_skipped_when_not_asked(tmp_path) -> None:
    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", OLD)

    result = cr.apply_retention(conn, retain_days=14, now=NOW, vacuum=False)

    assert result.threads_pruned == 1
    assert result.vacuumed is False


# -------------------------------------------------------------------- env plumbing


@pytest.mark.unit
def test_retain_days_from_env_defaults_to_the_migration() -> None:
    assert cr.retain_days_from_env({}) == cr.DEFAULT_RETAIN_DAYS


@pytest.mark.unit
def test_retain_days_from_env_reads_the_value() -> None:
    assert cr.retain_days_from_env({cr.RETAIN_DAYS_ENV: "7"}) == 7


@pytest.mark.unit
def test_blank_retain_days_env_means_unset() -> None:
    assert cr.retain_days_from_env({cr.RETAIN_DAYS_ENV: "   "}) == cr.DEFAULT_RETAIN_DAYS


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["0", "-1", "abc", "1.5"])
def test_retain_days_from_env_rejects_anything_unusable(raw: str) -> None:
    with pytest.raises(cr.RetentionConfigError):
        cr.retain_days_from_env({cr.RETAIN_DAYS_ENV: raw})


# --------------------------------------------------------------------- graph wiring


@pytest.mark.unit
def test_get_checkpointer_runs_retention_when_it_builds_the_saver(tmp_path, monkeypatch) -> None:
    """The CALL SITE is the deliverable: building the saver was already shipped.

    The old thread is written *before* get_checkpointer() is called, so it can only be
    gone afterwards if the factory itself invoked retention. Asserting that the helper
    works instead would leave this file green with the call deleted.
    """
    from digigraph.graph import graph as graph_module
    from digigraph.graph.mcp_checkpoint_redact import unwrap_checkpointer
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = str(tmp_path / "wired.sqlite")
    seeded, seed_conn = _saver(path)
    _put(seeded, "old", OLD)
    _put(seeded, "live", FRESH)
    assert _threads(seed_conn) == {"live", "old"}

    monkeypatch.setenv("DIGI_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("DIGI_CHECKPOINTER_SQLITE_URI", path)
    monkeypatch.setenv(cr.RETAIN_DAYS_ENV, "1")
    monkeypatch.setattr(graph_module, "_checkpointer_instance", None)
    monkeypatch.setattr(graph_module, "_cm_holders", [])

    inner = unwrap_checkpointer(graph_module.get_checkpointer())

    assert isinstance(inner, SqliteSaver)
    # retain_days=1, so the 40-day-old thread is stale and the 1-hour-old one is not.
    assert _threads(inner.conn) == {"live"}


@pytest.mark.unit
def test_apply_sqlite_retention_returns_what_it_deleted(tmp_path, monkeypatch) -> None:
    """The helper reports its own counts; get_checkpointer() ignores the return."""
    from digigraph.graph import graph as graph_module

    saver, conn = _saver(str(tmp_path / "helper.sqlite"))
    _put(saver, "old", OLD)
    _put(saver, "live", FRESH)
    monkeypatch.setenv(cr.RETAIN_DAYS_ENV, "1")

    result = graph_module._apply_sqlite_retention(saver)

    assert result is not None
    assert result.threads_pruned == 1
    assert _threads(conn) == {"live"}


@pytest.mark.unit
def test_retention_failure_never_stops_process_start(caplog) -> None:
    """A broken retention pass must be logged, not raised: it runs during startup."""
    from digigraph.graph import graph as graph_module

    class _NoConn:
        conn = None

    with caplog.at_level("ERROR"):
        assert graph_module._apply_sqlite_retention(_NoConn()) is None
    assert "retention" in caplog.text.lower()


@pytest.mark.unit
def test_unusable_retain_days_env_falls_back_to_the_default(tmp_path, monkeypatch) -> None:
    """A typo must not disable retention -- that would grow the file without bound."""
    from digigraph.graph import graph as graph_module

    saver, conn = _saver(str(tmp_path / "ckpt.sqlite"))
    _put(saver, "old", (NOW - timedelta(days=30)).isoformat())
    _put(saver, "newer", (NOW - timedelta(days=1)).isoformat())
    monkeypatch.setenv(cr.RETAIN_DAYS_ENV, "0")

    result = graph_module._apply_sqlite_retention(saver)

    assert result is not None
    # Default is 14 days: the 30-day-old thread goes, the 1-day-old thread stays.
    assert result.threads_pruned == 1
    assert _threads(conn) == {"newer"}
