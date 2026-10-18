"""Unit tests for scripts/inventory/supabase_caller_inventory.py (DIG-2889).

The exit scope for Supabase is "which table does which module touch", so the
caller map is the document a sequencing decision is read off. Two properties
matter and neither is obvious from the rendered table:

1. **The table universe comes from the migrations.** A name that no migration
   creates is not a caller, so a prose mention (or a table that only exists in
   the other repo) cannot inflate the map. These tests pin that with an A/B on
   identical source text where only the migration is added or removed.

2. **DDL is not a caller.** A `CREATE TABLE` proves the schema exists, not that
   any module depends on it. Counting migrations as callers would send the
   migration effort at migrations instead of at code.

They drive ``main()`` and read the rendered markdown rather than poking report
internals, so the assertions stay valid if the report shape is refactored. Each
test builds a tiny throwaway git repo, so they do not depend on the shape of
this repository.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "inventory" / "supabase_caller_inventory.py"

READER = """\
def load_theses(conn):
    return conn.from("theses").select("id").limit(10)


def write_position(conn, row):
    conn.table("positions").insert(row)
"""

# twelve-x passes table names as bare strings to a connector helper, so the
# map must find this even though no PostgREST idiom appears in the file.
STRING_CALLER = """\
QUERIES = {"digest": "fx_daily_digest"}


def digest(conn, run_date):
    return conn.query(QUERIES["digest"])
"""

MIGRATION = """\
CREATE TABLE theses (id uuid primary key, title text);
CREATE TABLE positions (id uuid primary key, thesis_id uuid);
"""

MIGRATION_WITH_EXTRA = (
    MIGRATION
    + "CREATE TABLE fx_daily_digest (run_date date primary key, body text);\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path, migration: str, name: str = "repo") -> Path:
    repo = tmp_path / name
    (repo / "db" / "migrations").mkdir(parents=True)
    (repo / "app").mkdir()
    (repo / "db" / "migrations" / "0001_init.sql").write_text(migration, encoding="utf-8")
    (repo / "app" / "reader.py").write_text(READER, encoding="utf-8")
    (repo / "app" / "digest.py").write_text(STRING_CALLER, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def _run(tmp_path: Path, repo: Path, name: str = "out.md") -> str:
    out = tmp_path / name
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", f"fixture={repo}", "--md", str(out)],
        capture_output=True,
        text=True,
    )
    # The exit code is a repo-level gate: its controls assert that THIS
    # repository has a table universe, a connection surface and the expected
    # control tables. A three-file fixture cannot satisfy them, so the code is
    # pinned separately by test_controls_gate_the_exit_code below. What these
    # tests assert is the map the run produced.
    assert out.exists(), f"no document written:\n{rc.stdout}\n{rc.stderr}"
    return out.read_text(encoding="utf-8")


def test_migrated_table_is_reported_with_its_caller(tmp_path):
    md = _run(tmp_path, _make_repo(tmp_path, MIGRATION))

    assert "theses" in md, "a table a migration creates must appear in the map"
    # Non-vacuity: the caller line names the file, so the mechanism really fired
    # and the table is not present as a name-only mention.
    lines = [ln for ln in md.splitlines() if "theses" in ln and "app/reader.py" in ln]
    assert lines, f"no caller row for theses:\n{md[:4000]}"


def test_a_table_no_migration_creates_is_not_a_caller(tmp_path):
    """Same fixture, migration emptied: pins the two halves of the universe rule.

    A ``.from("theses")`` call is a dependency whether or not a migration
    defines the table -- a missing definition is exactly the sort of defect
    this map should surface, so it is kept. A table merely NAMED in SQL text is
    the opposite case: it is counted only when the migrations create it, so
    prose and stale identifiers cannot inflate the map.
    """
    repo = _make_repo(tmp_path, "", "without")
    (repo / "app" / "ghost.py").write_text(
        "def w(conn):\n    return conn.execute('INSERT INTO ghost_table (id) VALUES (1)')\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ghost")
    md = _run(tmp_path, repo, name="without.md")

    assert "theses" in md, "a .from() call is a dependency even with no definition"
    assert "app/reader.py" in _caller_column(md, "theses"), (
        "the call site must still be attributed to the table it reads:\n" + md[:4000]
    )
    assert "ghost_table" not in md, (
        "a table named only in SQL text, created by no migration, is not a caller:\n"
        + md[:4000]
    )


def _caller_column(md: str, table: str) -> str:
    """Return the caller column of the per-table row, for a table."""
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols and cols[0] == f"`{table}`":
            # table | operations | mechanisms | callers | defined in
            assert len(cols) >= 5, f"unexpected table row shape: {cols}"
            return cols[3]
    raise AssertionError(f"no table row for {table}:\n{md[:4000]}")


def test_ddl_is_not_reported_as_a_caller(tmp_path):
    md = _run(tmp_path, _make_repo(tmp_path, MIGRATION))

    # The migration that CREATEs a table names it in the "defined in" column,
    # which is correct. It must never appear among the CALLERS: that would send
    # the exit effort at migrations instead of at the code that depends on them.
    callers = _caller_column(md, "theses")
    assert "0001_init.sql" not in callers, f"DDL counted as a caller: {callers!r}"
    assert "app/reader.py" in callers, f"control: the real caller is missing: {callers!r}"


def test_bare_string_table_reference_is_found(tmp_path):
    """The twelve-x idiom: a table name in a plain string, no PostgREST call."""
    md = _run(tmp_path, _make_repo(tmp_path, MIGRATION_WITH_EXTRA))

    assert "fx_daily_digest" in md, "control: the added table is in the universe"
    lines = [ln for ln in md.splitlines() if "fx_daily_digest" in ln and "app/digest.py" in ln]
    assert lines, f"a string-only reference was not counted as a caller:\n{md[:4000]}"


def test_controls_gate_the_exit_code(tmp_path):
    """A repo with no migrations has nothing to map, so every control fails."""
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fixture")

    rc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            f"empty={repo}",
            "--md",
            str(tmp_path / "empty.md"),
        ],
        capture_output=True,
        text=True,
    )

    assert rc.returncode == 1, "a run with no tables must not report success"
    assert "CONTROL FAIL" in rc.stdout, f"no failing control reported:\n{rc.stdout}"