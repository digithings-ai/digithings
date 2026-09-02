"""Structural contract tests for migration 105 (documents.workspace_id)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "105_documents_workspace_id.sql"
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
SQL_STRING = r"'(?:[^']|'')*'"

WRITERS = (
    "supabase_io.py::publish_document",
    "publish_phase.py",
    "commit_io.py",
    "attention_plan_io.py",
    "beliefs_distillation.py",
    "digiquant/scripts/research/publish_document.py",
    "digiquant/scripts/research/publish_research.py",
    "digiquant/scripts/research/materialize_snapshot.py",
    "digiquant/scripts/research/backfill_normalize_schemas.py",
    "digiquant/scripts/research/backfill_pm_rebalance_and_activity.py",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_migration_is_the_only_105() -> None:
    assert sorted(MIGRATIONS_DIR.glob("105_*.sql")) == [MIGRATION_PATH]


def test_header_enumerates_every_documents_writer(raw: str) -> None:
    header = raw.split("ALTER TABLE")[0]
    assert "HUMAN GATE" in header
    assert "REPLACE" in header
    for writer in WRITERS:
        assert writer in header


def test_legacy_unique_is_dropped_not_kept(sql: str) -> None:
    assert re.search(r"DROP CONSTRAINT IF EXISTS documents_date_document_key_key", sql, re.I)
    assert re.search(r"DROP CONSTRAINT IF EXISTS documents_new_date_document_key", sql, re.I)
    assert re.search(r"UNIQUE\s*\(\s*workspace_id\s*,\s*date\s*,\s*document_key\s*\)", sql, re.I)


def test_anon_read_is_not_touched(sql: str) -> None:
    assert not re.search(r"DROP POLICY[^;]*anon_read", sql, re.I)
    assert not re.search(r'CREATE POLICY\s+"anon_read"', sql, re.I)


def test_authenticated_own_workspace_select(sql: str) -> None:
    assert re.search(
        r'CREATE POLICY\s+"authenticated_select_documents"\s+ON\s+public\.documents',
        sql,
        re.I,
    )
    assert "workspace_members" in sql
    assert "6b753576-ced9-5319-9bfa-c5d0aacd9319" in sql
    assert "1105372f-4109-5815-be5a-21091ccfc8ad" in sql


def test_job_runs_persist_disabled(sql: str) -> None:
    match = re.search(
        r"ALTER TABLE public\.job_runs ADD CONSTRAINT job_runs_status_check\s+"
        r"CHECK \(status IN \((?P<values>.*?)\)\)",
        sql,
        re.I | re.S,
    )
    assert match
    values = set(re.findall(r"'([^']+)'", match.group("values")))
    assert "persist_disabled" in values


def test_backfill_house_then_not_null(sql: str) -> None:
    assert re.search(
        r"ALTER TABLE public\.documents ADD COLUMN IF NOT EXISTS workspace_id", sql, re.I
    )
    assert re.search(r"SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'", sql)
    assert re.search(r"ALTER COLUMN workspace_id SET NOT NULL", sql, re.I)


def test_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()
