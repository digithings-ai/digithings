"""Contract tests for migration 079, private dashboard forecast registry (#2663)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "079_olympus_forecast_registry.sql"

TABLES = (
    "olympus_forecast_assessments",
    "olympus_forecast_amendments",
)
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
FORBIDDEN_COLUMNS = (
    "prompt",
    "prompt_body",
    "response",
    "response_body",
    "api_key",
    "secret",
    "raw_exception",
    "reasoning",
    "message",
    "messages",
)
FORBIDDEN_SQL = (
    "INSERT INTO",
    "INSERT INTO public.dashboard_forecast",
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


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {table}"
    return match.group("body")


def test_migration_is_the_only_079() -> None:
    assert sorted(MIGRATIONS_DIR.glob("079_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_078() -> None:
    assert (MIGRATIONS_DIR / "078_attention_plan_category.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    upper = sql.upper()
    assert "INSERT INTO" not in upper


@pytest.mark.parametrize("table", TABLES)
def test_tables_exist(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


def test_assessment_pk_is_forecast_id(sql: str) -> None:
    body = _table_body(sql, "olympus_forecast_assessments")
    assert re.search(r"\bforecast_id\s+uuid\s+PRIMARY KEY\b", body, re.I)


def test_amendment_fk_to_base(sql: str) -> None:
    body = _table_body(sql, "olympus_forecast_amendments")
    assert re.search(r"\bamendment_id\s+uuid\s+PRIMARY KEY\b", body, re.I)
    assert re.search(
        r"FOREIGN KEY\s*\(base_forecast_id\)\s+REFERENCES\s+public\.olympus_forecast_assessments",
        body,
        re.I,
    )


@pytest.mark.parametrize("table", TABLES)
def test_privacy_rls_and_grants(sql: str, table: str) -> None:
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated" in sql
    assert f"REVOKE ALL ON public.{table} FROM service_role" in sql
    assert f"GRANT SELECT, INSERT ON public.{table} TO service_role" in sql


@pytest.mark.parametrize("table", TABLES)
def test_append_only_triggers(sql: str, table: str) -> None:
    assert f"reject_{table}_mutation" in sql or "reject_olympus_forecast_registry_mutation" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "BEFORE TRUNCATE" in sql


@pytest.mark.parametrize("table", TABLES)
def test_no_forbidden_payload_columns(sql: str, table: str) -> None:
    body = _table_body(sql, table).lower()
    for col in FORBIDDEN_COLUMNS:
        assert re.search(rf"\b{col}\b", body) is None, f"{table} must not store {col}"


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()
