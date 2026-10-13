"""Unit tests for the local-only Supabase -> D1 migration tooling (DIG-2893).

No network, no live Supabase, no production D1: the dump is a synthetic
string written to ``tmp_path``, and both databases are local SQLite. The
target DDL is created by hand in the test -- real DDL arrives with tickets
2/3; these tests pin the splitter, the batcher, the importer, and the
row-count + checksum verifier.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.supabase_exit.d1_import import assert_local_target, import_batches, open_local_db
from scripts.supabase_exit.d1_verify import all_verified, table_checksum, verify_tables
from scripts.supabase_exit.migrate import main as migrate_main
from scripts.supabase_exit.pg_dump_split import (
    assert_local_dump_file,
    batch_inserts,
    split_dump_text,
)

pytestmark = pytest.mark.unit

DUMP = """\
-- synthetic pg_dump --column-inserts fixture (no real data)
SET statement_timeout = 0;
CREATE TABLE public.positions (id bigint, symbol text);

INSERT INTO public.positions (id, symbol) VALUES (1, 'UUP');
INSERT INTO public.positions (id, symbol) VALUES (2, 'DBO');
INSERT INTO public.positions
  (id, symbol) VALUES (3, 'XLV');
SELECT pg_catalog.setval('public.positions_id_seq', 3, true);
INSERT INTO public.ledger (id, note) VALUES (10, 'open');
"""


def _write_dump(tmp_path: Path) -> Path:
    dump = tmp_path / "snapshot.sql"
    dump.write_text(DUMP, encoding="utf-8")
    return dump


def test_split_groups_per_table_and_skips_ddl() -> None:
    split = split_dump_text(DUMP)
    assert sorted(split.tables) == ["ledger", "positions"]
    assert len(split.tables["positions"]) == 3  # incl. the multi-line INSERT
    assert len(split.tables["ledger"]) == 1
    assert split.skipped_lines > 0  # SET + CREATE + setval are not payload


def test_batching_never_mixes_tables() -> None:
    split = split_dump_text(DUMP)
    batches = batch_inserts(split.tables, batch_size=2)
    assert [(b.table, len(b.statements)) for b in batches] == [
        ("ledger", 1),
        ("positions", 2),
        ("positions", 1),
    ]
    with pytest.raises(ValueError):
        batch_inserts(split.tables, batch_size=0)


def test_local_only_guards_refuse_remote_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        assert_local_dump_file("https://example.com/snapshot.sql")
    with pytest.raises(ValueError):
        assert_local_target("https://example.com/db.sqlite")
    with pytest.raises(FileNotFoundError):
        assert_local_dump_file(tmp_path / "missing.sql")


def _target_with_ddl() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute('CREATE TABLE "positions" (id TEXT, symbol TEXT)')
    conn.execute('CREATE TABLE "ledger" (id TEXT, note TEXT)')
    return conn


def test_import_then_verify_all_green(tmp_path: Path) -> None:
    dump = _write_dump(tmp_path)
    db = str(tmp_path / "local.sqlite")
    # Operator applies the ticket-2/3 DDL first; the migrator never creates schema.
    ddl = sqlite3.connect(db)
    try:
        with ddl:
            ddl.execute('CREATE TABLE "positions" (id TEXT, symbol TEXT)')
            ddl.execute('CREATE TABLE "ledger" (id TEXT, note TEXT)')
    finally:
        ddl.close()
    assert migrate_main(["--dump", str(dump), "--db", db, "--batch-size", "2"]) == 0
    # Independent re-verification straight from the dump text.
    from scripts.supabase_exit.migrate import _replay_source

    split_tables = split_dump_text(DUMP).tables
    source = _replay_source(split_tables)
    try:
        target = open_local_db(db)
        try:
            results = verify_tables(source=source, target=target, tables=["ledger", "positions"])
            assert all_verified(results)
            assert all(r.rows_match and r.checksums_match for r in results)
            assert {r.table: r.source_rows for r in results} == {"ledger": 1, "positions": 3}
        finally:
            target.close()
    finally:
        source.close()


def test_verifier_catches_tampered_target() -> None:
    source = sqlite3.connect(":memory:")
    target = _target_with_ddl()
    try:
        source.execute('CREATE TABLE "positions" (id TEXT, symbol TEXT)')
        source.executemany('INSERT INTO "positions" VALUES (?, ?)', [("1", "UUP"), ("2", "DBO")])
        target.executemany('INSERT INTO "positions" VALUES (?, ?)', [("1", "UUP"), ("2", "DBO")])
        (ok,) = verify_tables(source=source, target=target, tables=["positions"])
        assert ok.verified
        with target:  # tamper: one row silently changed
            target.execute("UPDATE \"positions\" SET symbol = 'XXX' WHERE id = '2'")
        (tampered,) = verify_tables(source=source, target=target, tables=["positions"])
        assert tampered.rows_match  # same count ...
        assert not tampered.checksums_match  # ... but the checksum catches it
        assert not all_verified([tampered])
    finally:
        source.close()
        target.close()


def test_checksum_is_order_stable() -> None:
    a = sqlite3.connect(":memory:")
    b = sqlite3.connect(":memory:")
    try:
        for conn in (a, b):
            conn.execute('CREATE TABLE "t" (id TEXT, v TEXT)')
        a.executemany('INSERT INTO "t" VALUES (?, ?)', [("1", "x"), ("2", "y")])
        b.executemany(
            'INSERT INTO "t" VALUES (?, ?)', [("2", "y"), ("1", "x")]
        )  # insertion order differs
        assert table_checksum(a, "t") == table_checksum(b, "t")
    finally:
        a.close()
        b.close()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    dump = _write_dump(tmp_path)
    db = tmp_path / "local.sqlite"
    assert migrate_main(["--dump", str(dump), "--db", str(db), "--dry-run"]) == 0
    assert not db.exists()


def test_unknown_table_selection_fails(tmp_path: Path) -> None:
    dump = _write_dump(tmp_path)
    assert (
        migrate_main(["--dump", str(dump), "--db", str(tmp_path / "x.sqlite"), "--tables", "nope"])
        == 2
    )


def test_import_batches_rejects_empty() -> None:
    with pytest.raises(ValueError):
        import_batches(sqlite3.connect(":memory:"), [])
