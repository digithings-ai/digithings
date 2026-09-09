"""Contract tests for migration 076, private dashboard research corpus (#2613)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "076_olympus_research_corpus.sql"

TABLE = "olympus_research_corpus"
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
    "user_id",
    "profile_id",
    "tenant_id",
    "profile_key",
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


def _table_body(sql: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{TABLE}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {TABLE}"
    return match.group("body")


def test_migration_is_the_only_076() -> None:
    assert sorted(MIGRATIONS_DIR.glob("076_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_075() -> None:
    assert (MIGRATIONS_DIR / "075_olympus_profile_config.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert 75 in numbers
    assert 76 in numbers
    assert numbers.index(76) == numbers.index(75) + 1


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_table_exists(sql: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{TABLE}\b",
        sql,
        re.IGNORECASE,
    )


def test_stable_uuid_primary_key(sql: str) -> None:
    body = _table_body(sql)
    assert re.search(r"\bid\s+uuid\s+PRIMARY KEY\b", body, re.I)


def test_tenant_agnostic_corpus_key(sql: str) -> None:
    body = _table_body(sql)
    assert re.search(r"\bcorpus_key\s+text\s+NOT NULL\b", body, re.I)
    assert "theme|asset|segment" in body
    assert re.search(r"\bwriter_role\s+text\s+NOT NULL\b", body, re.I)
    assert "payload" in body


def test_unique_corpus_key_index(sql: str) -> None:
    assert re.search(r"uq_olympus_research_corpus_key", sql, re.IGNORECASE)
    assert re.search(
        rf"UNIQUE\s+INDEX[\s\S]*?ON\s+public\.{TABLE}\s*\(\s*corpus_key\s*\)",
        sql,
        re.IGNORECASE,
    )


def test_rls_enabled_with_no_policies(sql: str) -> None:
    assert re.search(
        rf"ALTER\s+TABLE\s+public\.{TABLE}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(rf"CREATE\s+POLICY\b[^;]*{TABLE}", sql, re.IGNORECASE)


@pytest.mark.parametrize("role", PUBLIC_ROLES)
def test_client_roles_fully_revoked(sql: str, role: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+[^\n]*\b{role}\b",
        sql,
        re.IGNORECASE,
    )


def test_service_role_select_insert_only(sql: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"GRANT\s+SELECT\s*,\s*INSERT\s+ON\s+public\.{TABLE}\s+TO\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(
        rf"GRANT\s+[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b[^;]*ON\s+public\.{TABLE}\b",
        sql,
        re.IGNORECASE,
    )


def test_append_only_triggers(sql: str) -> None:
    assert re.search(
        rf"BEFORE\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.{TABLE}",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"BEFORE\s+TRUNCATE\s+ON\s+public\.{TABLE}",
        sql,
        re.IGNORECASE,
    )


def test_no_public_views_in_this_migration(sql: str) -> None:
    assert not re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", sql, re.IGNORECASE)


def test_no_forbidden_payload_columns(sql: str) -> None:
    body = _table_body(sql).lower()
    for col in FORBIDDEN_COLUMNS:
        # payload CHECK may mention forbidden keys as string literals — that's OK.
        # Forbid them as *columns*.
        assert not re.search(rf"\b{col}\s+", body), f"forbidden column {col}"
