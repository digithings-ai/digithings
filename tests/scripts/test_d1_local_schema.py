#!/usr/bin/env python3
"""The generated D1 (SQLite) schema must APPLY, not merely parse (DIG-2891).

These tests run the real migration files through the real sqlite3 binary, so a
DDL statement SQLite cannot execute fails here rather than at `wrangler dev`.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
D1_LOCAL = REPO / "apps" / "dashboard-api" / "d1-local"
MIGRATIONS = D1_LOCAL / "migrations"
GENERATOR = D1_LOCAL / "generate_d1_schema.py"

# The distinct core tables the PG migrations at github/develop declare.
EXPECTED_TABLES = 111

SQLITE3 = shutil.which("sqlite3") or "/usr/bin/sqlite3"


def migration_files() -> list[Path]:
    return sorted(p for p in MIGRATIONS.glob("*.sql"))


def test_migrations_exist():
    files = migration_files()
    assert files, "no D1 migration files under %s" % MIGRATIONS
    assert (MIGRATIONS / "0001_schema.sql").is_file()


def test_generator_ships_next_to_its_output():
    # The emitted header names this script; a header pointing at a missing file
    # is a false claim, so its presence is part of the contract.
    assert GENERATOR.is_file(), "generator named by the emitted header is missing"
    text = GENERATOR.read_text(encoding="utf-8")
    for word in ("def fetch_corpus", "def main", "def map_type"):
        assert word in text, "generator lost %r during assembly" % word


def test_every_migration_applies_in_order(tmp_path):
    """Apply the whole stream to one fresh database; SQLite must accept all of it."""
    if not Path(SQLITE3).exists():
        pytest.skip("sqlite3 binary not available at %s" % SQLITE3)
    db = tmp_path / "apply-check.sqlite3"
    sql = ";\n".join(p.read_text(encoding="utf-8") for p in migration_files())
    proc = subprocess.run([SQLITE3, str(db)], input=sql, text=True,
                          capture_output=True)
    assert proc.returncode == 0, "sqlite3 rejected the migrations:\n%s" % proc.stderr
    assert "Error" not in proc.stderr, proc.stderr
    assert db.exists(), "sqlite3 created no database -- the fetch/run did nothing"


def test_table_census_matches_the_pg_source(tmp_path):
    """111 distinct core tables, by the same count the emitter printed."""
    if not Path(SQLITE3).exists():
        pytest.skip("sqlite3 binary not available at %s" % SQLITE3)
    db = tmp_path / "census-check.sqlite3"
    sql = ";\n".join(p.read_text(encoding="utf-8") for p in migration_files())
    proc = subprocess.run([SQLITE3, str(db)], input=sql, text=True,
                          capture_output=True)
    assert proc.returncode == 0, proc.stderr
    con = sqlite3.connect(str(db))
    try:
        n = con.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'd1_local%'").fetchone()[0]
    finally:
        con.close()
    assert n == EXPECTED_TABLES, "expected %d tables, sqlite made %d" % (
        EXPECTED_TABLES, n)


def test_schema_version_markers_are_monotonic_from_2():
    """Version 1 belongs to DIG-2901; every generated file adds exactly one."""
    versions = []
    for path in migration_files():
        body = path.read_text(encoding="utf-8")
        found = re.findall(r"INSERT INTO d1_local_schema_version.*?WHERE version = (\d+)",
                           body, re.S)
        assert len(found) == 1, "%s carries %d markers, expected 1" % (path.name, len(found))
        versions.append(int(found[0]))
    assert versions == sorted(versions), "markers out of order: %s" % versions
    # 0001 carries version 1 (DIG-2901's placeholder); each generated file adds
    # exactly one, so the stream must be a gapless 1..N.
    assert versions == list(range(1, 1 + len(versions))), \
        "markers are not 1..%d: %s" % (len(versions), versions)


def test_generated_migrations_are_schema_only():
    """No seed/data path sneaks in: no INSERT of business rows, no Supabase DSN."""
    for path in migration_files():
        body = path.read_text(encoding="utf-8")
        if path.name == "0001_schema.sql":
            continue  # DIG-2901's placeholder, owns its own shape
        assert "supabase.co" not in body.lower(), path.name
        assert not re.search(r"\bCOPY\b|\bIMPORT\b", body, re.I), path.name
        inserts = [ln for ln in body.splitlines()
                   if ln.strip().upper().startswith("INSERT")
                   and "d1_local_schema_version" not in ln]
        assert not inserts, "%s inserts rows: %s" % (path.name, inserts[:2])
