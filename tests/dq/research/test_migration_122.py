"""Contract tests for migration 122, archive_objects RLS + REVOKE (#3793)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "122_archive_objects_rls.sql"
TABLE = "archive_objects"
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_migration_is_the_only_122() -> None:
    assert sorted(MIGRATIONS_DIR.glob("122_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_121() -> None:
    assert (MIGRATIONS_DIR / "121_checkpoint_blobs_nullable.sql").is_file()


def test_does_not_amend_119() -> None:
    """119 must stay as the create-only migration; lockdown is a follow-up file."""
    create = (MIGRATIONS_DIR / "119_archive_objects.sql").read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" not in create.upper()
    assert "REVOKE ALL" not in create.upper()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_privacy_rls_and_grants(sql: str) -> None:
    assert f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY" in sql
    assert f"REVOKE ALL ON public.{TABLE} FROM PUBLIC, anon, authenticated" in sql
    assert f"REVOKE ALL ON public.{TABLE} FROM service_role" in sql
    assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{TABLE} TO service_role" in sql


def test_zero_policies(sql: str) -> None:
    assert "CREATE POLICY" not in sql.upper()
    assert "CREATE OR REPLACE POLICY" not in sql.upper()


def test_identity_sequence_locked(sql: str) -> None:
    assert "pg_get_serial_sequence('public.archive_objects', 'id')" in sql
    assert "GRANT USAGE, SELECT ON SEQUENCE" in sql
    assert "REVOKE ALL ON SEQUENCE" in sql


def test_schema_documents_lockdown() -> None:
    schema = (REPO_ROOT / "digiquant" / "supabase" / "SCHEMA.md").read_text(encoding="utf-8")
    assert "archive_objects" in schema
    assert "122" in schema
    assert "SET LOCAL ROLE" in schema
