"""Contract tests for migration 072, private dashboard period accounting schema (#2596)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "072_olympus_period_accounting.sql"

TABLES = (
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
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
    "payload",
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


def test_migration_is_the_only_072() -> None:
    assert sorted(MIGRATIONS_DIR.glob("072_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_071() -> None:
    assert (MIGRATIONS_DIR / "071_olympus_position_events_book_source.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert numbers[-1] >= 72
    assert 72 in numbers


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_exist(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


def test_periods_use_stable_uuid_primary_key(sql: str) -> None:
    body = _table_body(sql, "olympus_accounting_periods")
    assert re.search(r"\bid\s+uuid\s+PRIMARY KEY\b", body, re.I)


def test_period_status_vocabulary(sql: str) -> None:
    body = _table_body(sql, "olympus_accounting_periods")
    for status in ("final", "estimated", "incomplete", "failed"):
        assert f"'{status}'" in body


def test_final_requires_empty_quality_reasons(sql: str) -> None:
    assert "chk_olympus_accounting_periods_final_clean" in sql
    assert re.search(
        r"status\s*<>\s*'final'\s*OR\s*cardinality\(\s*quality_reasons\s*\)\s*=\s*0",
        sql,
        re.IGNORECASE,
    )


def test_contributions_and_holdings_fk_to_period(sql: str) -> None:
    for table in ("olympus_accounting_contributions", "olympus_accounting_holdings"):
        body = _table_body(sql, table)
        assert re.search(
            r"FOREIGN KEY\s*\(\s*period_id\s*,\s*period_date\s*\)\s+"
            r"REFERENCES\s+public\.olympus_accounting_periods",
            body,
            re.IGNORECASE,
        )


@pytest.mark.parametrize("table", TABLES)
def test_rls_enabled_with_no_policies(sql: str, table: str) -> None:
    assert re.search(
        rf"ALTER\s+TABLE\s+public\.{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(rf"CREATE\s+POLICY\b[^;]*{table}", sql, re.IGNORECASE)


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("role", PUBLIC_ROLES)
def test_client_roles_fully_revoked(sql: str, table: str, role: str) -> None:
    # Matches both `FROM anon` and `FROM PUBLIC, anon, authenticated`.
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+[^\n]*\b{role}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_service_role_select_insert_only(sql: str, table: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"GRANT\s+SELECT\s*,\s*INSERT\s+ON\s+public\.{table}\s+TO\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(
        rf"GRANT\s+[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b[^;]*ON\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_append_only_triggers(sql: str, table: str) -> None:
    assert re.search(
        rf"BEFORE\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.{table}",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"BEFORE\s+TRUNCATE\s+ON\s+public\.{table}",
        sql,
        re.IGNORECASE,
    )


def test_no_public_views_in_this_migration(sql: str) -> None:
    assert not re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", sql, re.IGNORECASE)


def test_no_forbidden_payload_columns(sql: str) -> None:
    lowered = sql.lower()
    for col in FORBIDDEN_COLUMNS:
        assert not re.search(rf"\b{col}\s+", lowered)


def test_supersession_indexes(sql: str) -> None:
    assert "uq_olympus_accounting_periods_one_root" in sql
    assert "uq_olympus_accounting_periods_supersedes" in sql


def test_header_declares_privacy(raw: str) -> None:
    header = raw.split("CREATE TABLE", 1)[0].lower()
    assert "user-private" in header or "private" in header
    assert "anon" in header
