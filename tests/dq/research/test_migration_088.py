"""Contract tests for migration 088, private research-state store (#2854 / WP12.2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "088_olympus_research_state.sql"

TABLES = (
    "olympus_research_evidence",
    "olympus_research_belief_versions",
    "olympus_research_expected_event_versions",
    "olympus_research_patches",
    "olympus_research_legacy_refs",
    "olympus_research_state_versions",
    "olympus_research_state_pins",
)
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


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {table}"
    return match.group("body")


def test_migration_is_the_only_088() -> None:
    assert sorted(MIGRATIONS_DIR.glob("088_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_087() -> None:
    assert (MIGRATIONS_DIR / "087_olympus_forecast_outcome_horizon_unique.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_exist(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_privacy_rls_and_grants(sql: str, table: str) -> None:
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated" in sql
    assert f"REVOKE ALL ON public.{table} FROM service_role" in sql
    assert f"GRANT SELECT, INSERT ON public.{table} TO service_role" in sql


@pytest.mark.parametrize("table", TABLES)
def test_append_only_triggers(sql: str, table: str) -> None:
    assert "reject_olympus_research_state_mutation" in sql
    assert f"reject_{table}_mutation" in sql or "reject_olympus_research_state_mutation" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "BEFORE TRUNCATE" in sql


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()


def test_legacy_refs_force_null_known_at(sql: str) -> None:
    body = _table_body(sql, "olympus_research_legacy_refs")
    assert re.search(r"known_at\s+timestamptz\b", body, re.I)
    assert "chk_olympus_research_legacy_refs_null_known" in body
    assert re.search(r"known_at\s+IS\s+NULL", body, re.I)


def test_state_versions_parent_fk(sql: str) -> None:
    body = _table_body(sql, "olympus_research_state_versions")
    assert re.search(
        r"FOREIGN KEY\s*\(parent_state_version_id\)\s+REFERENCES\s+"
        r"public\.olympus_research_state_versions",
        body,
        re.I,
    )


def test_pins_pk_is_run_attempt(sql: str) -> None:
    body = _table_body(sql, "olympus_research_state_pins")
    assert re.search(r"PRIMARY KEY\s*\(\s*run_id\s*,\s*attempt_id\s*\)", body, re.I)
    assert re.search(
        r"FOREIGN KEY\s*\(state_version_id\)\s+REFERENCES\s+"
        r"public\.olympus_research_state_versions",
        body,
        re.I,
    )


def test_no_update_or_delete_grants(sql: str) -> None:
    assert "GRANT UPDATE" not in sql.upper()
    assert "GRANT DELETE" not in sql.upper()
    assert "GRANT ALL" not in sql.upper()
